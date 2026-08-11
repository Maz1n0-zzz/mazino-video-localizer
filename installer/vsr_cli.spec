# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec cho video-subtitle-remover (VSR) CLI, entry point
backend/main.py, chỉ cần chạy đúng với cấu hình cố định của pipeline này:

    --inpaint-mode sttn-auto

Khác với pyvideotrans, VSR KHÔNG có cơ chế nạp module động theo channel:
backend/main.py import TĨNH ở đầu file torch, cv2, và cả 4 class inpaint
(STTNAutoInpaint, STTNDetInpaint, LamaInpaint, OpenCVInpaint, PropainterInpaint)
dù pipeline chỉ dùng STTNAutoInpaint. PyInstaller tĩnh phát hiện được toàn bộ
import này (không cần --hidden-import), nhưng đồng nghĩa KHÔNG thể loại
torch/paddleocr/PySide6 ra khỏi bundle bằng --excludes như bên pyvideotrans -
chúng là bắt buộc để import module thành công dù runtime path sttn-auto không
gọi tới paddleocr/PySide6 GUI thật.

Ghi chú quan trọng (đã verify thực nghiệm build+run thật):

1. `backend/tools/model_config.py` có bug (đã patch trực tiếp trong vendor):
   ModelConfig.__init__ gọi merge_big_file_if_not_exists(LAMA_MODEL_DIR,
   'bit-lama.pt') - SAI TÊN FILE (đúng phải là 'big-lama.pt', file thật trong
   dir là big-lama.pt). Vì tên không khớp, hàm này LUÔN nghĩ file chưa merge
   và re-merge lại từ các part big-lama_1..5.pt MỖI LẦN chạy (dù sttn-auto
   không dùng LamaInpaint) - vừa tốn ~7s I/O, vừa buộc phải bundle thêm các
   file part + fs_manifest.csv (~200MB dư) chỉ để hàm merge không crash.
   Đã sửa 'bit-lama.pt' -> 'big-lama.pt' trong vendor code, nên giờ chỉ cần
   bundle bản merged sẵn (big-lama.pt, ProPainter.pth), KHÔNG cần các part.

2. ModelConfig.__init__ luôn gọi merge cho CẢ LAMA_MODEL_DIR và
   PROPAINTER_MODEL_DIR bất kể inpaint mode nào được chọn (không có nhánh
   điều kiện theo mode) - vì vậy dù pipeline chỉ dùng sttn-auto, vẫn phải
   bundle big-lama.pt (205MB) và ProPainter.pth (157MB) đã merge sẵn, nếu
   không merge_big_file_if_not_exists sẽ FileNotFoundError (thư mục không
   tồn tại) hoặc lỗi merge (thiếu manifest/part) ngay tại SubtitleRemover.__init__,
   crash trước khi kịp chạy sttn-auto.

3. backend/tools/subtitle_detect.py có `import paddle` / `from paddleocr import
   TextDetection` NẰM TRONG cached_property `text_detector` (lazy) - sttn_auto_mode
   không bao giờ chạm tới OCR detection nên property này không bao giờ được
   truy cập, và các model OCR PP-OCRv5 (backend/models/V5/) KHÔNG cần bundle.

4. `backend/tools/ffmpeg_cli.py`: FFmpegCLI luôn tự resolve ffmpeg riêng tại
   backend/ffmpeg/macos/ffmpeg (relative theo BASE_DIR = thư mục chứa
   backend/config.py) - không dùng PATH hệ thống. Phải bundle kèm executable
   ffmpeg thật, giữ đúng cấu trúc thư mục tương đối.

5. `contents_directory='.'` PHẢI set trên EXE(...) (bài học từ pyvideotrans_cli.spec)
   - nếu không, PyInstaller 6.x gom hết vào _internal/ nhưng
   backend/config.py tính BASE_DIR = Path(__file__).parent của chính module
   backend/config.py sau khi frozen, dẫn tới lệch đường dẫn khi tìm
   backend/ffmpeg/macos/ffmpeg, backend/models/...
"""
import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
VSR_DIR = os.path.join(PROJECT_ROOT, "vendor", "video-subtitle-remover")

DATAS = []

# ffmpeg binary riêng của VSR (backend/tools/ffmpeg_cli.py luôn resolve đường
# dẫn này, không bao giờ dùng PATH hệ thống). Giữ đúng cấu trúc tương đối
# backend/ffmpeg/<platform>/ so với exe (nhờ contents_directory='.'). Trên
# Windows KHÔNG có sẵn ffmpeg.exe đã merge (chỉ có 3 part + fs_manifest.csv
# do file gốc bị GitHub giới hạn size) — bundle nguyên cụm part đó, để
# FFmpegCLI tự merge_big_file_if_not_exists() ở lần chạy đầu như dev-mode.
if sys.platform == "win32":
    _ffmpeg_dir = os.path.join(VSR_DIR, "backend", "ffmpeg", "win_x64")
    _ffmpeg_dest = "backend/ffmpeg/win_x64"
else:
    _ffmpeg_dir = os.path.join(VSR_DIR, "backend", "ffmpeg", "macos")
    _ffmpeg_dest = "backend/ffmpeg/macos"
if os.path.isdir(_ffmpeg_dir):
    for _fname in os.listdir(_ffmpeg_dir):
        DATAS.append((os.path.join(_ffmpeg_dir, _fname), _ffmpeg_dest))

# Model thực sự dùng bởi sttn-auto.
_sttn_auto_model = os.path.join(VSR_DIR, "backend", "models", "sttn-auto", "infer_model.pth")
if os.path.exists(_sttn_auto_model):
    DATAS.append((_sttn_auto_model, "backend/models/sttn-auto"))

# big-lama.pt và ProPainter.pth KHÔNG được sttn-auto dùng tới, nhưng
# ModelConfig.__init__ (backend/tools/model_config.py) luôn gọi
# merge_big_file_if_not_exists cho cả 2 dir này bất kể mode -> phải có mặt
# bản đã merge sẵn để hàm merge tự bỏ qua (file đã tồn tại), tránh crash/
# tránh phải bundle thêm các file part.
# big-lama.pt (205MB) vuot gioi han 100MB/file cua GitHub -> KHONG commit ban
# merged truc tiep. Thay vao do bundle cac part 50MB (big-lama_1..5.pt) +
# fs_manifest.csv (giong cach repo VSR goc lam); ModelConfig.__init__ goi
# merge_big_file_if_not_exists -> Filesplit tu ghep thanh big-lama.pt ngay
# trong thu muc cai (writable vi cai vao {localappdata}) o lan chay dau.
_big_lama_dir = os.path.join(VSR_DIR, "backend", "models", "big-lama")
if os.path.isdir(_big_lama_dir):
    for _f in ("big-lama_1.pt", "big-lama_2.pt", "big-lama_3.pt",
               "big-lama_4.pt", "big-lama_5.pt", "fs_manifest.csv"):
        _p = os.path.join(_big_lama_dir, _f)
        if os.path.exists(_p):
            DATAS.append((_p, "backend/models/big-lama"))

_propainter = os.path.join(VSR_DIR, "backend", "models", "propainter", "ProPainter.pth")
if os.path.exists(_propainter):
    DATAS.append((_propainter, "backend/models/propainter"))

# backend/interface/*.ini: bảng dịch text output console (tr['Main'][...]),
# đọc theo config.interface.value ('en' bị main.py force-set trước khi chạy).
_interface_dir = os.path.join(VSR_DIR, "backend", "interface")
if os.path.exists(_interface_dir):
    DATAS.append((_interface_dir, "backend/interface"))

# Không có PyInstaller hook sẵn cho paddleocr/paddlex/qfluentwidgets (khác
# torch/cv2/torchvision đã có hook trong pyinstaller-hooks-contrib) - thêm
# thủ công phòng trường hợp import tĩnh (dù lazy-loaded ở runtime) cần data
# file kèm theo lúc PyInstaller phân giải module.
for _pkg in ("qfluentwidgets", "paddleocr", "paddlex"):
    DATAS += collect_data_files(_pkg)

# torch_directml: chỉ có wheel cho Windows (không cài được trên macOS nên
# không thể verify cục bộ) — hardware_accelerator.py chỉ check bằng
# importlib.util.find_spec("torch_directml") (không phải statement import
# tĩnh) nên PyInstaller không tự phát hiện qua static analysis thông thường
# ở điểm đó — nhưng `device` property CÓ 1 câu `import torch_directml` lồng
# trong hàm nên PyInstaller vẫn tự thấy được qua AST scan bình thường. Thêm
# hidden-import + collect_dynamic_libs để chắc chắn không thiếu DLL riêng
# của DirectML runtime (chưa verify được trên máy Windows thật, phòng hờ).
# Guard bằng find_spec để spec này vẫn build được trên macOS (bỏ qua đoạn
# này) lúc test các phần khác của bundle.
import importlib.util as _ilu
HIDDEN_IMPORTS = []
BINARIES = []
if _ilu.find_spec("torch_directml") is not None:
    HIDDEN_IMPORTS.append("torch_directml")
    BINARIES += collect_dynamic_libs("torch_directml")

EXCLUDES = [
    # GUI/desktop app của VSR (gui.py) không liên quan tới luồng CLI - loại
    # các submodule PySide6 nặng không cần thiết cho backend/main.py. Giữ
    # QtCore/QtGui/QtWidgets vì qfluentwidgets (backend/config.py) cần chúng
    # để định nghĩa ConfigItem/QConfig ngay ở import time.
    "PySide6.QtQml", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineCore",
    "PySide6.QtNetwork", "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtBluetooth",
    "PySide6.QtSerialPort", "PySide6.QtSerialBus", "PySide6.QtSensors",
    "PySide6.QtPositioning", "PySide6.QtNfc", "PySide6.QtDataVisualization",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras", "PySide6.Qt3DInput", "PySide6.Qt3DLogic",
    "PySide6.QtCharts", "PySide6.QtGraphs", "PySide6.QtGraphsWidgets",
    "tkinter",
    # LƯU Ý: matplotlib KHÔNG được loại - backend/inpaint/utils/sttn_utils.py
    # (dùng bởi sttn-auto, đường dẫn ta cần) import tĩnh matplotlib.pyplot ở
    # module level. Loại nó gây ModuleNotFoundError ngay khi import
    # STTNAutoInpaint - phát hiện qua thực nghiệm build+run thật (lần build
    # đầu tiên).
]

a = Analysis(
    [os.path.join(VSR_DIR, "backend", "main.py")],
    pathex=[VSR_DIR],
    binaries=BINARIES,
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
    name="vsr_cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    # Xem ghi chú #5 ở đầu file - bắt buộc để backend/config.py (BASE_DIR)
    # và backend/tools/ffmpeg_cli.py/model_config.py tìm đúng data cạnh exe,
    # không bị PyInstaller 6.x gom vào _internal/.
    contents_directory=".",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="vsr_cli",
)
