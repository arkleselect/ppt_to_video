#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import threading
import uuid
from datetime import datetime
from collections import deque
from pathlib import Path

import edge_tts
from flask import Flask, jsonify, request, send_file
from werkzeug.utils import secure_filename

from ppt_to_video import estimate_chars, extract_notes


BASE_DIR = Path(__file__).parent.resolve()
STORAGE_DIR = BASE_DIR / "storage"
UPLOAD_DIR = STORAGE_DIR / "uploads"
JOB_DIR = STORAGE_DIR / "jobs"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
JOB_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
jobs: dict[str, dict] = {}
server_logs: deque[dict] = deque(maxlen=300)


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
        "python3",
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
        if stderr:
            print(stderr, flush=True)
            first_line = stderr.strip().splitlines()[-1]
            append_log(job, first_line, "失败")
            append_server_log(stderr.strip(), "error")
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


@app.get("/api/download/<filename>")
def download(filename: str):
    path = JOB_DIR / filename
    return send_file(path, as_attachment=True)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=True, use_reloader=False)
