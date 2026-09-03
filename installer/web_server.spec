# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec cho web_server.py (FastAPI backend + UI static tự viết).
Nhẹ hơn hẳn 2 spec kia — không có ML dep riêng, chỉ gọi vsr_cli.exe/
pyvideotrans_cli.exe qua subprocess (orchestrator.py, đã tự nhận diện FROZEN).

Layout cài đặt do Inno Setup dựng (xem orchestrator.py, comment FROZEN):
    <install_dir>/
        web_server.exe        <- chính exe này, PHẢI nằm ở top-level
        web_static/           <- bundle kèm trong spec này (datas)
        pyvideotrans/pyvideotrans_cli.exe
        vsr/vsr_cli.exe
        ffmpeg/ffmpeg.exe, ffprobe.exe

contents_directory='.' bắt buộc (bài học từ 2 spec trước): web_server.py mount
StaticFiles tại orch.PROJECT_ROOT/web_static — PROJECT_ROOT khi FROZEN =
Path(sys.executable).parent, tức ngay top-level cạnh exe, không phải trong
_internal/.
"""
import os

from PyInstaller.utils.hooks import collect_all

PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

DATAS = [
    (os.path.join(PROJECT_ROOT, "web_static"), "web_static"),
]

# el_clone.py (dub ElevenLabs) chạy TRONG tiến trình web_server khi FROZEN —
# bản đóng gói không có python.exe nào để chạy nó như script rời, xem
# orchestrator.synthesize_elevenlabs_dub. Import nằm trong hàm nên PyInstaller
# không tự dò ra -> phải khai báo hiddenimport.
HIDDEN = ["el_clone", "uvicorn.loops.auto", "uvicorn.protocols.http.auto",
          "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on"]
BINARIES = []

# soundfile mang theo libsndfile (_soundfile_data) — thiếu là ImportError lúc
# chạy chứ không phải lúc build, nên gom trọn cho chắc.
_d, _b, _h = collect_all("soundfile")
DATAS += _d
BINARIES += _b
HIDDEN += _h
# numpy đã có hook sẵn của PyInstaller, không cần collect_all (chỉ làm phình bundle).

a = Analysis(
    [os.path.join(PROJECT_ROOT, "web_server.py")],
    pathex=[PROJECT_ROOT],
    binaries=BINARIES,
    datas=DATAS,
    hiddenimports=HIDDEN,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="web_server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    contents_directory=".",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="web_server",
)
