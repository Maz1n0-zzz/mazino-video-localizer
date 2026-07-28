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

PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

DATAS = [
    (os.path.join(PROJECT_ROOT, "web_static"), "web_static"),
]

a = Analysis(
    [os.path.join(PROJECT_ROOT, "web_server.py")],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=DATAS,
    hiddenimports=["uvicorn.loops.auto", "uvicorn.protocols.http.auto", "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on"],
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
