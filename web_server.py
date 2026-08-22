#!/usr/bin/env python3
"""Backend FastAPI cho UI custom (thay Gradio) — gọi lại orchestrator.py có sẵn.
Chạy: source web_env/bin/activate && python3 web_server.py
"""
import asyncio
import json
import shutil
import subprocess
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

# Thư viện giọng clone: mỗi giọng có tên + file wav mẫu + lời thoại (đã transcribe
# 1 lần). Lưu bền, dùng lại như preset trong dropdown -> khỏi upload/nhận diện lại
# mỗi lần làm video (chỉ phần F5 đọc từng câu là vẫn phải chạy theo từng video).
CLONE_DIR = PROJECT_ROOT / "clone_voices"
CLONE_DIR.mkdir(exist_ok=True)
CLONE_REGISTRY = CLONE_DIR / "voices.json"


def load_clone_voices():
    if CLONE_REGISTRY.exists():
        try:
            return json.loads(CLONE_REGISTRY.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_clone_voices(d):
    CLONE_REGISTRY.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


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
             inpaint_mode, sub_areas, subtitle_bottom_pct, sub_box,
             tts_engine, ref_audio_path, ref_text, el=None):
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
        # Ở chế độ clone, pyvideotrans vẫn phải dub Edge-TTS (ta sẽ thay bằng F5
        # sau) -> voice_role truyền cho nó PHẢI là giọng Edge hợp lệ, KHÔNG phải
        # tên giọng clone ("Voice Clone 1" không tồn tại trong Edge-TTS -> lỗi).
        pvt_voice = voice_role
        if tts_engine in ("f5clone", "elevenlabs"):
            _vs = voices_for_lang(target_lang)
            pvt_voice = _vs[0] if _vs else "vi-VN-HoaiMyNeural"
        dub_audio, dub_srt = orch.transcribe_translate_dub(
            input_video, work_dir, source_lang, target_lang, model_name, pvt_voice, tts_type="0",
        )
        _log(job_id, "✓ Xong bước 2/4")

        # Giữ lại srt gốc (transcribe) + srt dịch để debug chất lượng transcribe/dịch —
        # work_dir sẽ bị xoá sạch ở finally nên phải copy ra OUTPUT_DIR ngay.
        raw_srt = dub_srt.parent / f"{source_lang}.srt"
        if raw_srt.exists():
            shutil.copy2(raw_srt, OUTPUT_DIR / f"{job_id}_{source_lang}_raw.srt")
        shutil.copy2(dub_srt, OUTPUT_DIR / f"{job_id}_{target_lang}_translated.srt")

        # Nếu chọn clone giọng: thay bản dub Edge-TTS bằng giọng clone F5 theo
        # đúng timing của srt dịch (pyvideotrans vẫn lo transcribe+dịch ở trên).
        # Clone giọng: giọng đọc tự nhiên (dài hơn timing gốc) -> dùng srt MỚI do
        # F5 xuất ra (theo đúng vị trí audio) cho phụ đề + kéo giãn video cho khớp.
        ass_srt = dub_srt
        stretch_video = False
        if tts_engine == "f5clone" and ref_audio_path:
            rtext = ref_text
            if not rtext:
                _log(job_id, "    → Đang nhận diện lời thoại của giọng mẫu...")
                rtext = orch.transcribe_audio(ref_audio_path) or ""
            _log(job_id, "    → Đang tạo giọng CLONE bằng F5-TTS (có thể lâu, tuỳ độ dài & phần cứng)...")
            dub_audio, clone_srt = orch.synthesize_clone_dub(dub_srt, ref_audio_path, rtext, work_dir)
            if clone_srt:
                ass_srt = clone_srt
            stretch_video = True
            _log(job_id, "    ✓ Xong giọng clone")
        elif tts_engine == "elevenlabs" and el:
            _log(job_id, "    → Đang tạo giọng ElevenLabs (gọi 1 lần cả bài, chống lệch ngữ điệu)...")
            dub_audio, el_srt = orch.synthesize_elevenlabs_dub(dub_srt, el[0], el[1], el[2], work_dir)
            if el_srt:
                ass_srt = el_srt
            stretch_video = True
            _log(job_id, "    ✓ Xong giọng ElevenLabs")

        _log(job_id, "[3/4] Đang tạo lại phụ đề đúng vị trí cho video này...")
        width, height = orch.probe_resolution(cleaned)
        if sub_box:
            _log(job_id, f"    → Đặt phụ đề mới vào ô che sub {sub_box} (tự co cỡ chữ)")
        ass_path = orch.build_fixed_ass(
            ass_srt, work_dir, width, height,
            bottom_pct=subtitle_bottom_pct, sub_box=sub_box,
        )
        _log(job_id, "✓ Xong bước 3/4")

        _log(job_id, "[4/4] Đang ghép video cuối cùng...")
        output_path = OUTPUT_DIR / f"{job_id}_{target_lang}.mp4"
        orch.compose_final(cleaned, dub_audio, ass_path, output_path, stretch_video=stretch_video)

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
        # KHÔNG xoá ref_audio_path: đó là file giọng trong thư viện (dùng lại nhiều lần).


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
        "clone_voices": list(load_clone_voices().keys()),
    }


@app.post("/api/clone-voices")
async def add_clone_voice(name: str = Form(...), ref_audio: UploadFile = File(...)):
    """Thêm 1 giọng clone mới: lưu file mẫu (convert wav mono 24k) + transcribe 1
    lần, cất vào thư viện để chọn lại như preset."""
    name = name.strip()
    if not name:
        return JSONResponse({"error": "Thiếu tên giọng"}, status_code=400)
    voices = load_clone_voices()
    slug = uuid.uuid4().hex[:8]
    wav = CLONE_DIR / f"{slug}.wav"
    raw = CLONE_DIR / f"{slug}_raw{Path(ref_audio.filename or '').suffix or '.m4a'}"
    with raw.open("wb") as f:
        shutil.copyfileobj(ref_audio.file, f)
    # CẮT xuống ~14s (bỏ 1.5s đầu tránh nhạc/intro). F5 chỉ dùng ref ngắn ~10-15s;
    # nếu để file dài (vài phút) F5 loạn -> sinh tiếng lặp vô nghĩa (lỗi đã gặp).
    subprocess.run(
        [orch.FFMPEG_BIN, "-y", "-ss", "1.5", "-t", "14", "-i", str(raw),
         "-ac", "1", "-ar", "24000", str(wav)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    raw.unlink(missing_ok=True)
    text = orch.transcribe_audio(wav) or ""   # nhận diện lời thoại (chỉ đoạn 14s)
    voices[name] = {"file": str(wav), "text": text}
    save_clone_voices(voices)
    return {"clone_voices": list(voices.keys())}


@app.delete("/api/clone-voices/{name}")
async def delete_clone_voice(name: str):
    voices = load_clone_voices()
    v = voices.pop(name, None)
    if v:
        try:
            Path(v["file"]).unlink(missing_ok=True)
        except Exception:
            pass
        save_clone_voices(voices)
    return {"clone_voices": list(voices.keys())}


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
    place_sub_in_region: bool = Form(False),
    sub_box: str = Form(""),
    tts_engine: str = Form("edge"),
    el_api_key: str = Form(""),
    el_voice_id: str = Form(""),
    el_model: str = Form("eleven_multilingual_v2"),
):
    job_id = uuid.uuid4().hex[:12]
    suffix = Path(video.filename or "input.mp4").suffix or ".mp4"
    saved_path = UPLOAD_DIR / f"{job_id}{suffix}"
    with saved_path.open("wb") as f:
        shutil.copyfileobj(video.file, f)

    parsed_areas = _parse_sub_areas(sub_areas)
    bottom_pct = max(0, min(int(subtitle_bottom_pct), 45))
    # Khối "đặt sub" riêng (che sub cũ + sub mới đè lên). Nếu rỗng -> chỉ blur, sub ở đáy.
    _pb = _parse_sub_areas(f"[{sub_box}]") if sub_box.strip() else []
    parsed_box = _pb[0] if _pb else None

    # Chế độ clone giọng: voice_role là TÊN giọng đã lưu trong thư viện -> tra ra
    # file mẫu + lời thoại (đã transcribe sẵn lúc thêm giọng), khỏi upload lại.
    ref_wav = None
    ref_text = ""
    if tts_engine == "f5clone":
        v = load_clone_voices().get(voice_role)
        if v and Path(v["file"]).exists():
            ref_wav = v["file"]
            ref_text = v.get("text", "")

    # ElevenLabs: ghi API key + voice_id vào config pyvideotrans -> dùng tts_type 22.
    el = None
    if tts_engine == "elevenlabs" and el_api_key.strip() and el_voice_id.strip():
        el = (el_api_key.strip(), el_voice_id.strip(), el_model.strip() or "eleven_multilingual_v2")

    JOBS[job_id] = {"logs": [], "status": "running", "result": None}
    thread = threading.Thread(
        target=_run_job,
        args=(job_id, saved_path, source_lang, target_lang, model_name, voice_role,
              inpaint_mode, parsed_areas, bottom_pct, parsed_box,
              tts_engine, ref_wav, ref_text, el),
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
