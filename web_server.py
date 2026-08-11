#!/usr/bin/env python3
"""Backend FastAPI cho UI custom (thay Gradio) — gọi lại orchestrator.py có sẵn.
Chạy: source web_env/bin/activate && python3 web_server.py
"""
import asyncio
import json
import shutil
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, Form, File
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import orchestrator as orch
from pipeline_config import load_config, save_config

# Dùng lại PROJECT_ROOT của orchestrator (đã tự xử lý FROZEN vs dev-mode) thay
# vì tự tính Path(__file__).resolve().parent — trong bundle PyInstaller,
# __file__ của script chính không đảm bảo trỏ đúng thư mục cài đặt thật.
PROJECT_ROOT = orch.PROJECT_ROOT
OUTPUT_DIR = PROJECT_ROOT / "outputs"
UPLOAD_DIR = OUTPUT_DIR / "_uploads"
OUTPUT_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI()
JOBS = {}
JOBS_LOCK = threading.Lock()

LANG_CHOICES = [
    ("zh-cn", "Tiếng Trung (giản thể)"),
    ("zh-tw", "Tiếng Trung (phồn thể)"),
    ("en", "Tiếng Anh"),
    ("vi", "Tiếng Việt"),
    ("ja", "Tiếng Nhật"),
    ("ko", "Tiếng Hàn"),
    ("fr", "Tiếng Pháp"),
    ("de", "Tiếng Đức"),
    ("es", "Tiếng Tây Ban Nha"),
    ("ru", "Tiếng Nga"),
    ("th", "Tiếng Thái"),
    ("it", "Tiếng Ý"),
    ("pt", "Tiếng Bồ Đào Nha"),
]
MODEL_CHOICES = ["tiny", "base", "small", "medium", "large-v3"]
# Chỉ liệt kê các mode thực sự chạy được với bộ model đã đóng gói. sttn-det/
# lama/propainter/opencv (gốc) đều cần model OCR (PP-OCRv5) để tự dò vùng —
# KHÔNG được bundle nên sẽ lỗi; bỏ khỏi UI. 3 mode dưới đây áp thẳng vào vùng
# người dùng khoanh, không cần OCR:
INPAINT_CHOICES = [
    ("lama-auto", "Xoá bằng AI (LaMa) — xoá hẳn logo/sub cố định, có thể hơi nhoè"),
    ("blur", "Làm mờ vùng — nhanh & ổn định, che chỗ logo/sub cũ"),
    ("sttn-auto", "STTN — chỉ hợp phụ đề chạy chữ, KHÔNG xoá được logo cố định"),
]
LOCALE_OVERRIDE = {"zh-cn": "zh-CN", "zh-tw": "zh-TW"}

_ALL_VOICES = []
_DEFAULT_VOICES = {
    "vi": ["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"],
    "en": ["en-US-GuyNeural", "en-US-JennyNeural"],
    "zh-cn": ["zh-CN-XiaoxiaoNeural", "zh-CN-YunyangNeural"],
}


def _fetch_all_voices():
    global _ALL_VOICES
    try:
        import edge_tts
        _ALL_VOICES = asyncio.run(edge_tts.list_voices())
    except Exception as e:
        print(f"[warn] Không tải được danh sách voice lúc khởi động: {e}")
        _ALL_VOICES = []


_fetch_all_voices()


def voices_for_lang(lang_code):
    prefix = LOCALE_OVERRIDE.get(lang_code, lang_code).lower()
    matched = [v["ShortName"] for v in _ALL_VOICES if v["Locale"].lower().startswith(prefix)]
    return matched or _DEFAULT_VOICES.get(lang_code, [])


def _log(job_id, msg):
    with JOBS_LOCK:
        JOBS[job_id]["logs"].append(msg)


def _run_job(job_id, input_video, source_lang, target_lang, model_name, voice_role,
             inpaint_mode, sub_areas, subtitle_bottom_pct):
    work_dir = OUTPUT_DIR / f"_work_{job_id}"
    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        orch.preflight_checks()

        if sub_areas:
            _log(job_id, f"[1/4] Đang xoá sub/logo cũ ({len(sub_areas)} vùng đã chọn)...")
            cleaned = orch.remove_old_subtitles(input_video, work_dir, inpaint_mode, sub_areas=sub_areas)
        else:
            _log(job_id, "[1/4] Không chọn vùng xoá sub/logo — giữ nguyên video gốc, bỏ qua bước này.")
            cleaned = orch.remove_old_subtitles(input_video, work_dir, inpaint_mode, sub_areas=None)
        _log(job_id, "✓ Xong bước 1/4")

        _log(job_id, "[2/4] Đang transcribe + dịch + dub (pyvideotrans)... "
                      "(lần đầu chạy 1 model mới sẽ mất thêm thời gian tải model)")
        dub_audio, dub_srt = orch.transcribe_translate_dub(
            input_video, work_dir, source_lang, target_lang, model_name, voice_role,
        )
        _log(job_id, "✓ Xong bước 2/4")

        # Giữ lại srt gốc (transcribe) + srt dịch để debug chất lượng transcribe/dịch —
        # work_dir sẽ bị xoá sạch ở finally nên phải copy ra OUTPUT_DIR ngay.
        raw_srt = dub_srt.parent / f"{source_lang}.srt"
        if raw_srt.exists():
            shutil.copy2(raw_srt, OUTPUT_DIR / f"{job_id}_{source_lang}_raw.srt")
        shutil.copy2(dub_srt, OUTPUT_DIR / f"{job_id}_{target_lang}_translated.srt")

        _log(job_id, "[3/4] Đang tạo lại phụ đề đúng vị trí cho video này...")
        width, height = orch.probe_resolution(cleaned)
        ass_path = orch.build_fixed_ass(dub_srt, work_dir, width, height, bottom_pct=subtitle_bottom_pct)
        _log(job_id, "✓ Xong bước 3/4")

        _log(job_id, "[4/4] Đang ghép video cuối cùng...")
        output_path = OUTPUT_DIR / f"{job_id}_{target_lang}.mp4"
        orch.compose_final(cleaned, dub_audio, ass_path, output_path)

        with JOBS_LOCK:
            JOBS[job_id]["status"] = "done"
            JOBS[job_id]["result"] = output_path.name
        _log(job_id, f"✓ Hoàn tất! File: {output_path.name}")
    except orch.PipelineStageError as e:
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "error"
        _log(job_id, f"[LỖI ở bước: {e.stage}]\n{e.detail}")
    except Exception as e:
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "error"
        _log(job_id, f"[LỖI không xác định] {e}")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        try:
            input_video.unlink(missing_ok=True)
        except Exception:
            pass


@app.get("/api/config")
def get_config():
    cfg = load_config()
    return {
        "config": cfg,
        "lang_choices": LANG_CHOICES,
        "model_choices": MODEL_CHOICES,
        "inpaint_choices": INPAINT_CHOICES,
        "voices": voices_for_lang(cfg["target_lang"]),
        "subtitle_bottom_pct": cfg.get("subtitle_bottom_pct", 15),
    }


@app.get("/api/voices")
def get_voices(lang: str):
    return {"voices": voices_for_lang(lang)}


@app.post("/api/config")
async def post_config(payload: dict):
    merged = save_config(**payload)
    return {"config": merged}


def _parse_sub_areas(raw):
    """Parse chuỗi JSON các vùng [{ymin,ymax,xmin,xmax}, ...] từ UI thành list tuple.
    Trả về [] nếu rỗng/lỗi (an toàn: coi như không chọn vùng -> bỏ qua bước xoá)."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    areas = []
    for a in data:
        try:
            ymin, ymax = sorted((int(a["ymin"]), int(a["ymax"])))
            xmin, xmax = sorted((int(a["xmin"]), int(a["xmax"])))
            if ymax - ymin >= 2 and xmax - xmin >= 2:
                areas.append((ymin, ymax, xmin, xmax))
        except (KeyError, TypeError, ValueError):
            continue
    return areas


@app.post("/api/run")
async def run_pipeline(
    video: UploadFile = File(...),
    source_lang: str = Form(...),
    target_lang: str = Form(...),
    model_name: str = Form(...),
    voice_role: str = Form(...),
    inpaint_mode: str = Form(...),
    sub_areas: str = Form(""),
    subtitle_bottom_pct: int = Form(15),
):
    job_id = uuid.uuid4().hex[:12]
    suffix = Path(video.filename or "input.mp4").suffix or ".mp4"
    saved_path = UPLOAD_DIR / f"{job_id}{suffix}"
    with saved_path.open("wb") as f:
        shutil.copyfileobj(video.file, f)

    parsed_areas = _parse_sub_areas(sub_areas)
    bottom_pct = max(0, min(int(subtitle_bottom_pct), 45))

    JOBS[job_id] = {"logs": [], "status": "running", "result": None}
    thread = threading.Thread(
        target=_run_job,
        args=(job_id, saved_path, source_lang, target_lang, model_name, voice_role,
              inpaint_mode, parsed_areas, bottom_pct),
        daemon=True,
    )
    thread.start()
    return {"job_id": job_id}


@app.get("/api/progress/{job_id}")
async def progress(job_id: str):
    async def event_stream():
        sent = 0
        while True:
            with JOBS_LOCK:
                job = JOBS.get(job_id)
                if job is None:
                    yield f"event: error\ndata: job không tồn tại\n\n"
                    return
                logs = list(job["logs"])
                status = job["status"]
                result = job["result"]
            while sent < len(logs):
                yield f"data: {json.dumps({'log': logs[sent]})}\n\n"
                sent += 1
            if status in ("done", "error"):
                yield f"event: {status}\ndata: {json.dumps({'result': result})}\n\n"
                return
            await asyncio.sleep(0.4)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/outputs/{filename}")
def get_output(filename: str):
    path = OUTPUT_DIR / filename
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    media_type = "video/mp4" if path.suffix == ".mp4" else "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=filename)


app.mount("/", StaticFiles(directory=PROJECT_ROOT / "web_static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn

    if orch.FROZEN:
        # Bản đóng gói chạy như 1 app double-click, không có terminal để đọc
        # URL — tự mở browser cho người dùng.
        import threading
        import webbrowser
        threading.Timer(1.0, lambda: webbrowser.open("http://127.0.0.1:7860")).start()

    uvicorn.run(app, host="127.0.0.1", port=7860)
