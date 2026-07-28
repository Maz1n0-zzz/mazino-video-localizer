# Mazino Video Localizer

Pipeline cá nhân: xoá sub/logo cũ trong video → transcribe → dịch → dub giọng mới → ghép
sub mới đúng vị trí. Chạy hoàn toàn local trên máy, có UI web để dùng như 1 app.

## Kiến trúc

- `vendor/video-subtitle-remover/` — xoá sub/logo cũ (inpainting). Third-party, xem
  [Third-party notices](#third-party-notices).
- `vendor/pyvideotrans/` — transcribe (Whisper) + dịch + text-to-speech dub. Third-party,
  xem [Third-party notices](#third-party-notices). Chỉ gọi qua CLI/subprocess, không import
  code vào project.
- `orchestrator.py` — script điều phối nối 2 tool trên lại, tự sửa lỗi PlayRes khi ghép sub
  (2 tool trên không biết về nhau, phần nối + tự viết lại logic ghép sub là code gốc của
  Mazino).
- `web_server.py` + `web_static/` — backend FastAPI + UI web tự viết (HTML/CSS/JS, không
  dùng framework UI có sẵn).
- `pipeline_config.py` — lưu/đọc config mặc định (`config.json`, không commit).
- `legacy_gradio_app.py` — bản UI cũ bằng Gradio, không dùng nữa, giữ lại để tham khảo.

## Setup

Yêu cầu: macOS/Linux, [`uv`](https://github.com/astral-sh/uv), `ffmpeg` bản đầy đủ (có
`libass`/`libfreetype` — bản Homebrew `ffmpeg` mặc định KHÔNG có, phải dùng
`homebrew-ffmpeg/ffmpeg`).

```bash
brew tap homebrew-ffmpeg/ffmpeg
brew install homebrew-ffmpeg/ffmpeg/ffmpeg   # gỡ bản ffmpeg core trước nếu đã cài

cd vendor/pyvideotrans && uv sync && cd ../..
cd vendor/video-subtitle-remover
uv venv --python 3.12 videoEnv
source videoEnv/bin/activate
uv pip install paddlepaddle==3.0.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
uv pip install torch==2.7.0 torchvision==0.22.0
uv pip install -r requirements.txt
cd ../..

uv venv --python 3.12 web_env
source web_env/bin/activate
uv pip install fastapi "uvicorn[standard]" python-multipart edge-tts
```

Chi tiết đầy đủ + các lỗi từng gặp và cách sửa: xem `PROGRESS.md`.

## Chạy

```bash
source web_env/bin/activate
python3 web_server.py
```

Mở `http://127.0.0.1:7860`.

## Third-party notices

Project này gọi 2 công cụ mã nguồn mở qua subprocess (không import code, không sửa đổi
license của họ):

- **video-subtitle-remover** — [YaoFANGUK/video-subtitle-remover](https://github.com/YaoFANGUK/video-subtitle-remover) — Apache-2.0. LICENSE giữ nguyên tại `vendor/video-subtitle-remover/LICENSE`.
- **pyvideotrans** — [jianchang512/pyvideotrans](https://github.com/jianchang512/pyvideotrans) — GPL-3.0. LICENSE giữ nguyên tại `vendor/pyvideotrans/LICENSE`.

Toàn bộ code còn lại trong repo (`orchestrator.py`, `web_server.py`, `web_static/`,
`pipeline_config.py`, v.v.) do Mazino viết.
