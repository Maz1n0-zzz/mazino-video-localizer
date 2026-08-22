#!/usr/bin/env python3
"""
Phase 2 orchestrator: video-subtitle-remover (xoa sub/logo cu) -> pyvideotrans
(transcribe + dich + dub) -> tu ghep sub moi dung vi tri + audio dub vao video.

Khong dung buoc "burn hard-sub" noi bo cua pyvideotrans vi no luon gan
PlayResX/PlayResY co dinh 384x288 khi tu sinh .ass tu .srt, gay sai vi tri/
kich thuoc chu tren video khong chuan 4:3 (da xac nhan bang test tay Phase 1).
Script nay tu tao .ass voi PlayRes = do phan giai video thuc, roi ghep bang
1 lenh ffmpeg rieng, de sau nay de cam them buoc overlay logo moi.

Usage:
    python3 orchestrator.py --input <video> --source-lang zh-cn --target-lang vi
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from pipeline_config import load_config, save_config

# Frozen = đang chạy từ bundle PyInstaller (.exe Windows đóng gói sẵn model+ffmpeg).
# Dev = đang chạy trực tiếp bằng Python từ source, gọi vào venv riêng của từng vendor.
FROZEN = getattr(sys, "frozen", False)

if FROZEN:
    # Layout do Inno Setup dựng: <install_dir>/{web_server.exe, pyvideotrans/, vsr/, ffmpeg/}
    INSTALL_ROOT = Path(sys.executable).resolve().parent
    VSR_DIR = INSTALL_ROOT / "vsr"
    PVT_DIR = INSTALL_ROOT / "pyvideotrans"
    VSR_CMD_BASE = [str(VSR_DIR / "vsr_cli.exe")]
    PVT_CMD_BASE = [str(PVT_DIR / "pyvideotrans_cli.exe")]
    FFMPEG_BIN = str(INSTALL_ROOT / "ffmpeg" / "ffmpeg.exe")
    FFPROBE_BIN = str(INSTALL_ROOT / "ffmpeg" / "ffprobe.exe")
    PROJECT_ROOT = INSTALL_ROOT
    # pyvideotrans tự thêm ffmpeg/ riêng của nó vào PATH nhưng fallback sang PATH hệ
    # thống nếu rỗng — ta không copy ffmpeg vào đó, chỉ cần đưa ffmpeg chung vào PATH
    # kế thừa cho subprocess con (vsr_cli.exe/pyvideotrans_cli.exe).
    import os
    os.environ["PATH"] = str(INSTALL_ROOT / "ffmpeg") + os.pathsep + os.environ.get("PATH", "")
else:
    PROJECT_ROOT = Path(__file__).resolve().parent
    VSR_DIR = PROJECT_ROOT / "vendor" / "video-subtitle-remover"
    PVT_DIR = PROJECT_ROOT / "vendor" / "pyvideotrans"
    if sys.platform == "win32":
        VSR_PY = VSR_DIR / "videoEnv" / "Scripts" / "python.exe"
        PVT_PY = PVT_DIR / ".venv" / "Scripts" / "python.exe"
    else:
        VSR_PY = VSR_DIR / "videoEnv" / "bin" / "python"
        PVT_PY = PVT_DIR / ".venv" / "bin" / "python3"
    VSR_CMD_BASE = [str(VSR_PY), "-m", "backend.main"]
    PVT_CMD_BASE = [str(PVT_PY), "cli.py"]
    FFMPEG_BIN = "ffmpeg"
    FFPROBE_BIN = "ffprobe"

# --- F5-TTS voice clone (chạy trong f5env riêng, cô lập khỏi venv pyvideotrans) ---
F5_CLONE_SCRIPT = PROJECT_ROOT / "f5_clone.py"
if FROZEN:
    F5_PY = INSTALL_ROOT / "f5" / "python.exe"
    F5_MODEL_DIR = INSTALL_ROOT / "f5" / "models" / "f5-vi"
else:
    if sys.platform == "win32":
        F5_PY = PROJECT_ROOT / "f5env" / "Scripts" / "python.exe"
    else:
        F5_PY = PROJECT_ROOT / "f5env" / "bin" / "python"
    F5_MODEL_DIR = PROJECT_ROOT / "models" / "f5-vi"


class PipelineStageError(RuntimeError):
    """Lỗi ở 1 bước cụ thể trong pipeline — kèm tên bước để UI/CLI báo đúng chỗ hỏng."""

    def __init__(self, stage, detail):
        super().__init__(f"[{stage}] {detail}")
        self.stage = stage
        self.detail = detail


def preflight_checks():
    """Kiểm tra môi trường trước khi chạy, báo lỗi rõ ràng thay vì traceback khó hiểu."""
    problems = []
    if FROZEN:
        if shutil.which(FFMPEG_BIN) is None and not Path(FFMPEG_BIN).exists():
            problems.append(f"Không tìm thấy ffmpeg đóng gói: {FFMPEG_BIN}")
        if not Path(VSR_CMD_BASE[0]).exists():
            problems.append(f"Không tìm thấy vsr_cli.exe: {VSR_CMD_BASE[0]}")
        if not Path(PVT_CMD_BASE[0]).exists():
            problems.append(f"Không tìm thấy pyvideotrans_cli.exe: {PVT_CMD_BASE[0]}")
    else:
        if shutil.which(FFMPEG_BIN) is None:
            problems.append("Không tìm thấy `ffmpeg` trong PATH.")
        if shutil.which(FFPROBE_BIN) is None:
            problems.append("Không tìm thấy `ffprobe` trong PATH.")
        if not Path(VSR_CMD_BASE[0]).exists():
            problems.append(
                f"Chưa setup venv cho video-subtitle-remover ({VSR_CMD_BASE[0]} không tồn tại) — xem Phase 0."
            )
        if not Path(PVT_CMD_BASE[0]).exists():
            problems.append(
                f"Chưa setup venv cho pyvideotrans ({PVT_CMD_BASE[0]} không tồn tại) — xem Phase 0."
            )
    if problems:
        raise PipelineStageError(
            "Kiểm tra môi trường",
            "Thiếu môi trường, chạy lại sau khi khắc phục:\n" + "\n".join(f"  - {p}" for p in problems),
        )


def run(cmd, cwd=None, stage=""):
    print(f"[run] {' '.join(str(c) for c in cmd)}")
    try:
        subprocess.run(cmd, cwd=cwd, check=True)
    except FileNotFoundError as e:
        raise PipelineStageError(stage, f"Không tìm thấy chương trình để chạy: {e.filename}") from e
    except subprocess.CalledProcessError as e:
        raise PipelineStageError(
            stage, f"Lệnh thất bại (exit code {e.returncode}): {' '.join(str(c) for c in cmd)}"
        ) from e


def probe_resolution(video_path):
    out = subprocess.run(
        [FFPROBE_BIN, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", str(video_path)],
        check=True, capture_output=True, text=True,
    )
    info = json.loads(out.stdout)["streams"][0]
    return info["width"], info["height"]


def remove_old_subtitles(input_video, work_dir, inpaint_mode="sttn-auto", sub_areas=None):
    """Xoá sub/logo cũ trong các VÙNG do người dùng khoanh (sub_areas).

    sub_areas: list các tuple (ymin, ymax, xmin, xmax) theo pixel gốc của video.

    Nếu sub_areas rỗng/None -> BỎ QUA hẳn bước này, trả về video gốc. Lý do:
    mode sttn-auto KHÔNG tự dò tìm phụ đề (backend/main.py sttn_auto_mode ghi rõ
    "không tiến hành detect phụ đề" - chỉ xoá đúng vùng toạ độ được truyền vào).
    Nếu không truyền vùng, VSR mặc định lấy TOÀN khung hình rồi để STTN "vẽ lại"
    cả khung bằng cách mượn frame kế bên -> với video gần tĩnh nó tái tạo y nguyên
    (kể cả sub cũ) nên vô ích mà còn tốn cả giờ. Bỏ qua rõ ràng tốt hơn chạy 1
    bước vô nghĩa.
    """
    stage = "VSR xoá sub/logo cũ"
    if not sub_areas:
        return input_video
    cleaned = work_dir / "cleaned.mp4"
    cmd = [
        *VSR_CMD_BASE,
        "--input", str(input_video),
        "--output", str(cleaned),
        "--inpaint-mode", inpaint_mode,
    ]
    for area in sub_areas:
        ymin, ymax, xmin, xmax = area
        cmd += ["--subtitle-area-coords", str(int(ymin)), str(int(ymax)), str(int(xmin)), str(int(xmax))]
    run(cmd, cwd=VSR_DIR, stage=stage)
    if not cleaned.exists():
        raise PipelineStageError(stage, f"Không sinh ra file output mong đợi: {cleaned}")
    return cleaned


EL_CLONE_SCRIPT = PROJECT_ROOT / "el_clone.py"


def synthesize_elevenlabs_dub(dub_srt, api_key, voice_id, model, work_dir, speed=1.0):
    """Dub bằng ElevenLabs GỌI 1 LẦN /with-timestamps cho cả bài rồi cắt theo
    alignment -> KHÔNG lệch ngữ điệu. Chạy el_clone.py trong venv pyvideotrans
    (có elevenlabs/numpy/soundfile). Trả (wav, srt). Xem HANDOFF.md."""
    stage = "ElevenLabs dub"
    out_wav = work_dir / "el_dub.wav"
    out_srt = work_dir / "el.srt"
    if FROZEN:
        py = PVT_CMD_BASE[0]  # frozen chưa hỗ trợ — cần bổ sung sau
    else:
        py = str(PVT_PY)
    cmd = [py, str(EL_CLONE_SCRIPT), "--srt", str(dub_srt), "--out", str(out_wav),
           "--out-srt", str(out_srt), "--api-key", api_key, "--voice-id", voice_id,
           "--model", model, "--speed", str(speed)]
    print(f"[run] el_clone (voice={voice_id} model={model})")
    try:
        subprocess.run(cmd, check=True, cwd=str(PROJECT_ROOT))
    except subprocess.CalledProcessError as e:
        raise PipelineStageError(stage, f"ElevenLabs lỗi (exit {e.returncode}) — kiểm tra API key/Voice ID/model") from e
    if not out_wav.exists():
        raise PipelineStageError(stage, f"Không sinh ra file dub: {out_wav}")
    return out_wav, (out_srt if out_srt.exists() else None)


def set_elevenlabs_config(api_key, voice_id, model="eleven_multilingual_v2", name="EL Voice"):
    """Ghi API key + voice_id vào config của pyvideotrans để dùng ElevenLabs
    (tts_type=22). pyvideotrans đọc key từ params.json, voice_id từ elevenlabs.json
    theo tên role. Trả về tên role (dùng làm --voice_role)."""
    import json as _json
    pv = PVT_DIR / "videotrans" / "params.json"
    d = _json.loads(pv.read_text(encoding="utf-8")) if pv.exists() else {}
    d["elevenlabstts_key"] = api_key
    d["elevenlabstts_models"] = model
    pv.write_text(_json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    ev = PVT_DIR / "videotrans" / "voicejson" / "elevenlabs.json"
    ed = _json.loads(ev.read_text(encoding="utf-8")) if ev.exists() else {}
    ed[name] = {"name": name, "voice_id": voice_id}
    ev.write_text(_json.dumps(ed, ensure_ascii=False), encoding="utf-8")
    return name


def transcribe_translate_dub(input_video, work_dir, source_lang, target_lang,
                              model_name, voice_role, tts_type="0"):
    stage = "pyvideotrans transcribe/dịch/dub"
    pvt_out = work_dir / "pvt_out"
    pvt_out.mkdir(exist_ok=True)
    run([
        *PVT_CMD_BASE, "--task", "vtv",
        "--name", str(input_video),
        "--recogn_type", "0",
        "--model_name", model_name,
        "--source_language_code", source_lang,
        "--target_language_code", target_lang,
        "--translate_type", "0",
        "--tts_type", str(tts_type),
        "--voice_role", voice_role,
        "--subtitle_type", "0",
        "--voice_autorate",
        "--output-dir", str(pvt_out),
        "--verbose",
    ], cwd=PVT_DIR, stage=stage)

    dub_audio = pvt_out / f"{target_lang}.m4a"
    dub_srt = pvt_out / f"{target_lang}.srt"
    if not dub_audio.exists() or not dub_srt.exists():
        raise PipelineStageError(
            stage,
            f"Không sinh ra file mong đợi trong {pvt_out} (cần {dub_audio.name} + {dub_srt.name}). "
            f"Kiểm tra lại mã ngôn ngữ (--source-lang/--target-lang) và voice_role có hợp lệ không.",
        )
    return dub_audio, dub_srt


def transcribe_audio(wav_path):
    """Nhận diện lời thoại 1 file audio bằng faster-whisper của pyvideotrans (dev mode).

    Dùng để lấy ref_text cho F5 clone khi người dùng để trống. Chỉ chạy được ở
    dev mode (PVT_PY là python thật có faster_whisper). Frozen/Windows trả None ->
    F5 sẽ tự transcribe. Lỗi bất kỳ -> None (F5 tự lo), không làm hỏng pipeline.
    """
    if FROZEN:
        return None
    code = (
        "import sys;from faster_whisper import WhisperModel;"
        "m=WhisperModel('small',device='cpu',compute_type='int8');"
        "segs,_=m.transcribe(sys.argv[1],beam_size=5);"
        "print(' '.join(s.text.strip() for s in segs))"
    )
    try:
        out = subprocess.run(
            [str(PVT_PY), "-c", code, str(wav_path)],
            check=True, capture_output=True, text=True, timeout=180,
        )
        return out.stdout.strip().lower() or None
    except Exception as e:
        print(f"[transcribe_audio] Không transcribe được ref, để F5 tự lo: {e}")
        return None


def synthesize_clone_dub(dub_srt, ref_wav, ref_text, work_dir, device=None):
    """Tạo track audio dub bằng giọng CLONE (F5-TTS) theo timing của dub_srt.

    Gọi f5_clone.py trong f5env riêng (không đụng venv pyvideotrans). Dùng thay
    cho bản dub Edge-TTS khi người dùng chọn chế độ clone giọng.
    """
    stage = "F5 clone giọng"
    out_wav = work_dir / "clone_dub.wav"
    out_srt = work_dir / "clone.srt"
    if not Path(F5_PY).exists():
        raise PipelineStageError(
            stage, f"Chưa cài môi trường F5 (f5env). Chạy lại setup để cài. Thiếu: {F5_PY}")
    if not (F5_MODEL_DIR / "model_last.pt").exists():
        raise PipelineStageError(
            stage, f"Thiếu model F5 tiếng Việt ở {F5_MODEL_DIR}. Chạy lại setup để tải.")

    if device is None:
        device = "cuda" if sys.platform == "win32" else "mps"

    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"           # tránh Fatal error lúc torch teardown
    env["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
    # torchcodec (F5 đọc audio) cần ffmpeg 4-7; máy có thể có ffmpeg 8 -> trỏ
    # ffmpeg@6 (cài kèm) cho torchcodec tìm libavutil tương thích.
    if sys.platform == "darwin":
        for cand in ("/opt/homebrew/opt/ffmpeg@6/lib", "/usr/local/opt/ffmpeg@6/lib"):
            if Path(cand).exists():
                env["DYLD_FALLBACK_LIBRARY_PATH"] = cand + os.pathsep + env.get("DYLD_FALLBACK_LIBRARY_PATH", "")
                break

    cmd = [
        str(F5_PY), str(F5_CLONE_SCRIPT),
        "--ref", str(ref_wav),
        "--ref-text", ref_text or "",
        "--srt", str(dub_srt),
        "--out", str(out_wav),
        "--out-srt", str(out_srt),
        "--model-dir", str(F5_MODEL_DIR),
        "--device", device,
    ]
    print(f"[run] {' '.join(str(c) for c in cmd)}")
    try:
        subprocess.run(cmd, check=True, env=env, cwd=str(PROJECT_ROOT))
    except subprocess.CalledProcessError as e:
        raise PipelineStageError(stage, f"F5 clone giọng lỗi (exit code {e.returncode})") from e
    if not out_wav.exists():
        raise PipelineStageError(stage, f"F5 không sinh ra file dub: {out_wav}")
    return out_wav, (out_srt if out_srt.exists() else None)


def build_fixed_ass(srt_path, work_dir, width, height, bottom_pct=15, sub_box=None):
    """Convert srt->ass rồi patch PlayRes + font/margin cho đúng tỉ lệ video thật.

    bottom_pct: khoảng cách từ đáy video lên tới phụ đề, tính theo % chiều cao.
    Mặc định 15% (vùng an toàn TikTok — tránh bị caption/nút của TikTok che).

    sub_box: nếu truyền (ymin, ymax, xmin, xmax) theo pixel gốc -> đặt phụ đề mới
    NẰM TRONG ô này (căn giữa ô, cỡ chữ tự co vừa chiều cao ô, câu dài tự xuống
    dòng trong bề ngang ô). Dùng khi muốn sub mới đè lên đúng chỗ sub cũ đã blur.
    Nếu None -> đặt ở đáy như cũ theo bottom_pct.
    """
    stage = "Tạo phụ đề mới đúng vị trí"
    ass_path = work_dir / "fixed.ass"
    run([FFMPEG_BIN, "-y", "-i", str(srt_path), str(ass_path)], stage=stage)

    if not ass_path.exists():
        raise PipelineStageError(stage, f"ffmpeg không sinh ra file .ass: {ass_path}")

    text = ass_path.read_text(encoding="utf-8-sig")
    text = re.sub(r"PlayResX:\s*\d+", f"PlayResX: {width}", text)
    text = re.sub(r"PlayResY:\s*\d+", f"PlayResY: {height}", text)
    outline = max(1, round(height * 0.0025))

    if sub_box is not None:
        ymin, ymax, xmin, xmax = sub_box
        box_h = max(1, ymax - ymin)
        # Co chu vua ~2 dong trong o: 2 dong * ~1.2 line-height <= box_h ->
        # fontsize ~ box_h / 2.4. Chan tren de tranh chu qua to voi o cao,
        # chan duoi 14px de con doc duoc voi o thap.
        fontsize = max(14, min(round(box_h * 0.40), round(box_h * 0.72)))
        cx = round((xmin + xmax) / 2)
        cy = round((ymin + ymax) / 2)
        margin_l = max(0, round(xmin))
        margin_r = max(0, round(width - xmax))
        # Alignment 5 = giua-giua; \pos + \an5 chèn vào từng dòng để căn chính
        # xác tâm ô. MarginL/R vẫn quy định bề ngang để libass tự xuống dòng.
        new_style = (
            f"Style: Default,Arial,{fontsize},&Hffffff,&Hffffff,&H0,&H80000000,"
            f"0,0,0,0,100,100,0,0,1,{outline},0,5,{margin_l},{margin_r},0,1"
        )
        text = re.sub(r"^Style: Default,.*$", new_style, text, count=1, flags=re.MULTILINE)
        # Chèn override {\an5\pos(cx,cy)} vào đầu phần text của mỗi dòng Dialogue
        # (9 field trước text theo chuẩn ASS, text là phần còn lại sau dấu phẩy thứ 9).
        pos_tag = f"{{\\an5\\pos({cx},{cy})}}"
        text = re.sub(
            r"^(Dialogue:(?:[^,]*,){9})(.*)$",
            lambda m: m.group(1) + pos_tag + m.group(2),
            text, flags=re.MULTILINE,
        )
    else:
        fontsize = max(16, round(height * 0.035))
        margin_v = round(height * max(0, min(bottom_pct, 45)) / 100)
        margin_lr = round(width * 0.04)
        new_style = (
            f"Style: Default,Arial,{fontsize},&Hffffff,&Hffffff,&H0,&H80000000,"
            f"0,0,0,0,100,100,0,0,1,{outline},0,2,{margin_lr},{margin_lr},{margin_v},1"
        )
        text = re.sub(r"^Style: Default,.*$", new_style, text, count=1, flags=re.MULTILINE)

    ass_path.write_text(text, encoding="utf-8")
    return ass_path


def _media_duration(path):
    out = subprocess.run(
        [FFPROBE_BIN, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def compose_final(cleaned_video, dub_audio, ass_path, output_path, stretch_video=False):
    """Ghep: video da xoa sub cu (khong lay audio goc) + audio dub moi + sub moi dung vi tri.

    stretch_video: nếu True và dub dài hơn video, KÉO GIÃN video cho khớp độ dài
    dub (setpts) — dùng cho giọng clone đọc tự nhiên (dài hơn timing gốc) để giọng
    không bị cắt/không phải nén nhanh. Phụ đề (.ass) đã theo timing của dub nên khớp.
    """
    stage = "Ghép video cuối"
    vf = f"subtitles=filename='{ass_path.name}'"
    if stretch_video:
        vdur = _media_duration(cleaned_video)
        adur = _media_duration(dub_audio)
        if vdur > 0 and adur > vdur * 1.02:
            factor = adur / vdur
            # setpts kéo giãn thời gian video (chậm lại) cho bằng độ dài dub.
            vf = f"setpts={factor:.4f}*PTS,{vf}"
    run([
        FFMPEG_BIN, "-y",
        "-i", str(cleaned_video),
        "-i", str(dub_audio),
        "-filter_complex", f"[0:v]{vf}[vout]",
        "-map", "[vout]", "-map", "1:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac",
        "-shortest", "-movflags", "+faststart",
        str(output_path),
    ], cwd=ass_path.parent, stage=stage)

    if not output_path.exists():
        raise PipelineStageError(stage, f"ffmpeg không sinh ra file output cuối: {output_path}")


def main():
    cfg = load_config()
    parser = argparse.ArgumentParser(description="Video localization pipeline (VSR + pyvideotrans)")
    parser.add_argument("--input", required=True, help="Đường dẫn video gốc")
    parser.add_argument("--source-lang", default=cfg["source_lang"], help="Mã ngôn ngữ gốc, ví dụ zh-cn")
    parser.add_argument("--target-lang", default=cfg["target_lang"], help="Mã ngôn ngữ đích, ví dụ vi")
    parser.add_argument("--model", default=cfg["model_name"], help="Whisper model (tiny/small/medium/large-v3)")
    parser.add_argument("--voice", default=cfg["voice_role"], help="Edge-TTS voice role")
    parser.add_argument("--inpaint-mode", default=cfg["inpaint_mode"], help="VSR inpaint mode")
    parser.add_argument("--sub-area", action="append", nargs=4, type=int,
                         metavar=("YMIN", "YMAX", "XMIN", "XMAX"),
                         help="Vùng xoá sub/logo cũ (pixel gốc). Lặp lại nhiều lần cho nhiều vùng. "
                              "Không truyền -> bỏ qua bước xoá sub.")
    parser.add_argument("--subtitle-bottom-pct", type=int, default=int(cfg.get("subtitle_bottom_pct", 15)),
                         help="Khoảng cách phụ đề mới tới đáy video, tính theo %% chiều cao (mặc định 15).")
    parser.add_argument("--sub-in-region", action="store_true",
                         help="Đặt phụ đề mới vào ô --sub-area to nhất (đè lên chỗ sub cũ) thay vì ở đáy.")
    parser.add_argument("--output", default=None, help="File output cuối (mặc định: <input>_<target-lang>.mp4)")
    parser.add_argument("--keep-temp", action="store_true", help="Giữ lại thư mục tạm để debug")
    parser.add_argument("--save-as-default", action="store_true",
                         help="Lưu source-lang/target-lang/model/voice/inpaint-mode hiện tại làm mặc định mới")
    args = parser.parse_args()

    if args.save_as_default:
        save_config(
            source_lang=args.source_lang, target_lang=args.target_lang,
            model_name=args.model, voice_role=args.voice, inpaint_mode=args.inpaint_mode,
        )
        print(f"[config] Đã lưu mặc định mới vào {PROJECT_ROOT / 'config.json'}")

    input_video = Path(args.input).resolve()
    if not input_video.exists():
        sys.exit(f"[error] Không tìm thấy file: {input_video}")

    output_path = Path(args.output).resolve() if args.output else \
        input_video.parent / f"{input_video.stem}_{args.target_lang}.mp4"

    work_dir = input_video.parent / f"_work_{input_video.stem}"
    work_dir.mkdir(exist_ok=True)

    try:
        preflight_checks()

        print("== Bước 1/4: VSR xoá sub/logo cũ ==")
        cleaned_video = remove_old_subtitles(input_video, work_dir, args.inpaint_mode, sub_areas=args.sub_area)

        print("== Bước 2/4: pyvideotrans transcribe + dịch + dub ==")
        dub_audio, dub_srt = transcribe_translate_dub(
            input_video, work_dir, args.source_lang, args.target_lang,
            args.model, args.voice,
        )

        print("== Bước 3/4: tự tạo sub mới đúng vị trí (fix PlayRes bug) ==")
        width, height = probe_resolution(cleaned_video)
        sub_box = None
        if args.sub_in_region and args.sub_area:
            sub_box = max(args.sub_area, key=lambda a: (a[1] - a[0]) * (a[3] - a[2]))
            print(f"[sub] Đặt phụ đề vào ô {sub_box}")
        ass_path = build_fixed_ass(dub_srt, work_dir, width, height,
                                    bottom_pct=args.subtitle_bottom_pct, sub_box=sub_box)

        print("== Bước 4/4: ghép video sạch + audio dub + sub mới ==")
        compose_final(cleaned_video, dub_audio, ass_path, output_path)

        print(f"\n[Done] Output: {output_path}")
    except PipelineStageError as e:
        sys.exit(f"\n[LỖI] {e}")
    finally:
        if not args.keep_temp:
            shutil.rmtree(work_dir, ignore_errors=True)
        else:
            print(f"[debug] Thư mục tạm giữ lại: {work_dir}")


if __name__ == "__main__":
    main()
