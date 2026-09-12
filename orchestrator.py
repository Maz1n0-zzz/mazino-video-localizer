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
import hashlib
import json
import signal
import threading as _threading
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


class PipelineCancelled(Exception):
    """Người dùng bấm Ngưng — không phải lỗi, không báo đỏ."""


_LIVE_PROCS = set()
_PROCS_LOCK = _threading.Lock()
_CANCEL = _threading.Event()


def reset_cancel():
    _CANCEL.clear()


def is_cancelled():
    return _CANCEL.is_set()


def check_cancelled():
    """Gọi ở ranh giới từng bước để dừng cả những bước chạy trong tiến trình."""
    if _CANCEL.is_set():
        raise PipelineCancelled()


def cancel_all():
    """Bắn SIGTERM cho cả NHÓM tiến trình đang chạy. -> số tiến trình đã bắn.

    Giết theo NHÓM (killpg) chứ không riêng tiến trình con: VSR và pyvideotrans
    còn đẻ tiếp tiến trình cháu (ffmpeg, worker torch); giết mỗi tiến trình cha
    thì cháu vẫn chạy tiếp, vẫn ăn CPU và RAM. Vì thế Popen dưới đây luôn mở
    phiên mới (start_new_session) để có nhóm riêng mà giết.
    """
    _CANCEL.set()
    with _PROCS_LOCK:
        procs = list(_LIVE_PROCS)
    for p in procs:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        except Exception:
            try:
                p.terminate()
            except Exception:
                pass
    return len(procs)


def run(cmd, cwd=None, stage="", tail_lines=0):
    """tail_lines > 0: vừa in ra như cũ, vừa giữ lại N dòng cuối để nhét vào
    thông báo lỗi. Cần cho việc phân biệt "hết quota Gemini" với lỗi khác —
    exit code chỉ cho biết THẤT BẠI, không cho biết VÌ SAO.

    Luôn dùng Popen (kể cả khi không cần giữ log) để nút Ngưng có cái mà giết:
    subprocess.run() chặn luôn luồng, không lấy được tiến trình ra ngoài."""
    check_cancelled()
    print(f"[run] {' '.join(str(c) for c in cmd)}")

    from collections import deque
    keep = deque(maxlen=tail_lines) if tail_lines > 0 else None
    kw = {"cwd": cwd, "start_new_session": True}
    if keep is not None:
        kw.update(stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                  encoding="utf-8", errors="replace", bufsize=1)
    try:
        proc = subprocess.Popen(cmd, **kw)
    except FileNotFoundError as e:
        raise PipelineStageError(stage, f"Không tìm thấy chương trình để chạy: {e.filename}") from e

    with _PROCS_LOCK:
        _LIVE_PROCS.add(proc)
    try:
        if keep is not None:
            for line in proc.stdout:
                print(line, end="", flush=True)
                keep.append(line.rstrip("\n"))
        code = proc.wait()
    finally:
        with _PROCS_LOCK:
            _LIVE_PROCS.discard(proc)

    check_cancelled()   # bị giết do bấm Ngưng -> không phải lỗi pipeline
    if code != 0:
        raise PipelineStageError(
            stage,
            f"Lệnh thất bại (exit code {code}): {' '.join(str(c) for c in cmd)}"
            + ("\n" + "\n".join(keep) if keep else ""),
        )


# Dấu hiệu "hết hạn mức" của Gemini. Bậc miễn phí chỉ 20 request/NGÀY cho mỗi
# model (quotaId GenerateRequestsPerDayPerProjectPerModel-FreeTier) — 1 video
# 58 cue với batch 20 đã tốn 3 request. Quota tính RIÊNG từng model nên đổi
# model là có thêm 20 lượt.
QUOTA_MARKERS = ("RESOURCE_EXHAUSTED", "exceeded your current quota",
                 "429", "quota", "rate limit", "rate_limit")
QUOTA_MARKERS_LOWER = tuple(m.lower() for m in QUOTA_MARKERS)


def _chi_phan_loi(text):
    """Bóc DÒNG LỆNH ra, chỉ giữ phần output thật của tiến trình con.

    PipelineStageError của run() có dạng:
        Lệnh thất bại (exit code N): <cả dòng lệnh>
        <40 dòng output cuối>
    Dòng lệnh chứa tên tham số CLI như --recogn_type, --source_language_code,
    --target_language_code. Đo thực tế 9/9/2026: so marker trên cả chuỗi làm
    ENGINE_INDEPENDENT_MARKERS khớp nhầm 4 lần vào chính dòng lệnh -> job hết
    quota Gemini bị coi là "lỗi ngoài tầng dịch" -> không tụt hạng -> chết oan.
    """
    dong = str(text).splitlines()
    if dong and dong[0].startswith("Lệnh thất bại"):
        dong = dong[1:]
    return "\n".join(dong)


def is_quota_error(text):
    t = _chi_phan_loi(text).lower()
    return any(m.lower() in t for m in QUOTA_MARKERS)


# Lỗi mà ĐỔI ENGINE DỊCH CHẮC CHẮN KHÔNG CỨU ĐƯỢC -> phải nổi lên ngay, đừng
# thử lại 4 bậc còn lại cho tốn thêm mỗi bậc ~90 giây ASR.
#
# Đây là danh sách ĐEN, cố ý ngược với cách làm ban đầu. Lọc theo danh sách
# TRẮNG ("chỉ tụt hạng khi khớp mẫu lỗi đã biết") đã sai hai lần trong một tối
# 8/9/2026: lần đầu không khớp "Gemini result is emtpy", vá xong thì lần sau
# không khớp "503 UNAVAILABLE ... high demand". Không thể liệt kê hết mọi lỗi
# mà nhà cung cấp có thể trả về, nên mặc định là TỤT HẠNG; chỉ chặn những thứ
# nằm rõ ràng ngoài tầng dịch.
ENGINE_INDEPENDENT_MARKERS = (
    "ffmpeg", "ffprobe",              # dựng/ghép video
    "firered", "whisper", "sherpa",   # nhận dạng tiếng nói
    "语音识别", "recogn",
    "language_code", "source_language", "target_language",   # mã ngôn ngữ sai
    "no such file", "filenotfound", "không tìm thấy",
    "lama", "inpaint", "vsr",         # bước xoá sub
    "no space left", "disk full",
)


def is_engine_independent_error(text):
    """True = lỗi nằm ngoài tầng dịch, đổi engine vô ích.

    CHỈ soi phần output thật — xem _chi_phan_loi(). Soi cả dòng lệnh là sai.
    """
    t = _chi_phan_loi(text).lower()
    if any(m in t for m in QUOTA_MARKERS_LOWER):
        return False          # hết hạn mức thì đổi engine CÓ cứu được
    return any(m in t for m in ENGINE_INDEPENDENT_MARKERS)


def probe_resolution(video_path):
    out = subprocess.run(
        [FFPROBE_BIN, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", str(video_path)],
        check=True, capture_output=True, text=True,
    )
    info = json.loads(out.stdout)["streams"][0]
    return info["width"], info["height"]


LAMA_CACHE_DIR = PROJECT_ROOT / "outputs" / "_lama_cache"
LAMA_CACHE_INDEX = LAMA_CACHE_DIR / "index.json"

# Vùng xoá sub do Mazino KHOANH TAY nên không bao giờ trùng khít giữa hai lần.
# Đo thực tế 9/9/2026 trên cùng một video, ba lần vẽ:
#     (679,755, 81,515)  (687,774, 86,496)  (688,759, 94,481)
# Lệch tới 34 px. Làm tròn về lưới thì trượt vì bệnh mép; so sai số đối xứng thì
# phải nới ngưỡng mãi không biết dừng ở đâu.
#
# Luật đúng là hỏi "cache có DÙNG ĐƯỢC cho yêu cầu này không", gồm 2 điều kiện:
#   1. PHỦ HẾT vùng đang yêu cầu (cho hụt <= COVER_SLACK) -> chỗ cần blur chắc
#      chắn đã sạch trong bản cache.
#   2. KHÔNG xoá thừa quá EXTRA_MAX mỗi mép -> không bao giờ trả về bản bị xoá
#      rộng hơn ý người dùng. Vẽ hẹp lại vì muốn giữ mép nào đó là quyền của
#      người dùng, cache không được phép ghi đè quyết định đó.
LAMA_COVER_SLACK = 16
LAMA_EXTRA_MAX = 64


def _hash_video(input_video):
    h = hashlib.md5()
    with open(input_video, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _chuan_areas(sub_areas):
    return sorted(tuple(int(v) for v in a) for a in sub_areas)


def _lama_cache_file(input_video, inpaint_mode, sub_areas):
    """Đường dẫn cache CHÍNH XÁC (dùng để GHI). None nếu không băm được."""
    try:
        h = hashlib.md5(_hash_video(input_video).encode("utf-8"))
        h.update(repr((str(inpaint_mode), _chuan_areas(sub_areas))).encode("utf-8"))
        return LAMA_CACHE_DIR / f"{h.hexdigest()}.mp4"
    except Exception:
        return None


def _doc_index():
    try:
        return json.loads(LAMA_CACHE_INDEX.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _lama_cache_tim(input_video, inpaint_mode, sub_areas):
    """Tìm cache DÙNG ĐƯỢC: khớp nội dung video + mode, và mọi toạ độ lệch dưới
    LAMA_AREA_TOLERANCE. Trả Path hoặc None."""
    try:
        vhash = _hash_video(input_video)
        can = _chuan_areas(sub_areas)
    except Exception:
        return None
    for muc in _doc_index().get(vhash, []):
        if muc.get("mode") != str(inpaint_mode):
            continue
        co = [tuple(a) for a in muc.get("areas", [])]
        if len(co) != len(can) or not all(_vung_dung_duoc(c, y) for c, y in zip(co, can)):
            continue
        f = LAMA_CACHE_DIR / muc.get("file", "")
        if f.is_file():
            return f
    return None


def _vung_dung_duoc(co, yeu_cau):
    """Vùng đã xoá `co` có dùng được cho yêu cầu `yeu_cau` không?
    Toạ độ dạng (ymin, ymax, xmin, xmax)."""
    c_y0, c_y1, c_x0, c_x1 = co
    y_y0, y_y1, y_x0, y_x1 = yeu_cau
    # 1. phu het (cho hut <= COVER_SLACK o moi mep)
    if (c_y0 - y_y0 > LAMA_COVER_SLACK or y_y1 - c_y1 > LAMA_COVER_SLACK
            or c_x0 - y_x0 > LAMA_COVER_SLACK or y_x1 - c_x1 > LAMA_COVER_SLACK):
        return False
    # 2. khong xoa thua qua EXTRA_MAX o moi mep
    if (y_y0 - c_y0 > LAMA_EXTRA_MAX or c_y1 - y_y1 > LAMA_EXTRA_MAX
            or y_x0 - c_x0 > LAMA_EXTRA_MAX or c_x1 - y_x1 > LAMA_EXTRA_MAX):
        return False
    return True


def _lama_cache_ghi_index(input_video, inpaint_mode, sub_areas, cache_file):
    """Ghi thêm 1 mục vào index. Lỗi thì bỏ qua — chỉ mất tối ưu."""
    try:
        vhash = _hash_video(input_video)
        idx = _doc_index()
        muc = {"mode": str(inpaint_mode),
               "areas": [list(a) for a in _chuan_areas(sub_areas)],
               "file": cache_file.name}
        ds = idx.setdefault(vhash, [])
        if muc not in ds:
            ds.append(muc)
        LAMA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = LAMA_CACHE_INDEX.with_suffix(".json.part")
        tmp.write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(LAMA_CACHE_INDEX)
    except Exception as e:
        print(f"[LaMa] khong ghi duoc index cache: {e}", flush=True)


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

    # Bước này tốn ~47 phút cho video 5 phút, mà work_dir bị rmtree ở finally của
    # _run_job -> MỌI lỗi phía sau (dịch/dub) đều đập luôn thành quả LaMa. Ngày
    # 8/9/2026 mất ~2,5 tiếng vì 3 lần chết liên tiếp (OOM, thẻ bọc Gemini, 503).
    # Cache theo NỘI DUNG video + tham số xoá nên đổi vùng chọn là tự trượt cache.
    cache_file = _lama_cache_file(input_video, inpaint_mode, sub_areas)
    dung_lai = (cache_file if cache_file is not None and cache_file.exists()
                else _lama_cache_tim(input_video, inpaint_mode, sub_areas))
    if dung_lai is not None:
        print(f"[LaMa] dùng lại bản đã xoá sub trong cache, bỏ qua bước này: "
              f"{dung_lai.name}", flush=True)
        return dung_lai

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
    if cache_file is not None:
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            # Ghi ra file tạm rồi mới đổi tên: bị ngắt giữa dòng thì cache không
            # bao giờ ở trạng thái nửa vời.
            tmp = cache_file.with_suffix(".part")
            shutil.copy2(cleaned, tmp)
            tmp.replace(cache_file)
            _lama_cache_ghi_index(input_video, inpaint_mode, sub_areas, cache_file)
            print(f"[LaMa] đã lưu cache: {cache_file.name}", flush=True)
        except Exception as e:
            print(f"[LaMa] không lưu được cache (không sao, chỉ mất tối ưu): {e}", flush=True)
    return cleaned


EL_CLONE_SCRIPT = PROJECT_ROOT / "el_clone.py"


def synthesize_elevenlabs_dub(dub_srt, api_key, voice_id, model, work_dir, speed=1.0):
    """Dub bằng ElevenLabs GỌI 1 LẦN /with-timestamps cho cả bài rồi cắt theo
    alignment -> KHÔNG lệch ngữ điệu. Chạy el_clone.py trong venv pyvideotrans
    (có elevenlabs/numpy/soundfile). Trả (wav, srt). Xem HANDOFF.md."""
    stage = "ElevenLabs dub"
    out_wav = work_dir / "el_dub.wav"
    out_srt = work_dir / "el.srt"
    args = ["--srt", str(dub_srt), "--out", str(out_wav), "--out-srt", str(out_srt),
            "--api-key", api_key, "--voice-id", voice_id,
            "--model", model, "--speed", str(speed)]
    print(f"[run] el_clone (voice={voice_id} model={model})")

    if FROZEN:
        # Bản đóng gói KHÔNG có python.exe nào để chạy el_clone.py như script rời
        # (pyvideotrans_cli.exe là bundle PyInstaller, không phải trình thông dịch).
        # Gọi thẳng trong tiến trình -> lỗi thật nổi lên thành exception đọc được,
        # thay vì "exit 2" vô nghĩa. el_clone chỉ cần numpy+soundfile+urllib, đã
        # bundle kèm web_server.exe (xem installer/web_server.spec).
        import el_clone
        try:
            el_clone.main(args)
        except SystemExit as e:
            # el_clone dùng sys.exit("<mô tả>") cho lỗi tự bắt được.
            detail = str(e.code) if e.code not in (0, None) else ""
            if detail:
                raise PipelineStageError(stage, detail) from e
        except Exception as e:
            raise PipelineStageError(stage, f"{type(e).__name__}: {e}") from e
    else:
        cmd = [str(PVT_PY), str(EL_CLONE_SCRIPT), *args]
        try:
            # Giữ lại stderr để báo LỖI THẬT lên UI thay vì đoán mò theo exit code.
            subprocess.run(cmd, check=True, cwd=str(PROJECT_ROOT),
                           stderr=subprocess.PIPE, text=True)
        except subprocess.CalledProcessError as e:
            # Bỏ các dòng khung traceback (thụt đầu dòng) -> còn lại đúng dòng
            # exception cuối hoặc thông báo el_clone tự in ra.
            lines = [l for l in (e.stderr or "").splitlines()
                     if l.strip() and not l.startswith((" ", "\t")) and l != "Traceback (most recent call last):"]
            tail = "\n".join(lines[-3:])
            raise PipelineStageError(
                stage, tail or f"el_clone thoát với exit {e.returncode}, không rõ lý do") from e

    if not out_wav.exists():
        raise PipelineStageError(stage, f"Không sinh ra file dub: {out_wav}")
    return out_wav, (out_srt if out_srt.exists() else None)


# --- Nhận dạng giọng nói: FireRedASR + ElevenLabs Scribe ---------------------
# recogn_type của pyvideotrans (videotrans/recognition/__init__.py):
#   0 = faster-whisper (local)   4 = FireRedASR (local)   20 = ElevenLabs Scribe (cloud)
RECOGN_WHISPER = "0"
RECOGN_FIRERED = "4"
RECOGN_ELEVENLABS = "20"

# _fireredasr.py đặt model ở {pyvideotrans}/models/fireredasr và nạp encoder
# int8 ONNX qua sherpa-onnx. Kiểm đúng file encoder chứ không chỉ kiểm thư mục:
# lần tải dở vẫn để lại thư mục rỗng mà chạy là hỏng (bài học từ Whisper model.bin).
FIRERED_DIR = PVT_DIR / "models" / "fireredasr"
FIRERED_ENCODER = FIRERED_DIR / "encoder.int8.onnx"


# FireRedASR trả text THÔ không dấu câu -> cả đoạn dồn thành 1 câu dài, dịch ra
# lủng củng. pyvideotrans có sẵn bước khôi phục dấu câu (--fix_punc) chạy bằng
# sherpa-onnx ct-transformer, dùng chung thư viện với FireRed nên không kéo thêm
# dependency nào cho bản đóng gói Windows.
PUNC_MODEL = PVT_DIR / "models" / "puntc" / "model.onnx"


def firered_ready():
    return FIRERED_ENCODER.exists()


def punc_ready():
    return PUNC_MODEL.exists()


def _pvt_params_path():
    return PVT_DIR / "videotrans" / "params.json"


def get_elevenlabs_api_key():
    """Key ElevenLabs đã lưu (dùng chung cho cả giọng đọc TTS lẫn Scribe STT —
    videotrans/recognition/_elevenlabs.py đọc đúng key elevenlabstts_key này)."""
    import json as _json
    pv = _pvt_params_path()
    if not pv.exists():
        return ""
    try:
        return (_json.loads(pv.read_text(encoding="utf-8")).get("elevenlabstts_key") or "").strip()
    except Exception:
        return ""


def set_elevenlabs_api_key(api_key):
    """Ghi riêng API key (không đụng voice_id) — dùng khi chỉ chọn Scribe để
    transcribe mà giọng đọc vẫn là Edge-TTS/F5."""
    import json as _json
    pv = _pvt_params_path()
    d = _json.loads(pv.read_text(encoding="utf-8")) if pv.exists() else {}
    d["elevenlabstts_key"] = api_key
    pv.parent.mkdir(parents=True, exist_ok=True)
    pv.write_text(_json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


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


# --- Kênh dịch --------------------------------------------------------------
# translate_type của pyvideotrans (translator/_constants.py):
#   0 = Google (miễn phí, không key)   6 = Gemini   9 = Local LLM (Ollama)
# Google dịch TỪNG cue độc lập, không nhớ ngữ cảnh, không hiểu tiếng lóng và
# hay đổi cách phiên tên riêng giữa chừng (đo được: 小白 ra "Tiểu Bạch" chỗ này,
# "Xiaobai" chỗ kia). Hai kênh LLM nhận CẢ BATCH srt nên giữ được mạch hội thoại,
# lại đọc được prompt + glossary do ta soạn.
TRANS_GOOGLE = "0"
TRANS_CHATGPT = "4"
TRANS_DEEPSEEK = "5"
TRANS_GEMINI = "6"
TRANS_OLLAMA = "9"
TRANS_OPENROUTER = "10"

# Ba kênh TRẢ PHÍ, dùng khi chưa có model offline đủ tốt. Cùng một khuôn
# (key + tên model) nên gom vào một bảng thay vì viết 3 hàm gần giống nhau.
# Model mặc định lấy nguyên từ params.json của pyvideotrans — KHÔNG tự bịa
# tên model, vì đoán sai thì API trả 404 và job chết giữa chừng.
#
# TỐN TIỀN THẬT: các kênh này chỉ chạy khi người dùng CHỦ ĐỘNG chọn. Chuỗi tụt
# hạng không bao giờ tự nhảy vào đây — xem _translation_plan() ở web_server.
PAID_TRANS = {
    TRANS_CHATGPT: {
        "ten": "OpenAI", "key": "chatgpt_key", "model": "chatgpt_model",
        "mac_dinh": "gpt-5.5", "them": {"chatgpt_api": "https://api.openai.com/v1"},
    },
    TRANS_DEEPSEEK: {
        "ten": "DeepSeek", "key": "deepseek_key", "model": "deepseek_model",
        "mac_dinh": "deepseek-v4-pro", "them": {},
    },
    TRANS_OPENROUTER: {
        "ten": "OpenRouter", "key": "openrouter_key", "model": "openrouter_model",
        "mac_dinh": "minimax/minimax-m2.7", "them": {},
    },
}


def get_paid_key(engine):
    cfg = PAID_TRANS.get(engine)
    if not cfg:
        return ""
    return (_read_pvt_param(cfg["key"], "") or "").strip()


def get_paid_model(engine):
    cfg = PAID_TRANS.get(engine)
    if not cfg:
        return ""
    return (_read_pvt_param(cfg["model"], "") or "").strip() or cfg["mac_dinh"]


def set_paid_config(engine, api_key=None, model=None):
    """Ghi key + model cho 1 kênh trả phí vào params.json của pyvideotrans."""
    cfg = PAID_TRANS.get(engine)
    if not cfg:
        return False
    kv = dict(cfg["them"])
    if api_key:
        kv[cfg["key"]] = api_key.strip()
    kv[cfg["model"]] = (model or "").strip() or get_paid_model(engine)
    _write_pvt_params(**kv)
    set_ai_batch(AI_BATCH_GEMINI, send_srt=False)
    return True

OLLAMA_API = "http://localhost:11434/v1"
# 14b chứ không phải 7b: đo 3 lượt trên 58 cue thật, 7b LỆCH DÒNG mọi lượt
# (câu 16 nhận bản dịch câu 17) và bỏ dịch 18-32 block; 14b không lệch lượt nào,
# chỉ sót 2-5 block. Đánh đổi: 14b chậm gấp đôi (~110s so với ~50s).
OLLAMA_DEFAULT_MODEL = "qwen2.5:14b"
# KHÔNG dùng gemini-2.5-flash / 2.5-flash-lite: Google đã ngừng cấp cho tài
# khoản mới, API trả "no longer available to new users" dù model vẫn còn liệt kê
# trong /v1beta/models — cái bẫy này đã làm hỏng 1 job thật.
# Thứ tự thử: mỗi model có quota 20 req/ngày RIÊNG, nên hết model này còn model
# kia. Đã smoke-test cả 3 trả HTTP 200 với key của Mazino.
GEMINI_MODEL_CHAIN = ["gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-3.6-flash"]
GEMINI_DEFAULT_MODEL = GEMINI_MODEL_CHAIN[0]


# Luật riêng cho tiếng Việt, chèn vào prompt của kênh LLM. Prompt gốc của
# pyvideotrans đã lo phần chung (văn nói, ép 1-1 block, nén ngắn cho khớp TTS)
# nhưng KHÔNG biết gì về tiếng Việt — nên Google lẫn LLM đều mắc đúng mấy lỗi
# đã đo được trên video thật: xưng hô "Bạn" cho nhóm bạn trẻ cãi nhau, 块钱
# thành "đô la", 张若雪 thành "Zhang Ruoxue", 雪糕刺客 dịch chữ thành "sát thủ".
VI_PROMPT_RULES = """
# VIETNAMESE-SPECIFIC RULES (HIGHEST PRIORITY — override anything above that conflicts)

## Xưng hô (pronouns) — quan trọng nhất
Vietnamese has no neutral "you". Choosing wrong makes the dub sound robotic.
- NEVER default to "Bạn"/"bạn" unless the speakers are actually strangers being polite.
- Young friends joking, teasing, arguing (the common case in short-form video):
  use "mày/tao", "ông/tôi", "bà/tôi", or bare imperatives with no pronoun at all.
- Speaking to an older man/peer casually: "anh"; to an older woman: "chị";
  to a younger person: "em". Keep the SAME pronoun pair for the same speaker
  across the whole file — do not switch halfway.
- Chinese vocatives 大哥/哥/姐/兄弟 are usually just casual address, NOT literal
  family: render as "ông ơi", "anh ơi", "bà ơi", "thằng bạn" — never "Anh lớn".

## Tên riêng (proper nouns)
- Use the Sino-Vietnamese (Hán-Việt) reading, NEVER pinyin romanisation.
  小白 -> "Tiểu Bạch" (never "Xiaobai"); 张若雪 -> "Trương Nhược Tuyết"
  (never "Zhang Ruoxue"); 白天鹏 -> "Bạch Thiên Bằng".
- Once you pick a rendering for a name, reuse it identically everywhere.

## Tiền tệ, số, đơn vị
- 块 / 块钱 / 元 / 人民币 = "tệ" (NEVER "đô la", never "nhân dân tệ" in speech).
- Read decimals the Vietnamese way: 65.3度 -> "65 phẩy 3 độ".

## Tiếng lóng & meme
Translate the MEANING, never word-by-word. If a Chinese internet slang term has
no Vietnamese equivalent, use a short natural Vietnamese phrase with the same
punch. Example: 雪糕刺客 is not "sát thủ kem" — it means ice cream that turns out
shockingly expensive at checkout -> "kem chém giá" / "kem cắt cổ".

## Văn phong
- Spoken Vietnamese as heard in vlogs and street videos, not textbook Vietnamese.
- Keep interjections alive: 哎呀 -> "Ối giời", 妈呀 -> "Má ơi", 卧槽 -> "Vãi".
- Drop the machine-translation tics: never "Bạn có thể vui lòng...",
  never "Bạn chưa bao giờ nhìn thấy điều này trước đây".
- Do not translate filler that adds nothing (啊/呢/吧 at sentence end) literally.

## Định dạng đầu ra — ĐỌC KỸ (đã làm hỏng job thật)
- Output the translation text and NOTHING else. Never wrap a line in angle
  brackets, square brackets, parentheses, quotes or any tag. The placeholder
  examples earlier in this prompt use wrappers ONLY to mark "put text here" —
  those wrappers are NOT part of the expected output. Copying them is a FATAL
  ERROR: the dubbing engine reads a wrapped line as markup, speaks nothing, and
  the whole job crashes.
- Give exactly ONE translation per line. Never offer alternatives separated by
  "|" or "/". Pick the best one and output only that.
- Never leave Chinese, Japanese or Korean characters in the output — not even a
  single one, not even inside an otherwise Vietnamese sentence. If a word is
  hard, translate its meaning; never copy the source characters through.
"""

# Glossary khởi đầu, rút từ chính video test của Mazino. Format của
# pyvideotrans: mỗi dòng "từ gốc=bản dịch", nạp vào prompt kèm chỉ thị BẮT BUỘC
# dùng đúng (util/help_misc.py:get_prompt).
VI_GLOSSARY = """小白=Tiểu Bạch
白天鹏=Bạch Thiên Bằng
张若雪=Trương Nhược Tuyết
块钱=tệ
人民币=tệ
雪糕刺客=kem chém giá
大哥=ông ơi
哎呀=Ối giời
妈呀=Má ơi"""


# Prompt gốc của pyvideotrans minh hoạ đầu ra mong muốn bằng những dòng bọc
# trong ngoặc vuông ("[Extremely concise translation of ... in {lang}]"). Model
# nhỏ BẮT CHƯỚC cái vỏ đó: qwen2.5:14b đã trả về 10 dòng liền bọc "<...>" trong
# job thật. ElevenLabs coi dòng bọc ngoặc là markup, không đọc thành tiếng, dồn
# cả cụm về một mốc thời gian -> el_clone cắt đoạn dài 0 giây -> ffmpeg exit 234.
# Bóc ngoặc ở ví dụ thì không còn khuôn nào để bắt chước.
_EXAMPLE_WRAP_RE = re.compile(r"^\[(.+)\]$", re.M)


def _defuse_bracket_examples(text):
    """Bỏ ngoặc vuông ở những dòng ví dụ chỉ-toàn-placeholder. -> (text, số dòng đã sửa)"""
    n = 0

    def sub(m):
        nonlocal n
        n += 1
        return m.group(1)

    return _EXAMPLE_WRAP_RE.sub(sub, text), n


def install_vi_translation_assets(overwrite_glossary=False):
    """Chèn luật tiếng Việt vào prompt của Gemini + Local LLM, và tạo glossary.

    Chèn NGAY TRƯỚC mục "# ACTUAL TASK" để luật nằm sau phần khung chung nhưng
    trước dữ liệu thật -> mô hình đọc luật gần nhất với lúc phải áp dụng.

    LUÔN dựng lại từ bản .orig thay vì bỏ qua khi đã chèn: trước đây hàm này
    thoát sớm nếu thấy marker, nên mọi lần sửa VI_PROMPT_RULES về sau đều KHÔNG
    tới được máy đã chạy một lần — prompt đứng im ở phiên bản đầu tiên.
    """
    done = []
    # chatgpt/deepseek/openrouter: 3 kenh tra phi Mazino them ngay 09/09 - truoc
    # do KHONG duoc tiem luat tieng Viet nen dich ra van "ban", ten rieng pinyin.
    _KENH = ("gemini", "localllm", "chatgpt", "deepseek", "openrouter")
    targets = [(kind, name) for kind in ("srt", "text") for name in _KENH]
    # localllm_mt: prompt rieng cho model DICH CHUYEN DUNG (Hunyuan-MT, Qwen-MT...).
    # Chi co ban text vi che do line-mode (aisendsrt=False) moi dung no.
    targets.append(("text", "localllm_mt"))
    for kind, name in targets:
        f = PVT_DIR / "videotrans" / "prompts" / kind / f"{name}.txt"
        orig = f.with_suffix(".txt.orig")
        # localllm_mt chi co .orig do minh viet ra; ban .txt duoc sinh o duoi.
        if not f.exists() and not orig.exists():
            continue
        if not orig.exists():
            orig.write_text(f.read_text(encoding="utf-8-sig"), encoding="utf-8")
        base, n_fix = _defuse_bracket_examples(orig.read_text(encoding="utf-8-sig"))
        cut = "# ACTUAL TASK"
        text = (base.replace(cut, VI_PROMPT_RULES + "\n" + cut, 1)
                if cut in base else base + VI_PROMPT_RULES)
        if not f.exists() or text != f.read_text(encoding="utf-8-sig", errors="replace"):
            f.write_text(text, encoding="utf-8")
            done.append(f"{kind}/{name} (bóc ngoặc {n_fix} dòng ví dụ)")

    # glossary.txt KHÔNG nằm trong DATAS của bản đóng gói -> phải ghi lúc chạy,
    # giống cfg.json. Không đè nếu Mazino đã tự sửa thêm từ của riêng anh ấy.
    g = PVT_DIR / "videotrans" / "glossary.txt"
    if overwrite_glossary or not g.exists():
        g.write_text(VI_GLOSSARY, encoding="utf-8")
    return done


def _write_pvt_params(**kv):
    """Ghi thêm khoá vào params.json của pyvideotrans, giữ nguyên khoá cũ."""
    import json as _json
    pv = _pvt_params_path()
    d = _json.loads(pv.read_text(encoding="utf-8")) if pv.exists() else {}
    d.update({k: v for k, v in kv.items() if v is not None})
    pv.parent.mkdir(parents=True, exist_ok=True)
    pv.write_text(_json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def get_gemini_key():
    import json as _json
    pv = _pvt_params_path()
    if not pv.exists():
        return ""
    try:
        return (_json.loads(pv.read_text(encoding="utf-8")).get("gemini_key") or "").strip()
    except Exception:
        return ""


def set_gemini_config(api_key=None, model=GEMINI_DEFAULT_MODEL):
    _write_pvt_params(gemini_key=api_key, gemini_model=model)
    set_ai_batch(AI_BATCH_GEMINI, send_srt=False)


# Số block SRT gửi mỗi lần cho LLM. Prompt bắt trả về ĐÚNG số block, nhưng model
# càng nhỏ càng dễ trôi: đo thực tế qwen2.5:7b nuốt mất block cuối khi gửi cả
# batch. Thiếu block thì pyvideotrans chèn dòng RỖNG bù vào
# (translator/_base.py:114-117) -> phụ đề mất chữ. Batch nhỏ đổi lấy độ tin cậy;
# vẫn đủ ngữ cảnh vì mỗi batch là mấy câu liền mạch của cùng đoạn hội thoại.
AI_BATCH_OLLAMA = 8
AI_BATCH_GEMINI = 20


def set_ai_batch(n, send_srt=True):
    """aitrans_thread + aisendsrt nằm trong cfg.json (settings), không phải params.json.

    send_srt=False -> chỉ gửi TỪNG DÒNG text trần thay vì cả khối SRT có số thứ
    tự + timestamp. Model nhỏ chép lại timestamp rất hay sai: đo qwen2.5:7b thấy
    kết quả LỆCH nguyên một dòng (câu 16 nhận bản dịch của câu 17) và 18/57 block
    trả về nguyên chữ Hán. Chế độ dòng khớp 1-1 nên không lệch được."""
    import json as _json
    cfg = PVT_DIR / "videotrans" / "cfg.json"
    try:
        d = _json.loads(cfg.read_text(encoding="utf-8")) if cfg.exists() else {}
    except Exception:
        d = {}
    d["aitrans_thread"] = int(n)
    d["aitrans_context"] = False   # True = nhét cả file vào 1 lần -> trôi nặng
    d["aisendsrt"] = bool(send_srt)
    try:
        cfg.write_text(_json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        return False
    return True


def set_ollama_config(model=OLLAMA_DEFAULT_MODEL, api_url=OLLAMA_API):
    """Ollama phơi API tương thích OpenAI ở /v1 nên dùng thẳng kênh Local LLM.
    localllm_key phải khác rỗng: thư viện openai từ chối key rỗng, còn Ollama
    thì không kiểm nên giá trị gì cũng được."""
    _write_pvt_params(localllm_api=api_url, localllm_model=model, localllm_key="ollama")
    set_ai_batch(AI_BATCH_OLLAMA, send_srt=False)


def get_ollama_model():
    """Model Ollama DANG duoc cau hinh (do nguoi dung chon o UI). '' neu chua co."""
    return (_read_pvt_param("localllm_model", "") or "").strip()


def ollama_unload(model=None, ly_do="trước bước lồng tiếng"):
    """Đẩy model Ollama ra khỏi RAM ngay, không đợi hết keep_alive mặc định (5 phút).

    qwen2.5:14b chiếm 8,4 GB và Ollama giữ nguyên trong RAM suốt job. Máy 24 GB
    thì tới bước 3-4 (LaMa/PyTorch + ffmpeg ghép video) là vượt trần: đo thực tế
    macOS đã giết cả Ollama lẫn web server lúc 17:48, mất trắng 48 phút xoá sub
    đã chạy xong trước đó. Dịch xong là không cần model nữa -> trả RAM luôn.
    """
    import json as _json
    import urllib.request
    model = model or _read_pvt_param("localllm_model", OLLAMA_DEFAULT_MODEL)
    api = _read_pvt_param("localllm_api", OLLAMA_API).rstrip("/")
    base = api[:-3].rstrip("/") if api.endswith("/v1") else api
    try:
        req = urllib.request.Request(
            f"{base}/api/generate",
            data=_json.dumps({"model": model, "keep_alive": 0}).encode(),
            method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30):
            pass
        print(f"[RAM] đã đẩy {model} khỏi bộ nhớ {ly_do}", flush=True)
        return True
    except Exception as e:
        print(f"[RAM] không đẩy được model Ollama khỏi bộ nhớ: {e}", flush=True)
        return False


def ollama_models():
    """Danh sách model đang có trong Ollama. Máy chưa chạy Ollama -> [] (UI sẽ
    ghi rõ chưa sẵn sàng thay vì để người dùng chọn xong mới ăn lỗi)."""
    import json as _json
    import urllib.request
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2) as r:
            return [m["name"] for m in _json.loads(r.read()).get("models", [])]
    except Exception:
        return []


# --- Làm sạch bản dịch trước khi đưa xuống phụ đề & lồng tiếng ----------------
# Model local trả về rác theo 3 kiểu, cả 3 đều đo được trên job thật:
#   1. Bọc từng dòng trong "<...>" (bắt chước ví dụ placeholder của prompt gốc).
#      ElevenLabs đọc dòng bọc ngoặc như markup -> không phát ra tiếng -> alignment
#      dồn cả cụm về MỘT mốc -> el_clone cắt đoạn 0 giây -> ffmpeg exit 234.
#   2. Lọt nguyên chữ Hán ("ông没事", "下去 xem cho kỹ"). Đo qwen2.5:14b: 2-3 dòng
#      lọt ở CẢ 3/3 lượt chạy trên cùng 12 câu -> đây là lỗi hệ thống, không phải
#      xui. Giọng Việt không đọc được chữ Hán, mà phụ đề hiện ra thì lộ hẳn.
#   3. Đưa 2 phương án ngăn bằng "|" ("...交给我们。| ...我们来处理。").
# Hạ nguồn không có cách nào phân biệt rác với nội dung thật, nên phải chặn ở đây.
CJK_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿぀-ヿ가-힯]")
# Dau cau Trung nam o khoi Unicode KHAC voi chu Han nen khong lot luoi CJK_RE,
# de nguyen thi phu de hien "Chan\u3002" rat lo. Quy doi thay vi xoa: dau van mang
# thong tin ngat cau cho ca nguoi doc lan bo cat dong.
_CJK_PUNCT = str.maketrans({
    "\u3002": ".", "\uff0c": ",", "\u3001": ",", "\uff01": "!",
    "\uff1f": "?", "\uff1b": ";", "\uff1a": ":", "\uff08": "(",
    "\uff09": ")", "\u3010": "(", "\u3011": ")", "\u300a": '\"',
    "\u300b": '\"', "\u300c": '\"', "\u300d": '\"', "\u300e": '\"',
    "\u300f": '\"', "\u3000": " ", "\uff5e": "~",
})
_WRAP_RE = re.compile(r"^\s*<\s*(.+?)\s*>\s*$|^\s*\[\s*(.+?)\s*\]\s*$", re.S)
_STRAY_TAG_RE = re.compile(r"</?\s*TRANSLATE_TEXT\s*>", re.I)


def _strip_wrappers(text):
    """Bóc lớp vỏ <...> / [...] bọc TRỌN dòng. Lặp vì có khi bọc lồng nhau."""
    t = _STRAY_TAG_RE.sub("", text).strip()
    for _ in range(3):
        m = _WRAP_RE.match(t)
        if not m:
            break
        t = (m.group(1) or m.group(2) or "").strip()
    return t


def _co_chu_dinh(text):
    """Chu thuong dinh NGAY chu HOA, khong dau cach -> manh ngoai ngu bi dan vao.

    Do 11/9/2026: qwen2.5:7b tra ve "...ghe o to nay da sach het roi, lam
    saoRepair it? ..." - mot manh tieng Anh dinh vao giua cau tieng Viet. Loai
    loi nay di thang vao video vi khong buoc nao sau do bat duoc.

    Bat HAI dang dinh:
      1. chu thuong lien chu hoa  -> "lam saoRepair it?"
      2. dau cau lien chu hoa     -> "Vang, nhu vay.That"
    Dang 2 tim ra sau, luc do preset the loai: luat chi bat dang 1 de lot.

    Tieng Viet khong bao gio co chu thuong dinh lien chu hoa trong cung mot tu,
    va sau dau cau thi luon co dau cach, nen luat nay rat sac. Do tren 543 dong
    phu de that (9 file, ca ban truoc va sau khi soat): bao dung 2 dong, ca hai
    deu la dong hong. Khong bao nham lan nao. Ngoai le co the gap la ten thuong
    hieu kieu "iPhone"; bi chan thi chi giu nguyen cau cu, khong mat gi.
    """
    if any(text[i].islower() and text[i + 1].isupper()
           for i in range(len(text) - 1)):
        return True
    return bool(re.search(r'[.,;:!?]["\')\]]?[A-ZĐÀ-Ỹ]', text))


def _candidate_ok(cand, ask):
    """Ban dich lai chi dung duoc khi khong nuot mat noi dung.

    Do tren job that: dua nguyen mot cau dai lan chu Han cho qwen, no tra ve mot
    ban viet lai NGAN hon nhieu ("...ong di doc sach, ong<40 chu Han>" -> chi con
    hai bien the ngan trong ngoac kep). Cau ngan thi ti le do vo nghia (dich ra
    tieng Viet thuong dai hon ban Trung), nen chi chan o cau du dai.
    """
    if not cand:
        return False
    if _co_chu_dinh(cand):
        return False
    return not (len(ask) >= 40 and len(cand) < 0.6 * len(ask))


def _clean_cjk(text):
    """Xoa han chu Han con sot, don khoang trang, cat dau cau thua hai dau."""
    return re.sub(r"\s{2,}", " ", CJK_RE.sub("", text)).strip(" ,.;:!?-").strip()


# Model đưa nhiều phương án dịch cho cùng một câu. Đã gặp HAI kiểu ngăn cách
# trên job thật: bằng "|" ("...交给我们。| ...我们来处理。") và bằng ',:' kèm ngoặc
# kép ('lòng ta như,:"hở ra như bị"trái tim tan vỡ",:"trái tim ta như tan vỡ"').
# Cả hai đều sẽ bị đọc thành tiếng nếu không chặn. ',:' không xuất hiện trong
# tiếng Việt tự nhiên nên cắt ở đó là an toàn.
_ALT_RE = re.compile(r"\||,\s*:")


def _cut_alternatives(text):
    """Lấy phương án ĐẦU, bỏ các phương án model đưa thêm."""
    m = _ALT_RE.search(text)
    if not m:
        return text
    head = text[:m.start()].strip().strip('"\u201c\u201d').strip()
    return head or text


def _read_pvt_param(key, default=""):
    import json as _json
    pv = _pvt_params_path()
    if not pv.exists():
        return default
    try:
        return _json.loads(pv.read_text(encoding="utf-8")).get(key) or default
    except Exception:
        return default


def _llm_once(prompt, translate_type, timeout=120, model=None):
    """Gọi thẳng engine dịch cho MỘT câu hỏi. -> text, hoặc None nếu không gọi được.

    Cố tình không đi qua pyvideotrans: ở đây chỉ cần dịch lại vài dòng lẻ, dựng
    lại cả pipeline dịch của nó vừa chậm vừa kéo theo mọi hành vi batch đang lỗi.
    """
    import json as _json
    import urllib.request
    try:
        if translate_type == TRANS_OLLAMA:
            body = {"model": model or _read_pvt_param("localllm_model", OLLAMA_DEFAULT_MODEL),
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2, "stream": False}
            api = _read_pvt_param("localllm_api", OLLAMA_API).rstrip("/")
            req = urllib.request.Request(f"{api}/chat/completions",
                                         data=_json.dumps(body).encode(), method="POST",
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return _json.loads(r.read())["choices"][0]["message"]["content"]
        if translate_type == TRANS_GEMINI:
            key = get_gemini_key()
            if not key:
                return None
            model = _read_pvt_param("gemini_model", GEMINI_DEFAULT_MODEL)
            url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{model}:generateContent?key={key}")
            body = {"contents": [{"parts": [{"text": prompt}]}]}
            req = urllib.request.Request(url, data=_json.dumps(body).encode(),
                                         method="POST",
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = _json.loads(r.read())
            return d["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print(f"[sạch] gọi lại engine dịch hỏng: {e}", flush=True)
    return None


# --- Preset the loai noi dung ---------------------------------------------
# PeiPei Dub co dropdown "The loai video" (Tu tien/Tien hiep, Kiem hiep, Do thi,
# Ngon tinh...) va ban dich trong quang cao cua ho giu dung tong chu, thieu tong
# chu, phu than, lao tu, xung ho nhat quan ca doan. Do la thu vá dung loi
# Mazino phan nan: "con nhieu doan rat suong, loi danh xung".
#
# CHI nap vao HAI luot soat (soat_glossary_srt + viet_hoa_srt). Ca hai chay bang
# qwen2.5, la model BIET NGHE LENH, nen dat van xuoi tieng Anh trong prompt la
# an toan.
#
# TUYET DOI KHONG nap vao _RETRY_PROMPT. Prompt do di thang toi Hunyuan o buoc
# don ban dich (_llm_once model=None -> localllm_model), ma Hunyuan DICH LUON
# moi cau tieng Anh no thay trong prompt. Da dinh 3 lan trong mot toi vi bai
# hoc nay - xem ghi chu trong videotrans/translator/_localllm.py.
THE_LOAI = {
    "": "",

    "tu-tien": """Genre: Chinese cultivation drama (tu tiên / tiên hiệp).
- Pronouns are archaic, NEVER modern. Use ta/ngươi between equals or from a
  superior; tại hạ/các hạ when being polite; lão phu for an old man speaking of
  himself; đệ tử when addressing a master. NEVER "bạn", "anh/em", "cậu/tớ".
- Keep Hán-Việt terms: tông chủ, thiếu tông chủ, trưởng lão, tông môn, đại tỷ,
  phụ thân, mẫu thân, đệ tử, sư phụ, sư huynh, sư đệ, tu vi, linh khí, pháp bảo,
  phế vật, lão tử.
- Never use modern slang (ok, chuẩn, xịn, oke). The register is formal and old.""",

    "kiem-hiep": """Genre: wuxia (kiếm hiệp / võ hiệp).
- Pronouns: tại hạ, các hạ, ta/ngươi, lão phu. NEVER "bạn" or "anh/em".
- Keep Hán-Việt terms: đại hiệp, bang chủ, chưởng môn, võ lâm, giang hồ, nội
  công, khinh công, chiêu thức, sư phụ, đệ tử.
- Register is formal and old, no modern slang.""",

    "do-thi": """Genre: modern city drama (đô thị / hiện đại).
- Pronouns are everyday modern Vietnamese: anh, em, tôi, cậu, ông, bà, chú, cô.
  Pick by age and closeness, then keep the SAME pair for the same two people.
- Personal names still use Hán-Việt readings, never pinyin.
- Plain modern Vietnamese. No archaic words (ta/ngươi, tại hạ).""",

    "ngon-tinh": """Genre: romance (ngôn tình / lãng mạn).
- Between the couple use anh/em and keep it stable; never switch to tôi/bạn
  mid-scene.
- Warm, soft register. Avoid crude words unless the source is crude.
- Personal names use Hán-Việt readings, never pinyin.""",

    "hai-doi-thuong": """Genre: comedy / everyday life (hài, đời thường, vlog).
- NEVER "bạn". It is the one word that makes the dub sound like a machine.
- Choose the pronoun from WHO is speaking to WHOM, do not apply one pair to
  everything:
    close friends teasing each other  -> mày/tao
    friendly but not that close       -> ông/bà, ông ơi, bà ơi
    a stranger, a shop or hotel staff -> anh/chị, anh ơi, chị ơi
    speaking to the camera            -> mình and cả nhà
  Once a pair is chosen for two people, keep it for the rest of the video.
- If the line has NO pronoun in it, do not add one. "Cảm ơn" stays "Cảm ơn",
  never becomes "cảm ơn mày".
- Keep interjections alive: Ối giời, Má ơi, Ối, trời đất ơi.
- Short punchy lines. This is spoken comedy, not narration.""",

    "am-thuc": """Genre: food and cooking (ẩm thực / nấu ăn).
- Speaker talks to the viewer: dùng "mình" cho người nói, "các bạn" hoặc "cả
  nhà" cho người xem. Keep it warm and casual.
- Keep cooking words concrete: xào, hầm, chiên, nêm, ướp, đảo đều, lửa lớn.
- Personal names use Hán-Việt readings, never pinyin.""",
}


def _khoi_the_loai(khoa):
    """Khoi van ban the loai de chen vao prompt. Rong = khong chi dinh."""
    noi_dung = THE_LOAI.get((khoa or "").strip(), "")
    if not noi_dung:
        return "(khong chi dinh the loai)"
    return noi_dung


def _the_loai_dang_chon():
    """Doc the_loai tu config.json. Khoa la -> coi nhu khong chi dinh."""
    try:
        k = (load_config().get("the_loai") or "").strip()
    except Exception:
        return ""
    return k if k in THE_LOAI else ""


_RETRY_PROMPT = """Translate this ONE Chinese video-subtitle line into casual spoken Vietnamese.

HARD RULES:
- Answer with the Vietnamese translation ONLY. One single line.
- NO quotes, NO angle brackets, NO square brackets, NO tags, NO explanation.
- Give ONE version only. Never offer alternatives separated by "|" or "/".
- ZERO Chinese/Japanese characters may appear in your answer.
- Casual spoken register (mày/tao, ông ơi, Ối giời), never textbook Vietnamese,
  never "Bạn" for friends joking around.
- Names use Hán-Việt readings, never pinyin: 小白=Tiểu Bạch, 白天鹏=Bạch Thiên Bằng,
  张若雪=Trương Nhược Tuyết. 块钱/元/人民币 = "tệ".

LINE: {line}"""


def _retranslate_line(source_text, translate_type, tries=2):
    """Dich lai 1 dong -> (ban sach hoac None, ung vien tot nhat).

    Tra ve CA ung vien chua sach: qwen hay dich dung y ma van dinh lai 1-2 chu
    Han ("May chan muon chet le."). Bo di thi phai lui ve ban goc con te hon;
    giu lai roi xoa chu Han thi duoc cau dung duoc.
    """
    best = ""
    for _ in range(tries):
        out = _llm_once(_RETRY_PROMPT.format(line=source_text), translate_type)
        if not out or not out.strip():
            break
        cand = _cut_alternatives(_strip_wrappers(out.strip().splitlines()[0]))
        if not cand:
            continue
        if not CJK_RE.search(cand):
            return cand, cand
        if not best or len(CJK_RE.findall(cand)) < len(CJK_RE.findall(best)):
            best = cand
    return None, best


# --- Soat lai theo glossary ------------------------------------------------
# Hunyuan-MT doc glossary trong prompt roi VAN bo qua o mot so cho, va sai theo
# kieu doi han nghia. Do 10/9/2026 tren video that:
#   你大爷 (chui) -> "Ong oi" (goi le phep)   <- dao nguoc sac thai
#   幺零八 (so phong 108) -> mat han ca ve
# Regex khong cuu duoc vi khong co quy luat trat tu; prompt cung khong (glossary
# DA nam trong prompt, da thu 3 kieu). Nen: dich xong thi soat lai, cue nao
# thieu tu bat buoc thi dich lai RIENG cue do voi tu duoc nhac thang vao prompt.
#
# CHI soat nhung tu ma dich chech la HONG NGHIA. Co tinh KHONG soat cac tu ma
# dong nghia van chap nhan duoc (哎呀="Oi gioi" nhung "Oi troi" cung dung,
# 大哥="ong oi" nhung "anh oi" cung dung) - ep nhung tu do chi lam ban dich cung
# nhac di, va de gay dich lai vo ich.
# Tran do dai cho ban dich lai, tinh theo THOI GIAN cue co - khong tinh theo do
# dai ban cu, vi ban cu thuong ngan chinh VI no bo sot noi dung.
# Do tren video that (64 cue): trung vi 14,1 ky tu/giay, muc 90% la 22,2. Lay 18
# - noi hon trung vi de con cho nhet tu bat buoc vao, nhung khong toi muc doc
# khong kip. el_clone da bao 23 cau phai nen nhanh nen khong duoc nong hon.
KY_TU_MOI_GIAY = 18

_NHAY_DOI = (('"', '"'), ('\u201c', '\u201d'), ("'", "'"), ('\u2018', '\u2019'), ('\u00ab', '\u00bb'))


def _boc_nhay(t):
    """Bo cap dau nhay bao TRON dong. Nhay giua cau thi giu nguyen."""
    t = t.strip()
    for mo, dong in _NHAY_DOI:
        if len(t) > 1 and t.startswith(mo) and t.endswith(dong) and dong not in t[1:-1]:
            return t[1:-1].strip()
    return t


# Model dung RIENG cho buoc soat glossary. Khong dung lai model dang dich vi
# Hunyuan-MT KHONG lam duoc viec nay: do 10/9/2026, 3 ca that, 3 luot moi ca,
# no tra ve Y HET NHAU moi luot (tat dinh, nen thu lai vo ich) va deu tranh tu
# bat buoc - 你大爷 no dich thanh "Oi troi oi" chu nhat dinh khong chiu viet
# "bo may". qwen2.5:14b cung 3 ca do: 6/6 dat.
# Bang gia tri: model biet NGHE LENH thi lam duoc viec sua loi; model chuyen
# dich thi dich hay hon nhung khong sai bao duoc. Dung moi con mot viec.
#
# 7b DUNG TRUOC 14b. Do 11/9/2026 tren job 35889c8e3580 (83 cue, 7 cue thieu tu
# bat buoc), cung mot file, cung hai luot soat:
#   - diem glossary BANG NHAU: ca hai vá 6/7, truot o hai cue khac nhau.
#   - 7b: 71 giay. 14b: 176 giay.
#   - 14b can 9,0 GB nhung may chi con ~9,7 GB trong -> chay xong con 3,1 GB.
#     Da lam may sap hai lan truoc do. Mot luot soat bi sap thi chat luong bang
#     KHONG, khong phai cao hon.
# 14b viet tieng Viet tu nhien hon that (no viet lai ca cau, 7b hay chi doi dai
# tu roi de nguyen), nhung khoang cach do va duoc bang prompt, con RAM thi
# khong. Giu 14b trong danh sach de ai co may khoe van dung duoc.
GLOSSARY_MODEL_UU_TIEN = ("qwen2.5:7b", "qwen2.5:14b", "gemma3:12b")


# Model DICH CHUYEN DUNG. Ban sao cua MT_MODEL_RE trong
# videotrans/translator/_localllm.py - hai file chay o HAI tien trinh va HAI
# venv khac nhau nen khong import cheo duoc. Sua ben nay thi sua ca ben kia.
MT_MODEL_RE = re.compile(
    r'(hunyuan[-_]?mt|qwen[-_]?mt|nllb|opus[-_]mt|madlad|tower[-_]?instruct|seamless)',
    re.I)


def _chon_model_soat(translate_type):
    """Model rieng de soat. None = dung chinh engine dang chay, KHONG phai bo qua.

    Truoc day co them dieu kien `m != dang_dung` de khong dung lai model dang
    dich. Dieu kien do vo nghia: danh sach uu tien chi chua model biet nghe
    lenh, ma Hunyuan-MT khong bao gio nam trong do. Truong hop duy nhat no kich
    hoat la khi qwen vua dich vua soat - luc do dung lai chinh no HOAN TOAN on,
    vi day la hai viec khac nhau (dich ca lo vs sua mot dong theo luat). Bo di
    de log ghi dung ten model thay vi "(engine dang dung)" mo ho.
    """
    if translate_type != TRANS_OLLAMA:
        return None                     # Gemini: dung luon chinh no
    co = set(ollama_models())
    for m in GLOSSARY_MODEL_UU_TIEN:
        if m in co:
            return m
    return None


def _bo_qua_soat(ten_buoc, translate_type, model):
    """Buoc soat co nen dung lai khong. Tra True = dung, va DA in ly do.

    Do 12/9/2026: mot job chay 15 phut roi tut xuong Google, hai luot soat bo
    qua ma khong in mot chu nao. Chi phat hien ra khi doc lai code. Bo qua thi
    duoc, bo qua trong im lang thi khong.
    """
    if translate_type not in (TRANS_OLLAMA, TRANS_GEMINI):
        print(f"[{ten_buoc}] BỎ QUA — engine dịch hiện tại không gọi lại được từng "
              f"dòng. Bước này chỉ chạy với Ollama hoặc Gemini.", flush=True)
        return True
    if translate_type == TRANS_OLLAMA and not model:
        dang = _read_pvt_param("localllm_model", "") or "(chưa đặt)"
        print(f"[{ten_buoc}] BỎ QUA — máy không có model nào biết nghe lệnh. "
              f"Model đang dịch là {dang}; model dịch chuyên dụng đã đo là KHÔNG "
              f"sửa được lỗi theo luật (3 ca, 3 lượt mỗi ca, hỏng cả 9). "
              f"Bật lại bằng: ollama pull qwen2.5:7b", flush=True)
        return True
    return False


GLOSSARY_BAT_BUOC = (
    "白天鹏", "白天蓬", "雪莲", "张若雪", "小白",   # ten rieng - phai dung y het
    "你大爷",                                      # chui - dich chech la dao nghia
    "幺零八",                                      # so phong - rot la mat thong tin
    "一秒入睡",                                    # ten tro dua chay suot video
)

# Cac khoi lenh phai dat TRUOC "LINE:", de cau can dich la thu CUOI CUNG model
# nhin thay. Da mac loi nay 10/9: ghep them huong dan vao SAU "LINE:" thi
# Hunyuan bo qua sach - no dich thu nam cuoi prompt chu khong phai thu duoc gan
# nhan. Cung mot bai hoc voi khoi vi du va khoi ngu canh.
_RETRY_GLOSSARY_PROMPT = _RETRY_PROMPT.replace("LINE: {line}", """MANDATORY TERMS — the answer MUST contain these exact Vietnamese words:
{terms}

LENGTH LIMIT — this line is dubbed into a fixed {giay:.1f}s slot. Your answer
must be at most {tran} characters. Cut every word that is not needed; keep the
mandatory terms. A line that does not fit is worse than a plain one.

LINE: {line}""")


def _doc_glossary():
    """glossary.txt -> {tu_trung: tu_viet}. Thieu file thi tra ve rong."""
    f = PVT_DIR / "videotrans" / "glossary.txt"
    if not f.exists():
        return {}
    ra = {}
    for ln in f.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
        if "=" in ln and not ln.strip().startswith("#"):
            a, b = ln.split("=", 1)
            if a.strip() and b.strip():
                ra[a.strip()] = b.strip()
    return ra


def _tu_con_thieu(nguon, ban_dich, glos):
    """Tu bat buoc co trong cau NGUON ma ban dich khong co. -> list tu Viet."""
    thap = ban_dich.lower()
    thieu = []
    for k in GLOSSARY_BAT_BUOC:
        v = glos.get(k)
        if v and k in nguon and v.lower() not in thap:
            # 你大爷 chua 大爷: neu ca hai cung khop thi chi giu cai DAI hon,
            # vi tu dai la nghia dung (你大爷=bo may, khong phai 大爷=bac).
            if any(k in k2 and k2 != k and k2 in nguon for k2 in GLOSSARY_BAT_BUOC):
                continue
            thieu.append(v)
    return thieu


def soat_glossary_srt(srt_path, source_srt, translate_type, tries=2):
    """Dich lai cac cue thieu tu bat buoc. -> dict thong ke.

    Chi chay voi engine goi lai duoc (Ollama/Gemini). Ban dich moi chi duoc
    nhan khi no THAT SU co du tu con thieu va khong nuot noi dung.
    """
    st = {"soat": 0, "sua": 0, "model": ""}
    if _bo_qua_soat("glossary", translate_type, _chon_model_soat(translate_type)):
        return st
    glos = _doc_glossary()
    if not glos:
        return st
    cues = parse_srt(srt_path)
    src = parse_srt(source_srt) if source_srt and Path(source_srt).exists() else []
    if not cues or not src:
        return st
    smap = {a: t for a, _b, t in src}

    # Quet TRUOC de biet co viec khong: khong co cue nao thieu thi khong dong
    # toi model, khoi nap 9 GB vo ich.
    can_soat = [(a, b, t) for a, b, t in cues
                if smap.get(a) and _tu_con_thieu(smap[a], t, glos)]
    if not can_soat:
        return st
    model = _chon_model_soat(translate_type)
    st["model"] = model or "(engine dang dung)"
    if model and model != _read_pvt_param("localllm_model", ""):
        # Nha model dich TRUOC khi nap model soat: 4,6 GB + 9 GB cung luc la
        # dung lai dung cai OOM da giet job hai lan hom 8/9. Trung model thi
        # khong nha: nha xong nap lai dung thang do chi ton them thoi gian.
        ollama_unload(ly_do="để nhường chỗ cho model soát glossary")

    ra = []
    for start, end, text in cues:
        nguon = smap.get(start, "")
        thieu = _tu_con_thieu(nguon, text, glos) if nguon else []
        if thieu:
            st["soat"] += 1
            giay = max(0.1, (end - start) / 1000)
            # Khong bao gio chat hon ban dang co: neu ban cu von da dai hon tran
            # thi it nhat cho ban moi bang no.
            tran = int(max(40, giay * KY_TU_MOI_GIAY, len(text)))
            prompt = _RETRY_GLOSSARY_PROMPT.format(
                line=nguon, terms="\n".join(f'- "{t}"' for t in thieu),
                giay=giay, tran=tran)
            # Model phi tat dinh: cung mot prompt, luot nay bo quen tu bat buoc,
            # luot sau lai co. Do 10/9: 1 luot chi dat 1/4 cue. Nen thu lai vai
            # luot va lay ban DAU TIEN dat ca hai dieu kien (du tu + vua do dai).
            cand = ""
            for _ in range(max(1, tries)):
                out = _llm_once(prompt, translate_type, model=model)
                c = _cut_alternatives(_strip_wrappers(out.strip().splitlines()[0])) if out and out.strip() else ""
                if not c:
                    continue
                c = _boc_nhay(c.translate(_CJK_PUNCT))
                if (all(t.lower() in c.lower() for t in thieu) and len(c) <= tran
                        and not CJK_RE.search(c) and _candidate_ok(c, nguon)):
                    cand = c
                    break
                cand = cand or c          # giu ban dau lam ung vien bao loi
            du = cand and all(t.lower() in cand.lower() for t in thieu)
            vua_dai = cand and len(cand) <= tran
            if du and vua_dai and not CJK_RE.search(cand) and _candidate_ok(cand, nguon):
                text = cand
                st["sua"] += 1
            else:
                vi_sao = ("qua dai" if cand and not vua_dai else
                          "khong co du tu" if cand else "khong goi duoc model")
                print(f"[glossary] cue {start}ms thieu {thieu} - dich lai {vi_sao}, giu ban cu",
                      flush=True)
        ra.append((start, end, text))

    if model:
        ollama_unload(model, ly_do="(soát glossary xong)")
    if st["sua"]:
        Path(srt_path).write_text(
            "\n".join(f"{i}\n{_ms_to_srt_ts(a)} --> {_ms_to_srt_ts(b)}\n{c}\n"
                       for i, (a, b, c) in enumerate(ra, 1)),
            encoding="utf-8")
    return st

# --- Tang "Viet hoa": sua van phong cho ca file --------------------------
# Model dich 7B (Hunyuan-MT va ca ban Chimera - do 10/9, ket qua y het nhau)
# dich DUNG NGHIA nhung khong theo luat van phong: 17 lan "ban", 0 lan "may/tao",
# xung ho doi giua cac cue lien nhau. Prompt khong sua duoc, doi model cung khong.
#
# Nhung qwen2.5:14b thi NGUOC LAI: bat no dich ca lo thi vo vun (lan chu Han,
# dong rong, 22 phut/video) - do 10/9; con bat no sua TUNG CAU kem menh lenh ro
# thi 6/6 dat o buoc soat glossary. Nen tang nay giao dung viec no lam duoc:
# khong dich, chi VIET LAI cho dung giong, tung cau mot.
#
# Khac buoc soat glossary o cho: buoc kia chi dung vao cue thieu tu bat buoc
# (~4/64), tang nay quet HET moi cue.
VIET_HOA_MODEL_UU_TIEN = GLOSSARY_MODEL_UU_TIEN
VIET_HOA_NGU_CANH = 2          # so cau da sua dua vao lam mau xung ho

_VIET_HOA_PROMPT = """You rewrite Vietnamese subtitle lines so they sound like real
spoken Vietnamese. You are NOT translating: the meaning is already correct.

{luat}

# GENRE — match this register and terminology
{the_loai}

# WHAT TO DO
Rewrite the line in CURRENT so that it obeys the rules above — above all the
pronoun rules. Keep the meaning of SOURCE exactly: add nothing, drop nothing.

# HARD RULES
- Output ONLY the rewritten Vietnamese line. One line. Nothing else.
- No quotes, no brackets, no tags, no explanation, no alternatives.
- ZERO Chinese/Japanese/Korean characters.
- At most {tran} characters — this line is dubbed into a {giay:.1f}s slot.
- If CURRENT already obeys the rules, output it back unchanged.

# WORDS YOU MUST KEEP EXACTLY (they come from the project glossary)
{giu}

# PRONOUNS ALREADY USED (reference only — never output these lines)
{ngu_canh}

SOURCE (Chinese): {nguon}
CURRENT (Vietnamese): {hien_tai}"""


def _viet_hoa_hop_le(cand, hien_tai, nguon, tran, phai_giu=()):
    """Ban viet lai co dung duoc khong. Chan moi kieu hong da gap."""
    if not cand or CJK_RE.search(cand):
        return False
    # Khong duoc pha thanh qua cua buoc soat glossary. Do 10/9: tang Viet hoa
    # bien "bo may" (chui, dung glossary) nguoc lai thanh "bo oi" - lam mem
    # dung cai vua sua duoc, va lam am tham.
    if any(t.lower() not in cand.lower() for t in phai_giu):
        return False
    if len(cand) > tran:
        return False
    # Model doi khi tra ve loi giai thich thay vi cau dich.
    if re.search(r'^(here|sure|i |the line|ban dich|bản dịch)', cand, re.I):
        return False
    # Nuot noi dung: cau dai ma bi rut qua nua thi gan nhu chac chan mat y.
    if len(hien_tai) >= 40 and len(cand) < 0.6 * len(hien_tai):
        return False
    return _candidate_ok(cand, nguon)


def viet_hoa_srt(srt_path, source_srt, translate_type, tries=2, the_loai=None):
    """Viet lai ca file cho dung van phong tieng Viet. -> dict thong ke."""
    st = {"quet": 0, "sua": 0, "model": ""}
    if _bo_qua_soat("Việt hoá", translate_type, _chon_model_soat(translate_type)):
        return st
    cues = parse_srt(srt_path)
    src = parse_srt(source_srt) if source_srt and Path(source_srt).exists() else []
    if not cues or not src:
        return st
    smap = {a: t for a, _b, t in src}
    glos = _doc_glossary()
    khoi_tl = _khoi_the_loai(_the_loai_dang_chon() if the_loai is None else the_loai)
    model = _chon_model_soat(translate_type)
    st["model"] = model or "(engine dang dung)"
    if model and model != _read_pvt_param("localllm_model", ""):
        ollama_unload(ly_do="để nhường chỗ cho model Việt hoá")

    ra = []
    da_sua = []
    for start, end, text in cues:
        nguon = smap.get(start, "")
        if not nguon or not text.strip():
            ra.append((start, end, text))
            continue
        st["quet"] += 1
        giay = max(0.1, (end - start) / 1000)
        tran = int(max(40, giay * KY_TU_MOI_GIAY, len(text)))
        # Tu bat buoc DA co trong ban hien tai thi phai giu nguyen.
        phai_giu = tuple(v for k, v in glos.items()
                         if k in GLOSSARY_BAT_BUOC and v.lower() in text.lower())
        prompt = _VIET_HOA_PROMPT.format(
            luat=VI_PROMPT_RULES.strip(), tran=tran, giay=giay, the_loai=khoi_tl,
            ngu_canh="\n".join(da_sua[-VIET_HOA_NGU_CANH:]) or "(chua co cau nao)",
            giu=("\n".join(f'- "{t}"' for t in phai_giu) if phai_giu
                 else "(khong co tu nao bat buoc)"),
            nguon=nguon, hien_tai=text)
        moi = ""
        for _ in range(max(1, tries)):
            out = _llm_once(prompt, translate_type, model=model)
            if not out or not out.strip():
                continue
            c = _boc_nhay(_cut_alternatives(
                _strip_wrappers(out.strip().splitlines()[0])).translate(_CJK_PUNCT))
            if _viet_hoa_hop_le(c, text, nguon, tran, phai_giu):
                moi = c
                break
        if moi and moi != text:
            text = moi
            st["sua"] += 1
        da_sua.append(text)
        ra.append((start, end, text))

    if model:
        ollama_unload(model, ly_do="(Việt hoá xong)")
    if st["sua"]:
        Path(srt_path).write_text(
            "\n".join(f"{i}\n{_ms_to_srt_ts(a)} --> {_ms_to_srt_ts(b)}\n{c}\n"
                       for i, (a, b, c) in enumerate(ra, 1)),
            encoding="utf-8")
    return st

# --- Sua ngu phap tieng Viet bang luat -------------------------------------
# Model dich chuyen dung (Hunyuan-MT) dich DUNG NGHIA nhung sai mot so quy tac
# TRAT TU cua tieng Viet, va sai y het nhau moi lan. Prompt da ghi ro luat
# (vi du "65.3度 -> 65 phay 3 do") ma no van khong theo - do la gioi han cua
# model 7B chuyen dich, khong phai loi prompt. Nhung loi nay CO QUY LUAT nen
# sua bang luat thi chac chan dung hon la nan ni model.
# Mazino chi ra 10/9/2026: "May lai dang choi tro gi vay nua?" phai la "...gi
# nua vay?", va "sau muoi lam do ba phay" phai la "sau muoi lam phay ba do".

_SO_CHU = r'(?:không|một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười|mươi|lăm|linh|lẻ|trăm|nghìn|ngàn|triệu|tư)'

# 1. So thap phan bi dao: "<so> độ <so> phẩy" -> "<so> phẩy <so> độ".
#    Bat ca chu so lan so viet bang chu.
_RE_THAP_PHAN = re.compile(
    rf'\b((?:\d+|{_SO_CHU}(?:\s+{_SO_CHU})*))\s+độ\s+((?:\d+|{_SO_CHU}(?:\s+{_SO_CHU})*))\s+phẩy\b',
    re.I)

# 2. Tieu tu cuoi cau bi dao: "... vậy nữa?" -> "... nữa vậy?"
#    Trong tieng Viet "nua" luon dung TRUOC tieu tu tinh thai cuoi cau.
_RE_TIEU_TU = re.compile(r'\b(vậy|thế|đấy|rồi)\s+(nữa)\b(?=\s*[?!.…,]|\s*$)', re.I)

# 3. Thieu dau cach sau dau phay (khong dung cho so kieu "1,5").
_RE_PHAY_DINH = re.compile(r',(?=[^\s\d])')


def _sua_ngu_phap_vi(t):
    """Sua cac loi TRAT TU co quy luat. -> (text_moi, so_cho_da_sua)"""
    goc = t
    t = _RE_THAP_PHAN.sub(lambda m: f'{m.group(1)} phẩy {m.group(2)} độ', t)
    t = _RE_TIEU_TU.sub(lambda m: f'{m.group(2)} {m.group(1)}', t)
    t = _RE_PHAY_DINH.sub(', ', t)
    return t, (0 if t == goc else 1)


def sanitize_translated_srt(srt_path, source_srt=None, translate_type=TRANS_GOOGLE,
                            tries=2):
    """Làm sạch .srt dịch TẠI CHỖ. -> dict thống kê để log.

    Thứ tự: bóc vỏ -> cắt phương án thừa -> dòng nào còn chữ Hán thì dịch lại
    (ưu tiên dịch lại từ câu GỐC nếu có file srt nguồn khớp số cue) -> vẫn còn
    thì xoá hẳn chữ Hán. Không bao giờ để dòng rỗng: parse_srt của el_clone bỏ
    qua cue rỗng, lệch số đoạn là hỏng cả bản lồng tiếng.
    """
    cues = parse_srt(srt_path)
    if not cues:
        return {"cues": 0, "unwrapped": 0, "cut_alt": 0, "cjk": 0, "fixed": 0,
                "stripped": 0, "grammar": 0}

    # Ghep voi cau GOC theo MOC THOI GIAN, khong theo chi so: pyvideotrans co the
    # lam mat han mot cue khi dich (do that: nguon 58 cue -> ban dich 57), tu do
    # tro di chi so lech het. Moc thoi gian thi khong doi - do lai tren job that:
    # 57/57 cue khop chinh xac tung mili giay.
    src = parse_srt(source_srt) if source_srt and Path(source_srt).exists() else []
    smap = {a: t for a, _b, t in src}

    st = {"cues": len(cues), "unwrapped": 0, "cut_alt": 0, "cjk": 0, "fixed": 0,
          "stripped": 0, "grammar": 0}
    out = []
    for i, (start, end, text) in enumerate(cues):
        t = _strip_wrappers(text)
        if t != text.strip():
            st["unwrapped"] += 1
        t2 = _cut_alternatives(t)
        if t2 != t:
            st["cut_alt"] += 1
        t = t2.translate(_CJK_PUNCT)

        if CJK_RE.search(t):
            st["cjk"] += 1
            # CHI dich lai khi tim duoc cau goc. Dua nguyen ban dich da hong cho
            # model "sua ho" thi no khong biet dang lam gi: do that, qwen tra ve
            # mot mo bien the lap lai con te hon ban hong ban dau.
            ask = smap.get(start, "")
            good, best = _retranslate_line(ask, translate_type, tries=tries) if (
                ask and translate_type in (TRANS_OLLAMA, TRANS_GEMINI)) else (None, "")
            if good and _candidate_ok(good, ask):
                st["fixed"] += 1
                t = good.translate(_CJK_PUNCT)
            else:
                # Thà mất mấy chữ còn hơn để chữ Hán lên phụ đề tiếng Việt và
                # bắt giọng Việt đọc thứ nó không đọc được.
                # Uu tien xoa tren ban dich lai (sat nghia hon), chi lui ve
                # ban cu khi khong co ung vien nao.
                cand = (_clean_cjk(best.translate(_CJK_PUNCT))
                        if _candidate_ok(best, ask) else "")
                t = cand or _clean_cjk(t)
                st["stripped"] += 1
                if not t:
                    t = "…"
        t, n_gp = _sua_ngu_phap_vi(t)
        st["grammar"] += n_gp
        out.append((start, end, t))

    Path(srt_path).write_text(
        "\n".join(f"{i}\n{_ms_to_srt_ts(a)} --> {_ms_to_srt_ts(b)}\n{c}\n"
                  for i, (a, b, c) in enumerate(out, 1)),
        encoding="utf-8")
    return st


# --- Độ dài đoạn nhận dạng (quyết định cả chất lượng dịch lẫn phụ đề) --------
# pyvideotrans gộp mọi cue ngắn hơn min_speech_duration_ms vào cue kề
# (recognition/_base.py:_phase1_merge_short). Mặc định 2000ms khiến gộp dây
# chuyền: đo trên video thật ra cue trung bình 12,3s, dài nhất 44,5s, 11/20 cue
# vượt 8s. Hậu quả kép:
#   1. Cả khối chữ đổ lên màn hình cùng lúc, che kín video.
#   2. Google dịch nguyên đoạn dài thì tên riêng không nhất quán — đo được
#      小白 ra "Tiểu Bạch" chỗ này, "Xiaobai" chỗ kia trong CÙNG một cue.
# Hạ xuống 1000ms: VAD vốn đã không phát đoạn ngắn hơn ngưỡng này nên gần như
# không còn gì để gộp -> cue nằm trong 1-5s = cỡ một câu trọn. KHÔNG hạ thấp
# hơn: dưới ~1s là rơi vào đúng kiểu vụn 0,28s của Whisper ("我看" -> "tôi
# thấy"), lúc đó mới thật sự mất ngữ cảnh.
SEG_MIN_SPEECH_MS = 1000
SEG_MAX_SPEECH_S = 5


# Nguong silero-VAD. Mac dinh 0.5 bo sot rat nang khi video co nhac nen to: do
# tren video that, doan 00:58-01:26 (27,6s) chi tim ra 2,2s tieng noi, trong khi
# CA HAI model ASR deu nghe ro thoai ("小白抢回来抓住他厉害啊兄弟"). Ha xuong 0.35
# -> bat duoc ~4,1s. Khong ha sau hon vi cang thap cang de nhan nham nhac nen
# thanh tieng noi; phan con lai de luoi vot (_recover_missed_speech) lo.
SEG_VAD_THRESHOLD = 0.35


# VAD tach tieng noi. silero bo sot rat nang khi nhac nen to: do tren video that
# no bo qua 118,7s tren tong 296s (40%). Phan bo sot roi vao luoi vot
# _recover_missed_speech(), von cat mu thanh khoi 8 giay -> cue 3 chu keo dai
# 8,0s, TTS doc 1s roi im 7s trong khi nguoi goc van dang noi. Do chinh la loi
# "voice lech so voi tieng goc". Doi sang TEN VAD tren cung video: 0 khoang
# trong >=3s, luoi vot khong phai chay lan nao, bat them 105 ky tu tieng Trung.
# Goi `ten_vad` phai co trong .venv cua pyvideotrans; thieu thi no tu quay ve
# silero, luc do loi cu quay lai ma khong bao gi.
SEG_VAD_TYPE = "tenvad"

# Khoang lang toi thieu truoc khi cat sang cue moi. 140ms la gia tri da dung
# suot cac lan do TEN VAD o tren, ghi lai day de may cai moi chay dung cau hinh
# da nghiem thu. Chua do rieng anh huong cua tung muc.
SEG_MIN_SILENCE_MS = 140


def tune_segmentation(min_speech_ms=SEG_MIN_SPEECH_MS, max_speech_s=SEG_MAX_SPEECH_S,
                      threshold=SEG_VAD_THRESHOLD, vad_type=SEG_VAD_TYPE,
                      min_silence_ms=SEG_MIN_SILENCE_MS):
    """Ghi ngưỡng cắt đoạn + loại VAD vào cfg.json của pyvideotrans mỗi lần chạy.

    Ghi lúc chạy chứ không sửa sẵn file vendor: bản đóng gói Windows KHÔNG bundle
    cfg.json (AppSettings tự tạo lại với default khi thiếu — xem ghi chú DATAS
    trong installer/pyvideotrans_cli.spec), nên sửa tay file vendor sẽ mất trên
    máy người dùng."""
    import json as _json
    cfg = PVT_DIR / "videotrans" / "cfg.json"
    try:
        d = _json.loads(cfg.read_text(encoding="utf-8")) if cfg.exists() else {}
    except Exception:
        d = {}
    before = d.get("min_speech_duration_ms")
    before_th = d.get("threshold")
    before_vad = d.get("vad_type")
    d["min_speech_duration_ms"] = int(min_speech_ms)
    d["max_speech_duration_s"] = int(max_speech_s)
    d["threshold"] = float(threshold)
    d["vad_type"] = str(vad_type)
    d["min_silence_duration_ms"] = int(min_silence_ms)
    try:
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(_json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:
        print(f"[cảnh báo] không ghi được cfg.json ({e}) — vẫn chạy với ngưỡng cũ", flush=True)
        return False
    if before_vad != str(vad_type):
        print(f"[doan] VAD {before_vad} -> {vad_type}", flush=True)
    if before != int(min_speech_ms) or before_th != float(threshold):
        print(f"[đoạn] min_speech {before} -> {min_speech_ms}ms, max_speech {max_speech_s}s, "
              f"ngưỡng VAD {before_th} -> {threshold}", flush=True)
    return True


def transcribe_translate_dub(input_video, work_dir, source_lang, target_lang,
                              model_name, voice_role, tts_type="0", recogn_type="0",
                              fix_punc=False, translate_type="0"):
    """recogn_type = kênh nhận dạng giọng nói của pyvideotrans (xem
    videotrans/recognition/__init__.py): 0=faster-whisper, 4=FireRedASR,
    20=ElevenLabs Scribe. model_name chỉ có nghĩa với faster-whisper; các kênh
    khác bỏ qua nó nhưng CLI vẫn bắt buộc có giá trị hợp lệ."""
    stage = "pyvideotrans transcribe/dịch/dub"
    tune_segmentation()
    pvt_out = work_dir / "pvt_out"
    pvt_out.mkdir(exist_ok=True)
    run([
        *PVT_CMD_BASE, "--task", "vtv",
        "--name", str(input_video),
        "--recogn_type", str(recogn_type),
        "--model_name", model_name or "large-v3",
        "--source_language_code", source_lang,
        "--target_language_code", target_lang,
        "--translate_type", str(translate_type),
        "--tts_type", str(tts_type),
        "--voice_role", voice_role,
        "--subtitle_type", "0",
        "--voice_autorate",
        "--output-dir", str(pvt_out),
        "--verbose",
    ] + (["--fix_punc"] if fix_punc else []), cwd=PVT_DIR, stage=stage, tail_lines=40)

    dub_audio = pvt_out / f"{target_lang}.m4a"
    dub_srt = pvt_out / f"{target_lang}.srt"
    if not dub_audio.exists() or not dub_srt.exists():
        raise PipelineStageError(
            stage,
            f"Không sinh ra file mong đợi trong {pvt_out} (cần {dub_audio.name} + {dub_srt.name}). "
            f"Kiểm tra lại mã ngôn ngữ (--source-lang/--target-lang) và voice_role có hợp lệ không.",
        )

    st = sanitize_translated_srt(dub_srt, source_srt=pvt_out / f"{source_lang}.srt",
                                 translate_type=str(translate_type))
    # Soat glossary PHAI chay truoc ollama_unload: no con phai goi lai model.
    sg = soat_glossary_srt(dub_srt, pvt_out / f"{source_lang}.srt", str(translate_type))
    if sg["soat"]:
        print(f"[glossary] {sg['soat']} cue thiếu từ bắt buộc -> sửa được {sg['sua']} "
              f"(model soát: {sg['model']})", flush=True)
    # Tang Viet hoa: chay SAU soat glossary, va co rao chan giu lai tu glossary
    # (do 10/9: khong co rao thi no bien "bo may" nguoc thanh "bo oi").
    vh = viet_hoa_srt(dub_srt, pvt_out / f"{source_lang}.srt", str(translate_type))
    if vh["quet"]:
        print(f"[Việt hoá] {vh['quet']} cue -> viết lại {vh['sua']} "
              f"(model: {vh['model']})", flush=True)
    if str(translate_type) == TRANS_OLLAMA:
        # Trả RAM TRƯỚC bước dub + ghép video, nếu không máy 24 GB sẽ bị OOM.
        ollama_unload()
    if st["unwrapped"] or st["cut_alt"] or st["cjk"]:
        print(f"[sạch] {st['cues']} cue: bóc vỏ {st['unwrapped']}, cắt phương án thừa "
              f"{st['cut_alt']}, lọt chữ Hán {st['cjk']} (dịch lại được {st['fixed']}, "
              f"phải xoá {st['stripped']})", flush=True)
        # Bản dub Edge-TTS do pyvideotrans sinh TRƯỚC bước này nên vẫn đọc theo
        # bản chưa sạch; phụ đề thì đã đúng. Đường ElevenLabs/F5 dựng lại giọng
        # TỪ file vừa làm sạch nên sạch cả tiếng lẫn chữ.
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


# --- Cắt phụ đề dài thành nhiều dòng chạy tuần tự -----------------------------
# FireRedASR/Scribe có thể trả 1 câu dài nhiều giây; đổ nguyên khối vào ô blur thì
# libass xuống dòng thành 7-8 dòng che kín màn hình. Cắt nhỏ theo số ký tự vừa ô
# rồi chia lại thời gian theo độ dài từng mẩu -> chữ chạy tuần tự, mỗi lúc 1-2 dòng.
SUB_MAX_LINES = 2
SUB_MIN_MS = 600          # dưới ngưỡng này người xem không kịp đọc
_SENT_END = (".", "?", "!", ";", ":", "…", ",")


def _srt_ts_to_ms(ts):
    hh, mm, rest = ts.split(":")
    ss, ms = rest.replace(".", ",").split(",")
    return ((int(hh) * 60 + int(mm)) * 60 + int(ss)) * 1000 + int(ms)


def _ms_to_srt_ts(ms):
    ms = max(0, int(ms))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    sec, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def parse_srt(path):
    """-> [(start_ms, end_ms, text)] . Bỏ qua block hỏng thay vì ném lỗi: 1 dòng
    xấu không đáng làm hỏng cả video."""
    out = []
    raw = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    for block in re.split(r"\n\s*\n", raw.strip()):
        lines = [l for l in block.splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        tl = next((l for l in lines if "-->" in l), None)
        if not tl:
            continue
        try:
            a, b = [x.strip() for x in tl.split("-->")]
            start, end = _srt_ts_to_ms(a), _srt_ts_to_ms(b)
        except Exception:
            continue
        text = " ".join(lines[lines.index(tl) + 1:]).strip()
        if text:
            out.append((start, end, text))
    return out


def split_text_chunks(text, max_chars):
    """Cắt ở ranh giới TỪ, ưu tiên chốt ngay sau dấu câu để mỗi mẩu là một ý trọn."""
    words = text.split()
    chunks, cur = [], ""
    for w in words:
        cand = f"{cur} {w}".strip()
        if len(cand) <= max_chars:
            cur = cand
            if cur.endswith(_SENT_END) and len(cur) >= max_chars * 0.45:
                chunks.append(cur)
                cur = ""
        else:
            if cur:
                chunks.append(cur)
            cur = w
    if cur:
        chunks.append(cur)

    # Gộp mẩu quá ngắn vào mẩu liền kề: để lại 1 từ mồ côi ("Xiaobai") đứng riêng
    # 1 dòng trông rất xấu. Cho phép vượt max_chars ~15% vì thà 1 dòng hơi dài
    # còn hơn 1 dòng trống trải.
    limit = max_chars * 1.15
    i = 0
    while i < len(chunks):
        if len(chunks[i]) >= max_chars * 0.35 or len(chunks) == 1:
            i += 1
            continue
        prev_ok = i > 0 and len(chunks[i - 1]) + 1 + len(chunks[i]) <= limit
        next_ok = i + 1 < len(chunks) and len(chunks[i]) + 1 + len(chunks[i + 1]) <= limit
        if prev_ok:
            chunks[i - 1] = f"{chunks[i - 1]} {chunks.pop(i)}"
        elif next_ok:
            chunks[i] = f"{chunks[i]} {chunks.pop(i + 1)}"
            i += 1
        else:
            i += 1
    return chunks or [text]


def split_long_subtitles(srt_path, out_path, max_chars):
    """Ghi ra .srt mới đã cắt nhỏ. Thời gian chia theo TỈ LỆ ĐỘ DÀI từng mẩu (mẩu
    dài chữ thì hiện lâu hơn) và không bao giờ lấn sang cue kế tiếp."""
    cues = parse_srt(srt_path)
    out = []
    for start, end, text in cues:
        if len(text) <= max_chars:
            out.append((start, end, text))
            continue
        parts = split_text_chunks(text, max_chars)
        total = sum(len(p) for p in parts) or 1
        dur = max(end - start, len(parts) * SUB_MIN_MS)
        t = start
        for i, part in enumerate(parts):
            share = round(dur * len(part) / total)
            e = (start + dur) if i == len(parts) - 1 else min(t + share, start + dur)
            if e - t < SUB_MIN_MS:
                e = t + SUB_MIN_MS
            out.append((t, e, part))
            t = e

    lines = []
    for i, (start, end, text) in enumerate(out, 1):
        lines.append(f"{i}\n{_ms_to_srt_ts(start)} --> {_ms_to_srt_ts(end)}\n{text}\n")
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")
    return out_path, len(cues), len(out)


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

    # Số ký tự tối đa cho 1 lần hiện, suy từ bề ngang thật của chỗ đặt chữ và cỡ
    # chữ sẽ dùng bên dưới (Arial: bề ngang trung bình ~0.5 * fontsize). Tính
    # trước để cắt .srt rồi mới đổi sang .ass -> mỗi cue chỉ còn 1-2 dòng.
    if sub_box is not None:
        _ymin, _ymax, _xmin, _xmax = sub_box
        _fs = max(14, round(max(1, _ymax - _ymin) * 0.40))
        _avail = max(1, _xmax - _xmin)
    else:
        _fs = max(16, round(height * 0.035))
        _avail = max(1, round(width * 0.92))
    max_chars = max(12, int(_avail / (_fs * 0.52)) * SUB_MAX_LINES)

    split_srt = work_dir / "split.srt"
    _, _before, _after = split_long_subtitles(srt_path, split_srt, max_chars)
    print(f"[phụ đề] tối đa {max_chars} ký tự/lần hiện -> {_before} cue thành {_after} cue",
          flush=True)

    run([FFMPEG_BIN, "-y", "-i", str(split_srt), str(ass_path)], stage=stage)

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


def _has_audio_stream(path):
    """True nếu file có ít nhất 1 audio stream.

    ffprobe lỗi -> False (an toàn: coi như không có tiếng gốc, video cuối vẫn ra
    được với mỗi giọng dub thay vì hỏng cả pipeline).
    """
    try:
        out = subprocess.run(
            [FFPROBE_BIN, "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
            check=True, capture_output=True, text=True,
        )
        return bool(out.stdout.strip())
    except Exception:
        return False


def _audio_channels(path):
    """Số kênh của audio stream đầu tiên. ffprobe lỗi -> 0 (không biết)."""
    try:
        out = subprocess.run(
            [FFPROBE_BIN, "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=channels", "-of", "csv=p=0", str(path)],
            check=True, capture_output=True, text=True,
        )
        return int(out.stdout.strip().splitlines()[0])
    except Exception:
        return 0


def _to_stereo(path):
    """Filter đưa 1 nhánh audio về stereo mà KHÔNG đổi độ to nghe được.

    Mono thì nhân đôi kênh giữ NGUYÊN biên độ (pan), vì trình phát vốn phát track
    mono ra cả 2 loa ở biên độ đầy đủ. Để amix tự upmix thì nó hạ -3 dB mỗi kênh
    -> giọng dub (gần như luôn mono) nghe nhỏ hơn bản chưa trộn đúng 3 dB.
    """
    if _audio_channels(path) == 1:
        return "pan=stereo|c0=c0|c1=c0"
    return "aformat=channel_layouts=stereo"


def _atempo_chain(factor):
    """Chuỗi filter atempo đổi tốc độ audio theo `factor` (0.5 = chậm còn 1 nửa).

    Mỗi atempo chỉ nhận 0.5-2.0 nên factor ngoài khoảng đó phải chia thành nhiều
    bước nhân dồn (0.25 -> atempo=0.5,atempo=0.5).
    """
    steps = []
    f = float(factor)
    while f < 0.5:
        steps.append(0.5)
        f /= 0.5
    while f > 2.0:
        steps.append(2.0)
        f /= 2.0
    steps.append(f)
    return ",".join(f"atempo={s:.6f}" for s in steps)


def compose_final(cleaned_video, dub_audio, ass_path, output_path, stretch_video=False,
                   original_video=None, original_volume_pct=None):
    """Ghép: video đã xoá sub cũ + audio dub mới + TIẾNG GỐC hạ nhỏ + sub mới đúng vị trí.

    original_volume_pct: âm lượng tiếng gốc giữ lại, tính theo % so với ban đầu.
        0 = tắt hẳn tiếng gốc (hành vi cũ). None -> lấy từ config.
    original_video: file video gốc, dùng làm nguồn tiếng nền DỰ PHÒNG. Cần có vì
        VSR ghép audio lại bằng `-acodec copy` và nuốt lỗi im lặng (bắt exception
        rồi return — vendor/video-subtitle-remover/backend/main.py:470), nên
        cleaned.mp4 có thể ra mà không còn tiếng.
    stretch_video: nếu True và dub dài hơn video, KÉO GIÃN video cho khớp độ dài
    dub (setpts) — dùng cho giọng clone đọc tự nhiên (dài hơn timing gốc) để giọng
    không bị cắt/không phải nén nhanh. Phụ đề (.ass) đã theo timing của dub nên khớp.
    """
    stage = "Ghép video cuối"

    if original_volume_pct is None:
        original_volume_pct = load_config().get("original_volume_pct", 30)
    try:
        volume = max(0.0, min(float(original_volume_pct), 100.0)) / 100.0
    except (TypeError, ValueError):
        volume = 0.30

    vf = f"subtitles=filename='{ass_path.name}'"
    speed_factor = 1.0
    if stretch_video:
        vdur = _media_duration(cleaned_video)
        adur = _media_duration(dub_audio)
        if vdur > 0 and adur > vdur * 1.02:
            speed_factor = adur / vdur
            # setpts kéo giãn thời gian video (chậm lại) cho bằng độ dài dub.
            vf = f"setpts={speed_factor:.4f}*PTS,{vf}"

    # Nguồn tiếng gốc: ưu tiên video đã xoá sub (cùng timeline, khỏi thêm input);
    # nếu VSR làm rớt audio thì quay về file gốc người dùng đưa vào.
    extra_inputs = []
    bg_idx = None
    if volume > 0:
        if _has_audio_stream(cleaned_video):
            bg_idx = 0
        elif original_video and Path(original_video).exists() and _has_audio_stream(original_video):
            extra_inputs = ["-i", str(original_video)]
            bg_idx = 2

    if bg_idx is None:
        # Không có tiếng gốc để trộn (video câm, hoặc người dùng đặt 0%) -> chỉ dub.
        filter_complex = f"[0:v]{vf}[vout]"
        audio_map = "1:a"
    else:
        bg_path = original_video if bg_idx == 2 else cleaned_video
        bg_chain = [_to_stereo(bg_path)]
        if speed_factor > 1.0:
            # Video bị kéo giãn -> tiếng gốc phải giãn theo đúng tỉ lệ, không thì
            # nhạc nền/tiếng động lệch dần so với hình.
            bg_chain.append(_atempo_chain(1.0 / speed_factor))
        bg_chain.append(f"volume={volume:.4f}")
        filter_complex = (
            f"[0:v]{vf}[vout];"
            f"[{bg_idx}:a]{','.join(bg_chain)}[bg];"
            f"[1:a]{_to_stereo(dub_audio)}[dub];"
            # normalize=0 BẮT BUỘC: mặc định amix chia âm lượng cho số input ->
            # giọng dub sẽ bị nhỏ đi một nửa dù không ai hạ nó.
            f"[bg][dub]amix=inputs=2:duration=longest:normalize=0[aout]"
        )
        audio_map = "[aout]"

    run([
        FFMPEG_BIN, "-y",
        "-i", str(cleaned_video),
        "-i", str(dub_audio),
        *extra_inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", audio_map,
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
    parser.add_argument("--original-volume", type=int, default=int(cfg.get("original_volume_pct", 30)),
                         help="Âm lượng tiếng gốc giữ lại trong video cuối, %% so với ban đầu "
                              "(0 = tắt hẳn tiếng gốc, mặc định 30).")
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
            original_volume_pct=args.original_volume,
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
        compose_final(cleaned_video, dub_audio, ass_path, output_path,
                       original_video=input_video, original_volume_pct=args.original_volume)

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
