#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import threading
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
        "default_script_style": "培训讲师 · 稳妥清晰",
    }


def load_settings() -> dict:
    if not SETTINGS_FILE.exists():
        return default_settings()
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return {**default_settings(), **data}
    except Exception:
        return default_settings()


def save_settings(data: dict) -> dict:
    current = load_settings()
    merged = {**current, **data}
    if data.get("ai_api_key", "") == "":
        merged["ai_api_key"] = current.get("ai_api_key", "")
    SETTINGS_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged


def public_settings(settings: dict) -> dict:
    return {
        "ai_base_url": settings.get("ai_base_url", ""),
        "ai_model": settings.get("ai_model", ""),
        "default_script_style": settings.get("default_script_style", ""),
        "has_api_key": bool(settings.get("ai_api_key")),
    }


def ai_chat(settings: dict, messages: list[dict], temperature: float = 0.4) -> str:
    base_url = settings.get("ai_base_url", "").strip().rstrip("/")
    api_key = settings.get("ai_api_key", "").strip()
    model = settings.get("ai_model", "").strip()
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
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    with url_request.urlopen(req, timeout=120, context=ssl_context) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload["choices"][0]["message"]["content"].strip()


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
    safe_name = secure_filename(file.filename) or f"upload-{uuid.uuid4().hex}.pptx"
    path = UPLOAD_DIR / f"{uuid.uuid4().hex}-{safe_name}"
    file.save(path)
    notes = extract_notes(path)
    return jsonify({
        "upload_id": path.name,
        "slides": len(notes),
        "chars": estimate_chars(notes),
        "empty_notes": sum(1 for n in notes if not n.strip()),
    })


@app.post("/api/script/analyze")
def script_analyze():
    file = request.files.get("pptx")
    if not file or not file.filename.lower().endswith(".pptx"):
        return jsonify({"error": "请上传 .pptx 文件"}), 400
    safe_name = secure_filename(file.filename) or f"upload-{uuid.uuid4().hex}.pptx"
    path = UPLOAD_DIR / f"{uuid.uuid4().hex}-{safe_name}"
    file.save(path)
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

        settings = load_settings()
        strategy = payload.get("strategy", "short")
        style = payload.get("style") or settings.get("default_script_style") or "培训讲师 · 稳妥清晰"
        enrichment = payload.get("enrichment", "light")
        write_to_ppt = bool(payload.get("write_to_ppt"))
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
                )
            scripts.append(script)
            append_server_log(f"已生成第 {idx}/{len(slide_texts)} 页讲稿。")

        output_name = None
        write_result = None
        if write_to_ppt:
            output_path = JOB_DIR / f"{src.stem}_已生成讲稿.pptx"
            write_result = write_notes_copy(src, scripts, output_path)
            output_name = output_path.name
            append_server_log(f"已生成更新备注后的 PPT：{output_name}")

        return jsonify({
            "scripts": [
                {"index": idx, "title": (slide_texts[idx - 1].splitlines() or [f'第 {idx} 页'])[0], "script": script}
                for idx, script in enumerate(scripts, start=1)
            ],
            "ppt_output": output_name,
            "write_result": write_result,
        })
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


def run_job(job_id: str, src: Path, voice: str, rate: str, target_minutes: float):
    job = jobs[job_id]
    out = JOB_DIR / f"{src.stem}-{job_id}.mp4"
    cmd = [
        sys.executable,
        str(BASE_DIR / "ppt_to_video.py"),
        str(src),
        "--output",
        str(out),
        "--voice",
        voice,
        f"--rate={rate}",
    ]
    if target_minutes is not None:
        cmd.extend(["--target-minutes", str(target_minutes)])
    job["status"] = "running"
    append_log(job, "任务已启动。")
    append_server_log(f"任务 {job_id} 已启动。")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    job["process"] = proc
    stdout_lines = []
    assert proc.stdout is not None
    for line in proc.stdout:
        stdout_lines.append(line)
        text = line.strip()
        if text.startswith("[progress] "):
            append_log(job, text.replace("[progress] ", "", 1))
    stderr = proc.stderr.read() if proc.stderr else ""
    returncode = proc.wait()
    job["stdout"] = "".join(stdout_lines)
    job["stderr"] = stderr
    job.pop("process", None)
    if job.get("status") == "stopped":
        append_log(job, "视频生成已停止。", "已停止")
        append_server_log(f"任务 {job_id} 已停止。")
    elif returncode == 0:
        job["status"] = "done"
        job["output"] = out.name
        append_log(job, "视频生成完成。", "完成")
        append_server_log(f"任务 {job_id} 已完成。")
    else:
        job["status"] = "error"
        append_server_log(f"任务 {job_id} 子进程返回码：{returncode}", "error")
        if job["stdout"].strip():
            append_server_log(f"STDOUT:\n{job['stdout'].strip()}", "error")
        if stderr:
            print(stderr, flush=True)
            first_line = stderr.strip().splitlines()[-1]
            append_log(job, first_line, "失败")
            append_server_log(f"STDERR:\n{stderr.strip()}", "error")
        append_log(job, "视频生成失败。", "失败")
        append_server_log(f"任务 {job_id} 失败。", "error")


@app.post("/api/generate")
def generate():
    payload = request.get_json(force=True)
    src = UPLOAD_DIR / payload["upload_id"]
    if not src.exists():
        return jsonify({"error": "上传文件不存在"}), 404
    job_id = uuid.uuid4().hex[:10]
    jobs[job_id] = {"status": "queued", "logs": []}
    thread = threading.Thread(
        target=run_job,
        args=(
            job_id,
            src,
            payload["voice"],
            payload.get("rate", "-5%"),
            float(payload["target_minutes"]) if payload.get("target_minutes") is not None else None,
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


@app.get("/api/settings")
def get_settings():
    return jsonify(public_settings(load_settings()))


@app.post("/api/settings")
def update_settings():
    payload = request.get_json(force=True)
    settings = save_settings({
        "ai_base_url": payload.get("ai_base_url", "").strip().rstrip("/"),
        "ai_api_key": payload.get("ai_api_key", "").strip(),
        "ai_model": payload.get("ai_model", "").strip(),
        "default_script_style": payload.get("default_script_style", "").strip(),
    })
    append_server_log("AI 设置已保存。")
    return jsonify(public_settings(settings))


@app.post("/api/settings/test-ai")
def test_ai_settings():
    payload = request.get_json(silent=True) or {}
    stored = load_settings()
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
        )
        append_server_log("AI 连接测试成功。")
        return jsonify({"ok": True, "message": f"连接成功：{message[:40]}"})
    except url_error.HTTPError as exc:
        append_server_log(f"AI 连接测试失败：HTTP {exc.code}", "error")
        return jsonify({"ok": False, "message": f"连接失败：HTTP {exc.code}。"}), 400
    except Exception as exc:
        append_server_log(f"AI 连接测试失败：{exc}", "error")
        return jsonify({"ok": False, "message": f"连接失败：{exc}"}), 400


@app.get("/api/download/<filename>")
def download(filename: str):
    path = JOB_DIR / filename
    return send_file(path, as_attachment=True)


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5050"))
    app.run(host=host, port=port, debug=True, use_reloader=False)
