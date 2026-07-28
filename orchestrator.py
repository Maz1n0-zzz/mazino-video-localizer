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
import re
import shutil
import subprocess
import sys
from pathlib import Path

from pipeline_config import load_config, save_config

PROJECT_ROOT = Path(__file__).resolve().parent
VSR_DIR = PROJECT_ROOT / "vendor" / "video-subtitle-remover"
VSR_PY = VSR_DIR / "videoEnv" / "bin" / "python"
PVT_DIR = PROJECT_ROOT / "vendor" / "pyvideotrans"
PVT_PY = PVT_DIR / ".venv" / "bin" / "python3"


class PipelineStageError(RuntimeError):
    """Lỗi ở 1 bước cụ thể trong pipeline — kèm tên bước để UI/CLI báo đúng chỗ hỏng."""

    def __init__(self, stage, detail):
        super().__init__(f"[{stage}] {detail}")
        self.stage = stage
        self.detail = detail


def preflight_checks():
    """Kiểm tra môi trường trước khi chạy, báo lỗi rõ ràng thay vì traceback khó hiểu."""
    problems = []
    if shutil.which("ffmpeg") is None:
        problems.append("Không tìm thấy `ffmpeg` trong PATH.")
    if shutil.which("ffprobe") is None:
        problems.append("Không tìm thấy `ffprobe` trong PATH.")
    if not VSR_PY.exists():
        problems.append(
            f"Chưa setup venv cho video-subtitle-remover ({VSR_PY} không tồn tại) — xem Phase 0."
        )
    if not PVT_PY.exists():
        problems.append(
            f"Chưa setup venv cho pyvideotrans ({PVT_PY} không tồn tại) — xem Phase 0."
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
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", str(video_path)],
        check=True, capture_output=True, text=True,
    )
    info = json.loads(out.stdout)["streams"][0]
    return info["width"], info["height"]


def remove_old_subtitles(input_video, work_dir, inpaint_mode="sttn-auto"):
    stage = "VSR xoá sub/logo cũ"
    cleaned = work_dir / "cleaned.mp4"
    run([
        str(VSR_PY), "-m", "backend.main",
        "--input", str(input_video),
        "--output", str(cleaned),
        "--inpaint-mode", inpaint_mode,
    ], cwd=VSR_DIR, stage=stage)
    if not cleaned.exists():
        raise PipelineStageError(stage, f"Không sinh ra file output mong đợi: {cleaned}")
    return cleaned


def transcribe_translate_dub(input_video, work_dir, source_lang, target_lang,
                              model_name, voice_role):
    stage = "pyvideotrans transcribe/dịch/dub"
    pvt_out = work_dir / "pvt_out"
    pvt_out.mkdir(exist_ok=True)
    run([
        str(PVT_PY), "cli.py", "--task", "vtv",
        "--name", str(input_video),
        "--recogn_type", "0",
        "--model_name", model_name,
        "--source_language_code", source_lang,
        "--target_language_code", target_lang,
        "--translate_type", "0",
        "--tts_type", "0",
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


def build_fixed_ass(srt_path, work_dir, width, height):
    """Convert srt->ass rồi patch PlayRes + font/margin cho đúng tỉ lệ video thật."""
    stage = "Tạo phụ đề mới đúng vị trí"
    ass_path = work_dir / "fixed.ass"
    run(["ffmpeg", "-y", "-i", str(srt_path), str(ass_path)], stage=stage)

    if not ass_path.exists():
        raise PipelineStageError(stage, f"ffmpeg không sinh ra file .ass: {ass_path}")

    text = ass_path.read_text(encoding="utf-8-sig")
    text = re.sub(r"PlayResX:\s*\d+", f"PlayResX: {width}", text)
    text = re.sub(r"PlayResY:\s*\d+", f"PlayResY: {height}", text)

    fontsize = max(16, round(height * 0.035))
    outline = max(1, round(height * 0.0025))
    margin_v = round(height * 0.05)
    margin_lr = round(width * 0.04)
    new_style = (
        f"Style: Default,Arial,{fontsize},&Hffffff,&Hffffff,&H0,&H80000000,"
        f"0,0,0,0,100,100,0,0,1,{outline},0,2,{margin_lr},{margin_lr},{margin_v},1"
    )
    text = re.sub(r"^Style: Default,.*$", new_style, text, count=1, flags=re.MULTILINE)
    ass_path.write_text(text, encoding="utf-8")
    return ass_path


def compose_final(cleaned_video, dub_audio, ass_path, output_path):
    """Ghep: video da xoa sub cu (khong lay audio goc) + audio dub moi + sub moi dung vi tri."""
    stage = "Ghép video cuối"
    run([
        "ffmpeg", "-y",
        "-i", str(cleaned_video),
        "-i", str(dub_audio),
        "-filter_complex", f"[0:v]subtitles=filename='{ass_path.name}'[vout]",
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
        cleaned_video = remove_old_subtitles(input_video, work_dir, args.inpaint_mode)

        print("== Bước 2/4: pyvideotrans transcribe + dịch + dub ==")
        dub_audio, dub_srt = transcribe_translate_dub(
            input_video, work_dir, args.source_lang, args.target_lang,
            args.model, args.voice,
        )

        print("== Bước 3/4: tự tạo sub mới đúng vị trí (fix PlayRes bug) ==")
        width, height = probe_resolution(cleaned_video)
        ass_path = build_fixed_ass(dub_srt, work_dir, width, height)

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
