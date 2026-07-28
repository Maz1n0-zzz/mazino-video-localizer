# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec cho pyvideotrans CLI, chỉ bundle đúng những gì task `vtv` thực sự
dùng với cấu hình cố định của pipeline này:

    --recogn_type 0      (FASTER_WHISPER)
    --translate_type 0   (GOOGLE_INDEX, tự fallback MICROSOFT_INDEX khi lỗi mạng)
    --tts_type 0          (EDGE_TTS)

pyvideotrans hỗ trợ 30+ channel STT/dịch/TTS (kể cả các model ML nặng như
modelscope/torch/transformers/confuciustts) qua cơ chế nạp module động
(importlib.import_module theo channel id) — cli.py KHÔNG import tĩnh các channel
này, nên PyInstaller cũng không tự phát hiện được, phải khai --hidden-import
đúng 3 channel ta dùng.

Ngược lại, một số module base (vd videotrans/translator/_base.py) có `import torch`
nằm trong 1 method không liên quan tới luồng 0/0/0 (dùng cho channel dịch bằng model
cục bộ khác) — PyInstaller vẫn tĩnh phát hiện được câu import này dù nó nằm trong
function, nên mặc định SẼ kéo theo torch/transformers/accelerate/modelscope/...
(~1GB+) vào bundle dù không bao giờ chạy tới. Đã verify thực nghiệm (chặn hẳn các
package này rồi chạy full task vtv thật trên máy) rằng luồng 0/0/0 hoàn toàn không
cần chúng, nên loại thẳng qua `excludes` bên dưới.
"""
import os
from PyInstaller.utils.hooks import collect_data_files

PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
PVT_DIR = os.path.join(PROJECT_ROOT, "vendor", "pyvideotrans")

# Các channel STT/dịch/TTS ta thực sự dùng (nạp động qua importlib, PyInstaller
# không tự thấy được nên phải khai rõ).
HIDDEN_IMPORTS = [
    "videotrans.recognition._whisper",
    "videotrans.translator._google",
    "videotrans.translator._microsoft",  # fallback tự động khi Google lỗi mạng
    "videotrans.tts._edgetts",
    "videotrans.process.stt_faster",
    "videotrans.process.vad",
]

# Đã verify thực nghiệm (block import + chạy full task vtv thật) rằng các package
# này không cần cho luồng recogn_type=0/translate_type=0/tts_type=0. Loại bỏ để
# giảm size + tránh build native-binary Windows dễ vỡ (torch/numba/llvmlite...).
EXCLUDES = [
    "torch", "torchaudio", "torchvision",
    "transformers", "accelerate", "peft",
    "modelscope", "wandb",
    "numba", "llvmlite",
    "matplotlib", "Cython",
    "sqlalchemy", "alembic",
    "hydra", "omegaconf", "antlr4",
    "IPython", "jedi", "notebook", "jupyter",
    "fastapi", "uvicorn",  # web_server dùng riêng, không liên quan pyvideotrans cli
    "pyannote", "funasr",
    # onnxruntime KHÔNG được loại — faster-whisper tự dùng nó nội bộ cho VAD filter
    # (Silero VAD) mặc định khi recogn_type=0, phát hiện qua thực nghiệm build/run
    # thật (xem ghi chú trong lịch sử commit/PROGRESS.md).
    "PySide6.QtWidgets", "PySide6.QtGui", "PySide6.QtQml",
    "PySide6.QtWebEngineWidgets", "PySide6.QtNetwork", "PySide6.QtMultimedia",
    "tkinter",
]

DATAS = [
    (os.path.join(PVT_DIR, "videotrans", "cfg.json"), "videotrans"),
    (os.path.join(PVT_DIR, "videotrans", "params.json"), "videotrans"),
    (os.path.join(PVT_DIR, "videotrans", "language"), "videotrans/language"),
    (os.path.join(PVT_DIR, "videotrans", "voicejson"), "videotrans/voicejson"),
    (os.path.join(PVT_DIR, "videotrans", "prompts"), "videotrans/prompts"),
]
# styles/ chứa font/icon GUI + no-remove.mp4 (dùng để test hardware encoder) —
# chỉ lấy phần cần, bỏ simhei.ttf (font GUI 9.3MB, không dùng ở luồng CLI).
_styles_dir = os.path.join(PVT_DIR, "videotrans", "styles")
for _fname in ("no-remove.mp4", "no-remove.wav"):
    _fpath = os.path.join(_styles_dir, _fname)
    if os.path.exists(_fpath):
        DATAS.append((_fpath, "videotrans/styles"))

# faster-whisper ship kèm silero_vad_*.onnx trong package data (assets/), zhconv ship
# kèm zhcdict.json (giản thể<->phồn thể) — PyInstaller không tự gom data file ngoài
# .py, phải collect_data_files thủ công. Cả 2 phát hiện qua thực nghiệm build+run
# thật (lỗi "file doesn't exist"/FileNotFoundError khi thiếu).
DATAS += collect_data_files("faster_whisper")
DATAS += collect_data_files("zhconv")

a = Analysis(
    [os.path.join(PVT_DIR, "cli.py")],
    pathex=[PVT_DIR],
    binaries=[],
    datas=DATAS,
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="pyvideotrans_cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    # pyvideotrans tự tính ROOT_DIR = thư mục chứa exe (Path(sys.executable).parent),
    # rồi đọc data package của chính nó (videotrans/cfg.json, voicejson/, language/...)
    # bằng đường dẫn tuyệt đối nối trực tiếp vào ROOT_DIR — không biết gì về layout
    # "_internal/" mới của PyInstaller 6.x. Phát hiện qua thực nghiệm build+run thật:
    # thiếu contents_directory='.' khiến voicejson/edge_tts.json nằm ở
    # <exe_dir>/_internal/videotrans/voicejson/... trong khi code tìm ở
    # <exe_dir>/videotrans/voicejson/..., làm get_edge_rolelist() luôn trả về rỗng.
    contents_directory=".",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="pyvideotrans_cli",
)
