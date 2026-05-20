#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import random
import re
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from collections import deque
from pathlib import Path
from urllib import error as url_error
from urllib import request as url_request

import edge_tts
import certifi
from flask import Flask, jsonify, request, send_file
from werkzeug.utils import secure_filename
from werkzeug.exceptions import HTTPException

from ppt_to_video import estimate_chars, extract_notes, extract_slide_texts, write_notes_copy


BASE_DIR = Path(__file__).parent.resolve()
STORAGE_DIR = BASE_DIR / "storage"
UPLOAD_DIR = STORAGE_DIR / "uploads"
JOB_DIR = STORAGE_DIR / "jobs"
SETTINGS_FILE = STORAGE_DIR / "settings.json"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
JOB_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
jobs: dict[str, dict] = {}
server_logs: deque[dict] = deque(maxlen=300)
token_usage_history: deque[dict] = deque(maxlen=120)


def env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


SCRIPT_MAX_CONCURRENT_JOBS = env_int("SCRIPT_MAX_CONCURRENT_JOBS", 2)
AI_MAX_CONCURRENT_REQUESTS = env_int("AI_MAX_CONCURRENT_REQUESTS", 2)
AI_REQUEST_RETRIES = env_int("AI_REQUEST_RETRIES", 4)
script_job_slots = threading.BoundedSemaphore(SCRIPT_MAX_CONCURRENT_JOBS)
ai_request_slots = threading.BoundedSemaphore(AI_MAX_CONCURRENT_REQUESTS)

TOKEN_PRICING = {
    "input_per_million": 2.5,
    "completion_per_million": 15.0,
    "cache_read_per_million": 0.25,
}
USER_AI_SETTING_KEYS = {
    "ai_base_url",
    "ai_api_key",
    "ai_model",
    "ai_verify_ssl",
    "default_script_style",
}


@app.errorhandler(Exception)
def handle_exception(exc: Exception):
    if isinstance(exc, HTTPException):
        return exc
    append_server_log(f"未处理异常：{exc}", "error")
    if request.path.startswith("/api/"):
        return jsonify({"error": str(exc)}), 500
    raise exc


def default_settings() -> dict:
    return {
        "ai_base_url": "",
        "ai_api_key": "",
        "ai_model": "",
        "ai_verify_ssl": True,
        "default_script_style": "培训讲师 · 稳妥清晰",
        "subtitle_style": "classic",
        "users": {},
    }


def load_settings() -> dict:
    if not SETTINGS_FILE.exists():
        return default_settings()
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        settings = {**default_settings(), **data}
        if not isinstance(settings.get("users"), dict):
            settings["users"] = {}
        return settings
    except Exception:
        return default_settings()


def save_settings(data: dict) -> dict:
    current = load_settings()
    merged = {**current, **data}
    if data.get("ai_api_key", "") == "":
        merged["ai_api_key"] = current.get("ai_api_key", "")
    SETTINGS_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged


def user_settings(settings: dict, user: str) -> dict:
    users = settings.setdefault("users", {})
    stored = users.get(user) if isinstance(users, dict) else {}
    if not isinstance(stored, dict):
        stored = {}
    defaults = default_settings()
    return {
        "ai_base_url": stored.get("ai_base_url", ""),
        "ai_api_key": stored.get("ai_api_key", ""),
        "ai_model": stored.get("ai_model", ""),
        "ai_verify_ssl": stored.get("ai_verify_ssl", defaults["ai_verify_ssl"]),
        "default_script_style": stored.get("default_script_style", defaults["default_script_style"]),
        "subtitle_style": settings.get("subtitle_style", defaults["subtitle_style"]),
    }


def load_user_settings(user: str) -> dict:
    return user_settings(load_settings(), user)


def save_user_settings(user: str, data: dict) -> dict:
    settings = load_settings()
    users = settings.setdefault("users", {})
    current = users.get(user, {})
    if not isinstance(current, dict):
        current = {}

    updates = {key: data[key] for key in USER_AI_SETTING_KEYS if key in data}
    if "ai_api_key" in updates and not updates["ai_api_key"]:
        updates["ai_api_key"] = current.get("ai_api_key", "")
    users[user] = {**current, **updates}

    if "subtitle_style" in data:
        settings["subtitle_style"] = data.get("subtitle_style", "classic").strip() or "classic"

    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    return user_settings(settings, user)


def public_settings(settings: dict, user: str) -> dict:
    current = user_settings(settings, user)
    return {
        "ai_base_url": current.get("ai_base_url", ""),
        "ai_model": current.get("ai_model", ""),
        "ai_verify_ssl": current.get("ai_verify_ssl", True),
        "default_script_style": current.get("default_script_style", ""),
        "subtitle_style": current.get("subtitle_style", "classic"),
        "has_api_key": bool(current.get("ai_api_key")),
    }


def build_ssl_context(verify_ssl: bool = True) -> ssl.SSLContext:
    if not verify_ssl:
        return ssl._create_unverified_context()

    # Prefer the system trust store and add certifi as a supplemental CA bundle.
    ssl_context = ssl.create_default_context()
    try:
        ssl_context.load_verify_locations(cafile=certifi.where())
    except Exception:
        pass
    return ssl_context


def ai_chat(settings: dict, messages: list[dict], temperature: float = 0.4, log_prefix: str = "AI") -> str:
    base_url = settings.get("ai_base_url", "").strip().rstrip("/")
    api_key = settings.get("ai_api_key", "").strip()
    model = settings.get("ai_model", "").strip()
    verify_ssl = bool(settings.get("ai_verify_ssl", True))
    if not base_url or not api_key or not model:
        raise ValueError("请先在设置页填写 Base URL、API Key 和 Model。")

    body = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }).encode("utf-8")
    req = url_request.Request(
        f"{base_url}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    ssl_context = build_ssl_context(verify_ssl=verify_ssl)
    payload = open_ai_chat_with_retry(req, ssl_context, log_prefix)
    record_token_usage(payload.get("usage") or {})
    return payload["choices"][0]["message"]["content"].strip()


def is_retryable_ai_error(exc: Exception) -> bool:
    if isinstance(exc, url_error.HTTPError):
        return exc.code in {408, 409, 425, 429, 500, 502, 503, 504}
    return isinstance(
        exc,
        (
            url_error.URLError,
            ssl.SSLError,
            TimeoutError,
            socket.timeout,
            ConnectionError,
        ),
    )


def open_ai_chat_with_retry(req: url_request.Request, ssl_context: ssl.SSLContext, log_prefix: str) -> dict:
    last_exc: Exception | None = None
    for attempt in range(1, AI_REQUEST_RETRIES + 1):
        try:
            with ai_request_slots:
                with url_request.urlopen(req, timeout=120, context=ssl_context) as resp:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            last_exc = exc
            if not is_retryable_ai_error(exc) or attempt >= AI_REQUEST_RETRIES:
                raise
            delay = min(8.0, 1.5 * (2 ** (attempt - 1))) + random.uniform(0, 0.5)
            append_server_log(
                f"{log_prefix} 请求临时失败，{delay:.1f} 秒后重试（第 {attempt}/{AI_REQUEST_RETRIES} 次）：{exc}",
                "error",
            )
            time.sleep(delay)
    assert last_exc is not None
    raise last_exc


def usage_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def normalize_usage(usage: dict) -> dict:
    prompt_tokens = usage_int(usage.get("prompt_tokens"))
    completion_tokens = usage_int(usage.get("completion_tokens"))
    prompt_details = usage.get("prompt_tokens_details") or {}
    cached_tokens = usage_int(
        prompt_details.get("cached_tokens")
        or prompt_details.get("cache_read_input_tokens")
    )
    billable_input_tokens = max(0, prompt_tokens - cached_tokens)
    return {
        "input_tokens": billable_input_tokens,
        "completion_tokens": completion_tokens,
        "cache_read_tokens": cached_tokens,
        "total_tokens": billable_input_tokens + completion_tokens + cached_tokens,
    }


def usage_costs(usage: dict) -> dict:
    normalized = normalize_usage(usage)
    input_cost = normalized["input_tokens"] / 1_000_000 * TOKEN_PRICING["input_per_million"]
    completion_cost = normalized["completion_tokens"] / 1_000_000 * TOKEN_PRICING["completion_per_million"]
    cache_read_cost = normalized["cache_read_tokens"] / 1_000_000 * TOKEN_PRICING["cache_read_per_million"]
    total_cost = input_cost + completion_cost + cache_read_cost
    return {
        **normalized,
        "input_cost": input_cost,
        "completion_cost": completion_cost,
        "cache_read_cost": cache_read_cost,
        "total_cost": total_cost,
    }


def record_token_usage(usage: dict):
    metrics = usage_costs(usage)
    if not metrics["total_tokens"]:
        return
    token_usage_history.append({
        "time": datetime.now().strftime("%H:%M:%S"),
        **metrics,
    })


def token_usage_payload() -> dict:
    settings = load_settings()
    history = list(token_usage_history)
    totals = {
        "input_tokens": 0,
        "completion_tokens": 0,
        "cache_read_tokens": 0,
        "total_tokens": 0,
        "input_cost": 0.0,
        "completion_cost": 0.0,
        "cache_read_cost": 0.0,
        "total_cost": 0.0,
    }
    for item in history:
        for key in totals:
            totals[key] += item[key]
    return {
        "model": settings.get("ai_model", "").strip(),
        "pricing": TOKEN_PRICING,
        "totals": totals,
        "history": history,
    }


def script_prompt(
    strategy: str,
    style: str,
    enrichment: str,
    slide_no: int,
    slide_text: str,
    note: str,
    target_chars: int | None = None,
) -> list[dict]:
    strategy_desc = {
        "short": "只在原备注过短时扩写；如果原备注已经完整，可以在保留其结构的基础上润色。",
        "rewrite": "重写本页完整讲解词，保持培训讲师口吻。",
        "duration": "生成更充分的讲解词，适合拉长整体视频时长，但不要空泛重复。",
    }.get(strategy, "生成清晰、自然的中文讲解词。")
    enrichment_desc = {
        "strict": "严格基于 PPT 页面文字和原备注，只做整理、润色和必要衔接，不增加背景信息。",
        "light": "只基于 PPT 内容，允许少量背景解释和教学化表达，但不得引入无法从页面推断的事实。",
        "teaching": "在事实边界内做教学化展开，补充原因、注意点、操作含义和听众容易理解的解释。",
        "transition": "强化页内和上下页之间的过渡串联，让讲解更连贯，但不得编造具体事实。",
    }.get(enrichment, "只基于 PPT 内容，允许少量背景解释。")
    return [
        {
            "role": "system",
            "content": (
                "你是严谨的中文培训讲师，负责根据 PPT 页面内容生成可直接朗读的演讲者备注。"
                "只输出讲解词正文，不要输出标题、Markdown、项目符号或解释。"
                "不得编造与页面无关的事实；可以做少量衔接、解释和教学化表达。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"页面序号：第 {slide_no} 页\n"
                f"生成策略：{strategy_desc}\n"
                f"讲解风格：{style}\n\n"
                f"补充程度：{enrichment_desc}\n"
                f"{f'本页建议讲稿长度：约 {target_chars} 个中文字符。' if target_chars else ''}\n\n"
                f"【PPT 页面文字】\n{slide_text or '（本页未提取到页面文字）'}\n\n"
                f"【原备注】\n{note or '（本页暂无原备注）'}\n\n"
                "请生成一段自然、稳妥、适合中文配音朗读的本页讲解词。"
            ),
        },
    ]


def script_expand_prompt(
    style: str,
    enrichment: str,
    slide_no: int,
    slide_text: str,
    note: str,
    current_script: str,
    extra_chars: int,
) -> list[dict]:
    enrichment_desc = {
        "strict": "严格基于 PPT 页面文字和原备注，只做整理、润色和必要衔接，不增加背景信息。",
        "light": "只基于 PPT 内容，允许少量背景解释和教学化表达，但不得引入无法从页面推断的事实。",
        "teaching": "在事实边界内做教学化展开，补充原因、注意点、操作含义和听众容易理解的解释。",
        "transition": "强化页内和上下页之间的过渡串联，让讲解更连贯，但不得编造具体事实。",
    }.get(enrichment, "只基于 PPT 内容，允许少量背景解释。")
    return [
        {
            "role": "system",
            "content": (
                "你是严谨的中文培训讲师，负责在现有讲稿基础上做增量扩写。"
                "保持原有结构、事实边界和讲师口吻，不要整页重写。"
                "只输出扩写后的完整讲解词正文，不要输出说明。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"页面序号：第 {slide_no} 页\n"
                f"讲解风格：{style}\n"
                f"补充程度：{enrichment_desc}\n"
                f"目标：在当前讲稿基础上额外增加约 {extra_chars} 个中文字符。\n\n"
                f"【PPT 页面文字】\n{slide_text or '（本页未提取到页面文字）'}\n\n"
                f"【原备注】\n{note or '（本页暂无原备注）'}\n\n"
                f"【当前讲稿】\n{current_script or '（当前讲稿为空）'}\n\n"
                "请保留现有结构和事实边界，优先补充原因、解释、注意事项和过渡语，避免空泛重复。"
            ),
        },
    ]


def text_char_count(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def estimate_minutes_from_scripts(scripts: list[str], chars_per_minute: int = 264) -> float:
    total_chars = sum(text_char_count(script) for script in scripts)
    return total_chars / chars_per_minute if chars_per_minute else 0.0


def should_expand_duration(target_minutes: float, estimated_minutes: float) -> bool:
    if not target_minutes:
        return False
    if estimated_minutes >= target_minutes * 0.9:
        return False
    return (target_minutes - estimated_minutes) >= 3


def pick_expandable_indices(scripts: list[str], slide_texts: list[str], limit: int | None = None) -> list[int]:
    scored = []
    for idx, (script, slide_text) in enumerate(zip(scripts, slide_texts)):
        score = text_char_count(slide_text) - text_char_count(script)
        if score > 40:
            scored.append((score, idx))
    scored.sort(reverse=True)
    indices = [idx for _, idx in scored]
    if limit is not None:
        return indices[:limit]
    return indices


def append_log(job: dict, text: str, state: str = "进行中"):
    job.setdefault("logs", []).append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "text": text,
        "state": state,
    })


def append_server_log(text: str, level: str = "info"):
    server_logs.append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "text": text,
        "level": level,
    })


def client_user_label(value: str | None = None) -> str:
    label = (value or request.headers.get("X-Client-User") or "").strip()
    label = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "", label)
    return label[:32] or "未知用户"


def job_user_label(job: dict | None) -> str:
    if not job:
        return "未知用户"
    return job.get("user") or "未知用户"


def job_log_prefix(kind: str, job_id: str, job: dict | None = None) -> str:
    return f"{kind}任务 {job_id}（{job_user_label(job)}）"


def append_script_progress(job: dict | None, job_id: str | None, text: str, state: str = "进行中"):
    if job is not None:
        append_log(job, text, state)
    prefix = f"{job_log_prefix('讲稿', job_id, job)}：" if job_id else ""
    append_server_log(f"{prefix}{text}", "error" if state == "失败" else "info")


def client_filename(filename: str | None, fallback: str) -> str:
    name = re.split(r"[\\/]", filename or "")[-1].strip()
    return name or fallback


def upload_meta_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.json")


def save_upload_metadata(path: Path, original_name: str) -> None:
    upload_meta_path(path).write_text(
        json.dumps({"original_name": original_name}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_upload_original_name(path: Path) -> str:
    meta_path = upload_meta_path(path)
    if meta_path.exists():
        try:
            original_name = json.loads(meta_path.read_text(encoding="utf-8")).get("original_name", "")
            if original_name:
                return client_filename(original_name, path.name)
        except Exception:
            pass

    # Backward-compatible fallback for uploads created before metadata existed.
    match = re.match(r"^[0-9a-f]{32}-(.+)$", path.name)
    return match.group(1) if match else path.name


def download_name_for_upload(path: Path, suffix: str | None = None) -> str:
    original_name = load_upload_original_name(path)
    if suffix is None:
        return original_name
    stem = Path(original_name).stem or path.stem
    return f"{stem}{suffix}"


def generate_scripts_payload(src: Path, payload: dict, job: dict | None = None, job_id: str | None = None) -> dict:
    settings = load_user_settings(job_user_label(job))
    strategy = payload.get("strategy", "short")
    style = payload.get("style") or settings.get("default_script_style") or "培训讲师 · 稳妥清晰"
    enrichment = payload.get("enrichment", "light")
    write_to_ppt = True
    auto_expand_duration = bool(payload.get("auto_expand_duration"))
    short_threshold = int(payload.get("short_threshold") or 180)
    target_minutes = float(payload.get("target_minutes") or 40)
    slide_texts = extract_slide_texts(src)
    notes = extract_notes(src)
    target_chars_per_slide = None
    if strategy == "duration" and slide_texts:
        target_chars_per_slide = max(80, int(target_minutes * 264 / len(slide_texts)))

    scripts = []
    for idx, slide_text in enumerate(slide_texts, start=1):
        note = notes[idx - 1] if idx - 1 < len(notes) else ""
        if strategy == "short" and len(re.sub(r"\s+", "", note)) >= short_threshold:
            script = note
        else:
            script = ai_chat(
                settings,
                script_prompt(strategy, style, enrichment, idx, slide_text, note, target_chars_per_slide),
                log_prefix=job_log_prefix("讲稿", job_id, job) if job_id else "讲稿",
            )
        scripts.append(script)
        append_script_progress(job, job_id, f"已生成第 {idx}/{len(slide_texts)} 页讲稿。")

    expansion_applied = False
    estimated_minutes = estimate_minutes_from_scripts(scripts)
    if strategy == "duration" and auto_expand_duration and should_expand_duration(target_minutes, estimated_minutes):
        append_script_progress(
            job,
            job_id,
            f"首轮讲稿预计约 {estimated_minutes:.1f} 分钟，低于目标 {target_minutes:.1f} 分钟，开始增量补写。"
        )
        missing_chars = max(0, int((target_minutes - estimated_minutes) * 264))
        expandable_indices = pick_expandable_indices(scripts, slide_texts, limit=max(1, len(scripts) // 2))
        if expandable_indices and missing_chars > 0:
            extra_per_page = max(80, missing_chars // len(expandable_indices))
            for turn, idx in enumerate(expandable_indices, start=1):
                note = notes[idx] if idx < len(notes) else ""
                expanded = ai_chat(
                    settings,
                    script_expand_prompt(
                        style,
                        enrichment,
                        idx + 1,
                        slide_texts[idx],
                        note,
                        scripts[idx],
                        extra_per_page,
                    ),
                    log_prefix=job_log_prefix("讲稿", job_id, job) if job_id else "讲稿",
                )
                scripts[idx] = expanded
                append_script_progress(job, job_id, f"已补写第 {turn}/{len(expandable_indices)} 个扩写页面（第 {idx + 1} 页）。")
            estimated_minutes = estimate_minutes_from_scripts(scripts)
            expansion_applied = True
            append_script_progress(job, job_id, f"补写后预计讲稿时长约 {estimated_minutes:.1f} 分钟。")

    output_name = None
    output_download_name = None
    write_result = None
    if write_to_ppt:
        output_download_name = download_name_for_upload(src, ".pptx")
        output_path = JOB_DIR / f"script-{job_id or uuid.uuid4().hex}-{uuid.uuid4().hex}.pptx"
        write_result = write_notes_copy(src, scripts, output_path)
        output_name = output_path.name
        append_script_progress(job, job_id, f"已生成更新备注后的 PPT：{output_download_name}", "完成")

    return {
        "scripts": [
            {"index": idx, "title": (slide_texts[idx - 1].splitlines() or [f'第 {idx} 页'])[0], "script": script}
            for idx, script in enumerate(scripts, start=1)
        ],
        "ppt_output": output_name,
        "ppt_download_name": output_download_name,
        "write_result": write_result,
        "estimated_minutes": estimated_minutes,
        "expansion_applied": expansion_applied,
    }


def run_script_job(job_id: str, src: Path, payload: dict):
    job = jobs[job_id]
    append_log(job, "讲稿生成任务已进入后端队列。")
    append_server_log(f"{job_log_prefix('讲稿', job_id, job)} 已进入队列。")
    acquired = script_job_slots.acquire(blocking=False)
    if not acquired:
        append_log(job, f"当前已有讲稿任务在执行，等待可用名额（最大并行 {SCRIPT_MAX_CONCURRENT_JOBS} 个）。", "排队中")
        append_server_log(f"{job_log_prefix('讲稿', job_id, job)} 等待执行名额。")
        script_job_slots.acquire()
    job["status"] = "running"
    append_log(job, "讲稿生成任务已启动。")
    append_server_log(f"{job_log_prefix('讲稿', job_id, job)} 已启动。")
    try:
        slide_count = len(extract_slide_texts(src))
        if slide_count:
            append_log(job, f"已识别 {slide_count} 页，开始逐页生成讲稿。")
        result = generate_scripts_payload(src, payload, job, job_id)
        if result.get("ppt_output"):
            append_log(job, "已写入新的 PPT 副本。", "完成")
        job["result"] = result
        job["status"] = "done"
        append_log(job, "讲稿生成完成。", "完成")
        append_server_log(f"{job_log_prefix('讲稿', job_id, job)} 已完成。")
    except Exception as exc:
        job["status"] = "error"
        append_log(job, f"讲稿生成失败：{exc}", "失败")
        append_server_log(f"{job_log_prefix('讲稿', job_id, job)} 失败：{exc}", "error")
    finally:
        script_job_slots.release()


async def chinese_voices() -> list[dict]:
    voices = await edge_tts.list_voices()
    result = []
    for v in voices:
        if v["Locale"].startswith("zh-"):
            result.append({
                "id": v["ShortName"],
                "name": v["FriendlyName"],
                "gender": v["Gender"],
                "locale": v["Locale"],
            })
    return result


@app.get("/")
def index():
    return jsonify({"service": "archive-voice-studio-api", "status": "ok"})


@app.get("/api/voices")
def voices():
    return jsonify(asyncio.run(chinese_voices()))


@app.post("/api/analyze")
def analyze():
    file = request.files.get("pptx")
    if not file or not file.filename.lower().endswith(".pptx"):
        return jsonify({"error": "请上传 .pptx 文件"}), 400
    original_name = client_filename(file.filename, f"upload-{uuid.uuid4().hex}.pptx")
    safe_name = secure_filename(original_name) or f"upload-{uuid.uuid4().hex}.pptx"
    path = UPLOAD_DIR / f"{uuid.uuid4().hex}-{safe_name}"
    file.save(path)
    save_upload_metadata(path, original_name)
    notes = extract_notes(path)
    return jsonify({
        "upload_id": path.name,
        "original_name": original_name,
        "slides": len(notes),
        "chars": estimate_chars(notes),
        "empty_notes": sum(1 for n in notes if not n.strip()),
    })


@app.post("/api/script/analyze")
def script_analyze():
    file = request.files.get("pptx")
    if not file or not file.filename.lower().endswith(".pptx"):
        return jsonify({"error": "请上传 .pptx 文件"}), 400
    original_name = client_filename(file.filename, f"upload-{uuid.uuid4().hex}.pptx")
    safe_name = secure_filename(original_name) or f"upload-{uuid.uuid4().hex}.pptx"
    path = UPLOAD_DIR / f"{uuid.uuid4().hex}-{safe_name}"
    file.save(path)
    save_upload_metadata(path, original_name)
    slide_texts = extract_slide_texts(path)
    notes = extract_notes(path)
    slides = []
    for idx, text in enumerate(slide_texts, start=1):
        note = notes[idx - 1] if idx - 1 < len(notes) else ""
        title = next((line.strip() for line in text.splitlines() if line.strip()), f"第 {idx} 页")
        slides.append({
            "index": idx,
            "title": title,
            "text": text,
            "note": note,
            "note_chars": len(re.sub(r"\s+", "", note)),
        })
    return jsonify({
        "upload_id": path.name,
        "original_name": original_name,
        "slides": slides,
        "slide_count": len(slides),
        "chars": estimate_chars(notes),
    })


@app.post("/api/script/generate")
def script_generate():
    try:
        payload = request.get_json(force=True)
        src = UPLOAD_DIR / payload["upload_id"]
        if not src.exists():
            return jsonify({"error": "上传文件不存在"}), 404
        job_id = uuid.uuid4().hex[:10]
        jobs[job_id] = {"status": "queued", "logs": [], "kind": "script", "user": client_user_label(payload.get("user_id"))}
        thread = threading.Thread(target=run_script_job, args=(job_id, src, payload), daemon=True)
        thread.start()
        return jsonify({"job_id": job_id})
    except Exception as exc:
        append_server_log(f"讲稿生成失败：{exc}", "error")
        return jsonify({"error": str(exc)}), 500


@app.post("/api/preview")
def preview():
    payload = request.get_json(force=True)
    voice = payload["voice"]
    text = payload.get("text") or "大家好，这是当前音色的试听效果。"
    out = JOB_DIR / f"preview-{uuid.uuid4().hex}.mp3"
    asyncio.run(edge_tts.Communicate(text, voice=voice, rate=payload.get("rate", "-5%")).save(str(out)))
    return send_file(out, mimetype="audio/mpeg", as_attachment=False)


def run_job(job_id: str, src: Path, voice: str, rate: str, target_minutes: float, subtitle_style: str):
    job = jobs[job_id]
    out = JOB_DIR / f"{uuid.uuid4().hex}.mp4"
    cmd = [
        sys.executable,
        str(BASE_DIR / "ppt_to_video.py"),
        str(src),
        "--output",
        str(out),
        "--voice",
        voice,
        f"--rate={rate}",
        "--subtitle-style",
        subtitle_style,
    ]
    if target_minutes is not None:
        cmd.extend(["--target-minutes", str(target_minutes)])
    job["status"] = "running"
    append_log(job, "任务已启动。")
    append_server_log(f"{job_log_prefix('视频', job_id, job)} 已启动。")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    job["process"] = proc
    stdout_lines = []
    assert proc.stdout is not None
    for line in proc.stdout:
        stdout_lines.append(line)
        text = line.strip()
        if text.startswith("[progress] "):
            progress_text = text.replace("[progress] ", "", 1)
            append_log(job, progress_text)
            append_server_log(f"{job_log_prefix('视频', job_id, job)}：{progress_text}")
    stderr = proc.stderr.read() if proc.stderr else ""
    returncode = proc.wait()
    job["stdout"] = "".join(stdout_lines)
    job["stderr"] = stderr
    job.pop("process", None)
    if job.get("status") == "stopped":
        append_log(job, "视频生成已停止。", "已停止")
        append_server_log(f"{job_log_prefix('视频', job_id, job)} 已停止。")
    elif returncode == 0:
        job["status"] = "done"
        job["output"] = out.name
        job["output_download_name"] = download_name_for_upload(src, ".mp4")
        append_log(job, "视频生成完成。", "完成")
        append_server_log(f"{job_log_prefix('视频', job_id, job)} 已完成。")
    else:
        job["status"] = "error"
        append_server_log(f"{job_log_prefix('视频', job_id, job)} 子进程返回码：{returncode}", "error")
        if job["stdout"].strip():
            append_server_log(f"{job_log_prefix('视频', job_id, job)} STDOUT:\n{job['stdout'].strip()}", "error")
        if stderr:
            print(stderr, flush=True)
            first_line = stderr.strip().splitlines()[-1]
            append_log(job, first_line, "失败")
            append_server_log(f"{job_log_prefix('视频', job_id, job)} STDERR:\n{stderr.strip()}", "error")
        append_log(job, "视频生成失败。", "失败")
        append_server_log(f"{job_log_prefix('视频', job_id, job)} 失败。", "error")


@app.post("/api/generate")
def generate():
    payload = request.get_json(force=True)
    src = UPLOAD_DIR / payload["upload_id"]
    if not src.exists():
        return jsonify({"error": "上传文件不存在"}), 404
    settings = load_settings()
    subtitle_style = (payload.get("subtitle_style") or settings.get("subtitle_style") or "classic").strip()
    job_id = uuid.uuid4().hex[:10]
    jobs[job_id] = {"status": "queued", "logs": [], "kind": "video", "user": client_user_label(payload.get("user_id"))}
    thread = threading.Thread(
        target=run_job,
        args=(
            job_id,
            src,
            payload["voice"],
            payload.get("rate", "-5%"),
            float(payload["target_minutes"]) if payload.get("target_minutes") is not None else None,
            subtitle_style,
        ),
        daemon=True,
    )
    thread.start()
    return jsonify({"job_id": job_id})


@app.get("/api/jobs/<job_id>")
def job_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"status": "missing"})
    safe_job = {k: v for k, v in job.items() if k != "process"}
    return jsonify(safe_job)


@app.post("/api/jobs/<job_id>/stop")
def stop_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "任务不存在"}), 404
    proc = job.get("process")
    if proc and proc.poll() is None:
        proc.terminate()
        job["status"] = "stopped"
        append_log(job, "收到停止请求，正在终止任务。", "已停止")
    return jsonify({"status": job["status"]})


@app.get("/api/server-logs")
def get_server_logs():
    return jsonify(list(server_logs))


@app.get("/api/token-usage")
def get_token_usage():
    return jsonify(token_usage_payload())


@app.get("/api/settings")
def get_settings():
    user = client_user_label()
    return jsonify(public_settings(load_settings(), user))


@app.post("/api/settings")
def update_settings():
    payload = request.get_json(force=True)
    user = client_user_label(payload.get("user_id"))
    updates: dict = {}
    if "ai_base_url" in payload:
        updates["ai_base_url"] = payload.get("ai_base_url", "").strip().rstrip("/")
    if "ai_api_key" in payload:
        updates["ai_api_key"] = payload.get("ai_api_key", "").strip()
    if "ai_model" in payload:
        updates["ai_model"] = payload.get("ai_model", "").strip()
    if "ai_verify_ssl" in payload:
        updates["ai_verify_ssl"] = bool(payload.get("ai_verify_ssl", True))
    if "default_script_style" in payload:
        updates["default_script_style"] = payload.get("default_script_style", "").strip()
    if "subtitle_style" in payload:
        updates["subtitle_style"] = payload.get("subtitle_style", "classic").strip() or "classic"
    settings = save_user_settings(user, updates)
    append_server_log(f"AI 设置已保存（{user}）。")
    return jsonify(public_settings(load_settings(), user))


@app.post("/api/settings/test-ai")
def test_ai_settings():
    payload = request.get_json(silent=True) or {}
    user = client_user_label(payload.get("user_id"))
    stored = load_user_settings(user)
    settings = {**stored, **payload}
    if not payload.get("ai_api_key"):
        settings["ai_api_key"] = stored.get("ai_api_key", "")
    base_url = settings.get("ai_base_url", "").strip().rstrip("/")
    api_key = settings.get("ai_api_key", "").strip()
    model = settings.get("ai_model", "").strip()
    if not base_url or not api_key or not model:
        return jsonify({"ok": False, "message": "请先填写 Base URL、API Key 和 Model。"}), 400

    try:
        message = ai_chat(
            settings,
            [
                {"role": "system", "content": "你是连接测试助手。"},
                {"role": "user", "content": "请只回复 OK。"},
            ],
            temperature=0,
            log_prefix=f"AI 连接测试（{user}）",
        )
        append_server_log(f"AI 连接测试成功（{user}）。")
        return jsonify({"ok": True, "message": f"连接成功：{message[:40]}"})
    except url_error.HTTPError as exc:
        append_server_log(f"AI 连接测试失败（{user}）：HTTP {exc.code}", "error")
        return jsonify({"ok": False, "message": f"连接失败：HTTP {exc.code}。"}), 400
    except Exception as exc:
        append_server_log(f"AI 连接测试失败（{user}）：{exc}", "error")
        return jsonify({"ok": False, "message": f"连接失败：{exc}"}), 400


@app.get("/api/download/<filename>")
def download(filename: str):
    path = JOB_DIR / Path(filename).name
    download_name = request.args.get("name") or path.name
    return send_file(path, as_attachment=True, download_name=download_name)


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5050"))
    app.run(host=host, port=port, debug=True, use_reloader=False)
