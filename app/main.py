from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import pytesseract

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "350")) * 1024 * 1024
MAX_DURATION_SECONDS = int(os.getenv("MAX_DURATION_SECONDS", "900"))
MAX_FRAMES = int(os.getenv("MAX_FRAMES", "180"))
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}

app = FastAPI(title="FrameCheck", version="1.0.1", description="Free timestamped video text review")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://tanshi2003.github.io"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if os.getenv("TESSERACT_CMD"):
    pytesseract.pytesseract.tesseract_cmd = os.environ["TESSERACT_CMD"]


def tool_path(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise HTTPException(503, f"{name} is not installed on this server.")
    return found


def run_command(command: list[str], timeout: int = 120) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Video processing took too long. Try a shorter clip.")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "Unknown processing error")[-1200:]
        raise HTTPException(422, f"Video processing failed: {detail}")
    return result.stdout


def get_video_info(path: Path) -> dict[str, Any]:
    output = run_command([
        tool_path("ffprobe"), "-v", "error", "-show_entries",
        "format=duration,size:stream=codec_type,width,height",
        "-of", "json", str(path)
    ])
    try:
        info = json.loads(output)
        duration = float(info.get("format", {}).get("duration", 0))
    except (ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(422, "Could not read video metadata.")
    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
    if duration <= 0 or not video:
        raise HTTPException(422, "The file does not contain a readable video stream.")
    if duration > MAX_DURATION_SECONDS:
        raise HTTPException(413, f"Video is longer than the {MAX_DURATION_SECONDS // 60}-minute limit.")
    return {"duration": duration, "width": video.get("width"), "height": video.get("height")}


def timestamp(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def extract_frames(video_path: Path, out_dir: Path, duration: float) -> list[dict[str, Any]]:
    interval = 5.0
    expected = max(1, min(MAX_FRAMES, int(duration // interval) + 1))
    fps = 1 / interval
    run_command([
        tool_path("ffmpeg"), "-hide_banner", "-loglevel", "error", "-i", str(video_path),
        "-vf", f"fps={fps},scale='min(1600,iw)':-2",
        "-frames:v", str(expected), "-q:v", "3", str(out_dir / "frame-%04d.jpg")
    ], timeout=240)
    frames = sorted(out_dir.glob("frame-*.jpg"))
    results = []
    for index, frame in enumerate(frames):
        seconds = index * interval
        results.append({"path": frame, "seconds": seconds, "timestamp": timestamp(seconds)})
    if not results:
        raise HTTPException(422, "No frames could be extracted from this video.")
    return results


def clean_text(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip()


def analyse_text(text: str, language_tool: Any | None) -> list[dict[str, str]]:
    if not text.strip() or language_tool is None:
        return []
    findings: list[dict[str, str]] = []
    for match in language_tool.check(text):
        if match.ruleId in {"WHITESPACE_RULE", "COMMA_PARENTHESIS_WHITESPACE"}:
            continue
        findings.append({
            "category": "Grammar" if match.ruleId and ("GRAMMAR" in match.ruleId or "PUNCT" in match.ruleId) else "Spelling / style",
            "message": match.message,
            "suggestion": match.replacements[0] if match.replacements else "",
            "context": match.context or "",
            "offset": str(match.offset),
            "length": str(match.errorLength),
        })
    return findings[:80]


@app.get("/")
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "FrameCheck",
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "ffprobe": shutil.which("ffprobe") is not None,
        "tesseract": shutil.which("tesseract") is not None or bool(os.getenv("TESSERACT_CMD")),
    }


@app.post("/api/analyse")
async def analyse_video(video: UploadFile = File(...)) -> dict[str, Any]:
    filename = video.filename or "upload.mp4"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, "Please upload an MP4, MOV, M4V, WebM, MKV or AVI video.")

    with tempfile.TemporaryDirectory(prefix="framecheck-") as temp:
        work = Path(temp)
        video_path = work / f"input{suffix}"
        bytes_written = 0
        try:
            with video_path.open("wb") as destination:
                while chunk := await video.read(1024 * 1024):
                    bytes_written += len(chunk)
                    if bytes_written > MAX_UPLOAD_BYTES:
                        raise HTTPException(413, f"Video exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit.")
                    destination.write(chunk)
        finally:
            await video.close()

        if bytes_written == 0:
            raise HTTPException(400, "The uploaded file is empty.")

        video_info = get_video_info(video_path)
        frame_dir = work / "frames"
        frame_dir.mkdir()
        frames = extract_frames(video_path, frame_dir, video_info["duration"])

        if not shutil.which("tesseract") and not os.getenv("TESSERACT_CMD"):
            raise HTTPException(503, "Text recognition is unavailable because Tesseract is not installed.")

        language_tool = None
        language_check_available = False
        try:
            import language_tool_python
            language_tool = language_tool_python.LanguageTool("en-US")
            language_check_available = True
        except Exception:
            language_tool = None

        results: list[dict[str, Any]] = []
        try:
            for frame in frames:
                try:
                    with Image.open(frame["path"]) as image:
                        image = image.convert("RGB")
                        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT, config="--psm 11")
                        words = [w.strip() for w in data["text"] if w and w.strip()]
                        extracted = clean_text(" ".join(words))
                        confidence_values = []
                        for value in data.get("conf", []):
                            try:
                                score = float(value)
                                if score >= 0:
                                    confidence_values.append(score)
                            except (TypeError, ValueError):
                                continue
                        confidence = round(sum(confidence_values) / len(confidence_values), 1) if confidence_values else 0
                except Exception:
                    extracted, confidence = "", 0

                try:
                    findings = analyse_text(extracted, language_tool)
                except Exception:
                    findings = []
                results.append({
                    "timestamp": frame["timestamp"],
                    "seconds": frame["seconds"],
                    "text": extracted,
                    "confidence": confidence,
                    "findings": findings,
                })
        finally:
            if language_tool is not None:
                try:
                    language_tool.close()
                except Exception:
                    pass

        combined = clean_text(" ".join(dict.fromkeys(r["text"] for r in results if r["text"])))
        total_findings = sum(len(r["findings"]) for r in results)
        return {
            "job_id": str(uuid.uuid4()),
            "filename": Path(filename).name,
            "video": {
                "duration": video_info["duration"],
                "duration_label": timestamp(video_info["duration"]),
                "width": video_info["width"],
                "height": video_info["height"],
                "size": bytes_written,
            },
            "summary": {
                "frames_scanned": len(results),
                "frames_with_text": sum(bool(r["text"]) for r in results),
                "issues_found": total_findings,
            },
            "combined_text": combined,
            "frames": results,
            "language_check_available": language_check_available,
            "notice": "Text recognition and language suggestions are automated. Review every suggestion before changing your design.",
        }
