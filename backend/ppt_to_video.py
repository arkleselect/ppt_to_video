#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import math
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import edge_tts
from mutagen.mp3 import MP3

try:
    import fitz
except ImportError:
    fitz = None


NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}

ET.register_namespace("a", NS["a"])
ET.register_namespace("p", NS["p"])
ET.register_namespace("r", NS["r"])


def run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def libreoffice_user_installation_arg(profile_dir: Path) -> str:
    profile_dir.mkdir(parents=True, exist_ok=True)
    return f"-env:UserInstallation={profile_dir.resolve().as_uri()}"


def convert_pptx_to_pdf(soffice: str, pptx_path: Path, pdf_dir: Path, out_dir: Path) -> Path:
    pdf_path = pdf_dir / f"{pptx_path.stem}.pdf"
    last_error: subprocess.CalledProcessError | None = None

    for attempt in range(1, 4):
        profile_dir = out_dir / f"lo_profile_{attempt}"
        if profile_dir.exists():
            shutil.rmtree(profile_dir, ignore_errors=True)

        cmd = [
            soffice,
            libreoffice_user_installation_arg(profile_dir),
            "--headless",
            "--nologo",
            "--nofirststartwizard",
            "--nolockcheck",
            "--convert-to",
            "pdf:impress_pdf_Export",
            "--outdir",
            str(pdf_dir),
            str(pptx_path),
        ]

        try:
            run(cmd)
        except subprocess.CalledProcessError as exc:
            last_error = exc
            print(f"[progress] LibreOffice 导出 PDF 失败，准备重试 {attempt}/3", flush=True)
            time.sleep(attempt)
            continue

        if pdf_path.exists() and pdf_path.stat().st_size > 0:
            return pdf_path

        print(f"[progress] LibreOffice 未生成有效 PDF，准备重试 {attempt}/3", flush=True)
        time.sleep(attempt)

    if last_error:
        raise last_error
    raise RuntimeError("LibreOffice 导出 PDF 失败：未生成有效 PDF 文件。")


def ffmpeg_subtitles_filter(path: Path) -> str:
    # `subtitles` filter treats `:` as an option separator, so Windows drive
    # letters like `C:/...` must be escaped before being passed to ffmpeg.
    normalized = str(path.resolve()).replace("\\", "/")
    escaped = (
        normalized
        .replace("\\", r"\\")
        .replace(":", r"\:")
        .replace("'", r"\'")
        .replace(",", r"\,")
        .replace("[", r"\[")
        .replace("]", r"\]")
    )
    return f"subtitles=filename='{escaped}'"


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if path:
        return path
    raise FileNotFoundError(f"缺少系统命令：{name}。请确认已安装，并已加入 PATH。")


def find_tool(name: str) -> str | None:
    return shutil.which(name)


def natural_key(path: str) -> list[object]:
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", path)]


def read_xml(zf: zipfile.ZipFile, name: str) -> ET.Element:
    return ET.fromstring(zf.read(name))


def extract_notes(pptx_path: Path) -> list[str]:
    with zipfile.ZipFile(pptx_path) as zf:
        names = set(zf.namelist())
        presentation = read_xml(zf, "ppt/presentation.xml")
        pres_rels = read_xml(zf, "ppt/_rels/presentation.xml.rels")

        rel_map = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in pres_rels.findall("rel:Relationship", NS)
        }

        notes: list[str] = []
        slide_ids = presentation.findall("p:sldIdLst/p:sldId", NS)
        for idx, sld_id in enumerate(slide_ids, start=1):
            slide_target = rel_map[sld_id.attrib[f"{{{NS['r']}}}id"]]
            slide_path = f"ppt/{slide_target}".replace("ppt/slides/../", "ppt/")
            slide_name = Path(slide_path).name
            slide_rels_path = f"ppt/slides/_rels/{slide_name}.rels"

            note_text = ""
            if slide_rels_path in names:
                slide_rels = read_xml(zf, slide_rels_path)
                for rel in slide_rels.findall("rel:Relationship", NS):
                    if rel.attrib.get("Type", "").endswith("/notesSlide"):
                        target = rel.attrib["Target"]
                        note_path = f"ppt/slides/{target}"
                        note_path = note_path.replace("ppt/slides/../", "ppt/")
                        note_root = read_xml(zf, note_path)
                        chunks = [
                            t.text.strip()
                            for t in note_root.findall(".//a:t", NS)
                            if t.text and t.text.strip()
                        ]
                        note_text = clean_note_text(chunks)
                        break
            notes.append(note_text)
            print(f"[progress] 提取备注 {idx}/{len(slide_ids)}", flush=True)
        return notes


def slide_paths_in_order(zf: zipfile.ZipFile) -> list[str]:
    presentation = read_xml(zf, "ppt/presentation.xml")
    pres_rels = read_xml(zf, "ppt/_rels/presentation.xml.rels")
    rel_map = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in pres_rels.findall("rel:Relationship", NS)
    }
    paths: list[str] = []
    for sld_id in presentation.findall("p:sldIdLst/p:sldId", NS):
        slide_target = rel_map[sld_id.attrib[f"{{{NS['r']}}}id"]]
        paths.append(f"ppt/{slide_target}".replace("ppt/slides/../", "ppt/"))
    return paths


def extract_slide_texts(pptx_path: Path) -> list[str]:
    with zipfile.ZipFile(pptx_path) as zf:
        texts: list[str] = []
        for slide_path in slide_paths_in_order(zf):
            root = read_xml(zf, slide_path)
            chunks = [
                t.text.strip()
                for t in root.findall(".//a:t", NS)
                if t.text and t.text.strip()
            ]
            texts.append("\n".join(chunks))
        return texts


def find_notes_paths(zf: zipfile.ZipFile) -> list[str | None]:
    names = set(zf.namelist())
    paths: list[str | None] = []
    for slide_path in slide_paths_in_order(zf):
        slide_name = Path(slide_path).name
        slide_rels_path = f"ppt/slides/_rels/{slide_name}.rels"
        note_path = None
        if slide_rels_path in names:
            slide_rels = read_xml(zf, slide_rels_path)
            for rel in slide_rels.findall("rel:Relationship", NS):
                if rel.attrib.get("Type", "").endswith("/notesSlide"):
                    target = rel.attrib["Target"]
                    note_path = f"ppt/slides/{target}".replace("ppt/slides/../", "ppt/")
                    break
        paths.append(note_path)
    return paths


def set_text_body(tx_body: ET.Element, text: str) -> None:
    for child in list(tx_body):
        if child.tag == f"{{{NS['a']}}}p":
            tx_body.remove(child)
    for line in [line for line in text.splitlines() if line.strip()] or [text]:
        paragraph = ET.SubElement(tx_body, f"{{{NS['a']}}}p")
        run = ET.SubElement(paragraph, f"{{{NS['a']}}}r")
        ET.SubElement(run, f"{{{NS['a']}}}rPr", {"lang": "zh-CN", "dirty": "0"})
        node = ET.SubElement(run, f"{{{NS['a']}}}t")
        node.text = line.strip()


def update_note_root(note_root: ET.Element, text: str) -> bool:
    shapes = note_root.findall(".//p:sp", NS)
    candidates = []
    for shape in shapes:
        ph = shape.find(".//p:ph", NS)
        tx_body = shape.find("p:txBody", NS)
        if tx_body is None:
            continue
        if ph is not None and ph.attrib.get("type") == "body":
            set_text_body(tx_body, text)
            return True
        candidates.append(tx_body)
    if candidates:
        set_text_body(candidates[0], text)
        return True
    return False


def write_notes_copy(pptx_path: Path, scripts: list[str], output_path: Path) -> dict:
    updated = 0
    missing = 0
    with zipfile.ZipFile(pptx_path, "r") as zin:
        note_paths = find_notes_paths(zin)
        replacements: dict[str, bytes] = {}
        for idx, note_path in enumerate(note_paths):
            if idx >= len(scripts):
                break
            if not note_path:
                missing += 1
                continue
            note_root = read_xml(zin, note_path)
            if update_note_root(note_root, scripts[idx]):
                replacements[note_path] = ET.tostring(note_root, encoding="utf-8", xml_declaration=True)
                updated += 1
            else:
                missing += 1

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = replacements.get(item.filename)
                zout.writestr(item, data if data is not None else zin.read(item.filename))
    return {"updated": updated, "missing": missing}


def clean_note_text(chunks: list[str]) -> str:
    cleaned: list[str] = []
    for chunk in chunks:
        text = chunk.strip()
        if not text:
            continue
        if re.fullmatch(r"\d{1,2}\.\d{1,2}\.\d{4}", text):
            continue
        if text in {"‹#›", "<#>"}:
            continue
        cleaned.append(text)
    return "\n".join(cleaned)


def render_pdf_with_pymupdf(pdf_path: Path, img_dir: Path) -> list[Path]:
    if fitz is None:
        raise FileNotFoundError(
            "缺少系统命令：pdftoppm，且未安装 Python 依赖 PyMuPDF。"
            "请安装 poppler 并加入 PATH，或执行 `pip install -r backend/requirements.txt`。"
        )

    slides: list[Path] = []
    with fitz.open(pdf_path) as pdf:
        for idx, page in enumerate(pdf, start=1):
            out_path = img_dir / f"slide-{idx}.png"
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            pix.save(out_path)
            slides.append(out_path)
            print(f"[progress] 渲染幻灯片图片 {idx}/{len(pdf)}", flush=True)
    return slides


def export_slides(pptx_path: Path, out_dir: Path) -> list[Path]:
    pdf_dir = out_dir / "pdf"
    img_dir = out_dir / "slides"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    img_dir.mkdir(parents=True, exist_ok=True)

    soffice = require_tool("soffice")
    pdftoppm = find_tool("pdftoppm")
    pdf_path = convert_pptx_to_pdf(soffice, pptx_path, pdf_dir, out_dir)
    print("[progress] 已导出 PDF，开始渲染幻灯片图片", flush=True)
    if pdftoppm:
        run([pdftoppm, "-png", str(pdf_path), str(img_dir / "slide")])
        slides = sorted(img_dir.glob("slide-*.png"), key=lambda p: natural_key(p.name))
    else:
        print("[progress] 未找到 pdftoppm，改用 PyMuPDF 渲染 PDF", flush=True)
        slides = render_pdf_with_pymupdf(pdf_path, img_dir)
    print(f"[progress] 幻灯片图片渲染完成，共 {len(slides)} 页", flush=True)
    return slides


async def synthesize_one(text: str, out_path: Path, voice: str, rate: str) -> None:
    fallback = "本页暂无备注。"
    communicate = edge_tts.Communicate(text or fallback, voice=voice, rate=rate)
    await communicate.save(str(out_path))


def ticks_to_seconds(ticks: int) -> float:
    return ticks / 10_000_000


def merge_word_boundaries(boundaries: list[dict]) -> list[dict]:
    if not boundaries:
        return []

    merged: list[dict] = []
    buffer_text = ""
    buffer_start = None
    buffer_end = None

    def flush() -> None:
        nonlocal buffer_text, buffer_start, buffer_end
        text = re.sub(r"\s+", "", buffer_text)
        if text and buffer_start is not None and buffer_end is not None:
            merged.append({
                "start": buffer_start,
                "end": buffer_end,
                "text": text,
            })
        buffer_text = ""
        buffer_start = None
        buffer_end = None

    for boundary in boundaries:
        text = boundary["text"]
        start = boundary["start"]
        end = boundary["end"]
        compact = re.sub(r"\s+", "", text)
        if not compact:
            continue

        if buffer_start is None:
            buffer_start = start
        buffer_end = end
        buffer_text += compact

        compact_len = len(re.sub(r"\s+", "", buffer_text))
        if re.search(r"[。！？!?；;：:]", compact):
            flush()
            continue
        if compact_len >= 18 and re.search(r"[，、,）)]$", compact):
            flush()
            continue
        if compact_len >= 26:
            flush()

    flush()
    return merged


async def synthesize_one_with_boundaries(
    text: str,
    out_path: Path,
    voice: str,
    rate: str,
) -> list[dict]:
    fallback = "本页暂无备注。"
    communicate = edge_tts.Communicate(
        text or fallback,
        voice=voice,
        rate=rate,
        boundary="WordBoundary",
    )
    word_boundaries: list[dict] = []
    with open(out_path, "wb") as audio:
        async for message in communicate.stream():
            if message["type"] == "audio":
                audio.write(message["data"])
            elif message["type"] == "WordBoundary":
                word_boundaries.append({
                    "start": ticks_to_seconds(message["offset"]),
                    "end": ticks_to_seconds(message["offset"] + message["duration"]),
                    "text": message["text"],
                })
    return merge_word_boundaries(word_boundaries)


async def synthesize_all(
    notes: list[str],
    out_dir: Path,
    voice: str,
    rate: str,
) -> tuple[list[Path], list[list[dict]]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    boundaries_by_page: list[list[dict]] = []
    for idx, note in enumerate(notes, start=1):
        path = out_dir / f"{idx:03d}.mp3"
        boundaries = await synthesize_one_with_boundaries(note, path, voice, rate)
        paths.append(path)
        boundaries_by_page.append(boundaries)
        print(f"[progress] 生成音频 {idx}/{len(notes)}", flush=True)
    return paths, boundaries_by_page


def duration(path: Path) -> float:
    return MP3(path).info.length


def subtitle_styles() -> dict[str, str]:
    return {
        "classic": "Default,Noto Sans CJK SC,44,&H00FFFFFF,&H000000FF,&H00282828,&H00000000,0,0,0,0,100,100,0,0,1,2.4,0,2,72,72,38,1",
        "bold": "Default,Noto Sans CJK SC,50,&H00FFFFFF,&H000000FF,&H00141414,&H00000000,1,0,0,0,100,100,0,0,1,3.8,0,2,64,64,40,1",
        "minimal": "Default,Noto Sans CJK SC,40,&H00F2F2F2,&H000000FF,&H001A1A1A,&H00000000,0,0,0,0,100,100,0,0,1,1.2,0,2,84,84,34,1",
    }


def ass_time(seconds: float) -> str:
    total_cs = max(0, int(round(seconds * 100)))
    hours = total_cs // 360000
    minutes = (total_cs % 360000) // 6000
    secs = (total_cs % 6000) // 100
    centis = total_cs % 100
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def wrap_subtitle_text(text: str, max_chars: int = 22) -> str:
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return "本页暂无备注。"
    lines = [compact[i:i + max_chars] for i in range(0, len(compact), max_chars)]
    if len(lines) > 2:
        midpoint = math.ceil(len(compact) / 2)
        midpoint = min(max_chars, max(1, midpoint))
        lines = [compact[:midpoint], compact[midpoint:midpoint + max_chars]]
    return r"\N".join(line for line in lines if line)


def write_ass_subtitles(
    notes: list[str],
    page_durations: list[float],
    boundaries_by_page: list[list[dict]],
    output_path: Path,
    style_name: str,
) -> None:
    style = subtitle_styles().get(style_name, subtitle_styles()["classic"])
    lead_in = 0.35
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1920",
        "PlayResY: 1080",
        "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        f"Style: {style}",
        "",
        "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]
    elapsed = 0.0
    for note, page_duration, boundaries in zip(notes, page_durations, boundaries_by_page):
        page_start = elapsed
        elapsed += page_duration
        if boundaries:
            for boundary in boundaries:
                start_seconds = max(0.0, boundary["start"] - lead_in)
                end_seconds = min(page_duration, max(start_seconds + 0.18, boundary["end"]))
                start = ass_time(page_start + start_seconds)
                end = ass_time(page_start + end_seconds)
                text = wrap_subtitle_text(boundary["text"]).replace("{", r"\{").replace("}", r"\}")
                lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")
        else:
            start = ass_time(page_start)
            end = ass_time(page_start + page_duration)
            text = wrap_subtitle_text(note).replace("{", r"\{").replace("}", r"\}")
            lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def build_video(
    slides: list[Path],
    audios: list[Path],
    notes: list[str],
    boundaries_by_page: list[list[dict]],
    output_path: Path,
    target_minutes: float | None,
    subtitle_style: str,
) -> tuple[float, float]:
    raw_durations = [duration(p) for p in audios]
    natural_total = sum(raw_durations)
    target_total = (target_minutes or 0) * 60
    extra = max(0.0, target_total - natural_total)
    pad_each = extra / len(slides) if slides else 0.0
    page_durations = [raw_duration + pad_each for raw_duration in raw_durations]

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        concat_file = work / "concat.txt"
        subtitle_file = work / "subtitles.ass"
        video_parts: list[Path] = []
        merged_video = work / "merged.mp4"

        for idx, (slide, audio, page_duration) in enumerate(zip(slides, audios, page_durations), start=1):
            part = work / f"page_{idx:03d}.mp4"
            padded_audio = work / f"audio_{idx:03d}.mp3"

            run([
                "ffmpeg", "-loglevel", "error", "-y",
                "-i", str(audio),
                "-af", f"apad=pad_dur={pad_each:.3f}",
                "-t", f"{page_duration:.3f}",
                str(padded_audio),
            ])
            run([
                "ffmpeg", "-loglevel", "error", "-y",
                "-framerate", "1",
                "-loop", "1",
                "-i", str(slide),
                "-i", str(padded_audio),
                "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-tune", "stillimage",
                "-r", "1",
                "-c:a", "aac",
                "-b:a", "192k",
                "-pix_fmt", "yuv420p",
                "-shortest",
                "-t", f"{page_duration:.3f}",
                str(part),
            ])
            video_parts.append(part)
            print(f"[progress] 合成页面视频 {idx}/{len(slides)}", flush=True)

        concat_file.write_text("".join(f"file '{p}'\n" for p in video_parts), encoding="utf-8")
        run([
            "ffmpeg", "-loglevel", "error", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(merged_video),
        ])
        print("[progress] 已完成最终视频拼接", flush=True)
        write_ass_subtitles(notes, page_durations, boundaries_by_page, subtitle_file, subtitle_style)
        print("[progress] 已生成字幕文件，开始压制字幕", flush=True)
        run([
            "ffmpeg", "-loglevel", "error", "-y",
            "-i", str(merged_video),
            "-vf", ffmpeg_subtitles_filter(subtitle_file),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-c:a", "copy",
            str(output_path),
        ])
        print("[progress] 已完成字幕压制", flush=True)
    return natural_total, natural_total + extra


def estimate_chars(notes: list[str]) -> int:
    return sum(len(re.sub(r"\s+", "", note)) for note in notes)


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert PPT speaker notes into a narrated Chinese video.")
    parser.add_argument("pptx", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--target-minutes", type=float, default=None)
    parser.add_argument("--voice", default="zh-CN-XiaoxiaoNeural")
    parser.add_argument("--rate", default="-5%")
    parser.add_argument("--subtitle-style", default="classic")
    args = parser.parse_args()

    pptx_path = args.pptx.expanduser().resolve()
    if not pptx_path.exists():
        print(f"找不到文件：{pptx_path}", file=sys.stderr)
        return 1
    if pptx_path.stat().st_size < 1024:
        print("这个文件太小，不像真正的 PPTX；请确认不是 Office 临时文件。", file=sys.stderr)
        return 2

    output_path = (args.output or pptx_path.with_suffix(".mp4")).expanduser().resolve()
    work_dir = pptx_path.parent / f"{pptx_path.stem}_build"
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)

    notes = extract_notes(pptx_path)
    if not notes:
        print("没有提取到幻灯片。", file=sys.stderr)
        return 3

    char_count = estimate_chars(notes)
    print(f"共 {len(notes)} 页，备注总字数约 {char_count}。")
    if any(not n.strip() for n in notes):
        missing = sum(1 for n in notes if not n.strip())
        print(f"其中 {missing} 页没有备注，将使用占位语音。")

    slides = export_slides(pptx_path, work_dir)
    if len(slides) != len(notes):
        print(f"警告：导出图片 {len(slides)} 张，备注 {len(notes)} 页。", file=sys.stderr)

    audios, boundaries_by_page = asyncio.run(synthesize_all(notes, work_dir / "audio", args.voice, args.rate))
    natural_total, final_total = build_video(
        slides,
        audios,
        notes,
        boundaries_by_page,
        output_path,
        args.target_minutes,
        args.subtitle_style,
    )
    print(f"自然配音时长：{natural_total / 60:.2f} 分钟")
    print(f"最终视频时长：{final_total / 60:.2f} 分钟")
    print(f"输出完成：{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
