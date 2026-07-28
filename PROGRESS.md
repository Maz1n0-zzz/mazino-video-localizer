# Video Pipeline — Tiến độ theo Phase

## Phase 0 — Setup môi trường ✅ DONE (2026-07-27)

- [x] Clone `pyvideotrans` vào `vendor/pyvideotrans/` (git, `--depth 1`)
- [x] Clone `video-subtitle-remover` vào `vendor/video-subtitle-remover/` (git, `--depth 1`, ~1.7GB)
- [x] `pyvideotrans`: venv qua `uv` theo `.python-version` (3.10.19). Patch `pyproject.toml`:
      comment out `pynini` + `WeTextProcessing` (không có wheel macOS, source build lỗi API
      với openfst mới trên Homebrew — StringJoin/StrJoin). Không ảnh hưởng vì project này
      không dùng nhánh TTS text-normalization cần 2 package đó.
- [x] `pyvideotrans` CLI verified: `uv run --no-sync cli.py --list languages` chạy đúng.
- [x] `video-subtitle-remover`: venv riêng qua `uv venv --python 3.12` (tên `videoEnv/`,
      nằm trong `vendor/video-subtitle-remover/`) — vì system Python là 3.14 (quá mới,
      không có wheel sẵn cho paddlepaddle/torch/onnxruntime).
- [x] Cài theo đúng thứ tự README macOS: `paddlepaddle==3.0.0` (CPU wheel, nguồn PaddlePaddle
      official) → `torch==2.7.0` + `torchvision==0.22.0` → `pip install -r requirements.txt`.
- [x] `video-subtitle-remover` CLI verified: `python -m backend.main --help` chạy đúng,
      hiện đủ flags (`--input`, `--output`, `--subtitle-area-coords`, `--inpaint-mode`
      với 5 mode: sttn-auto/sttn-det/lama/propainter/opencv).

**Kết luận Phase 0:** cả 2 CLI đã chạy được độc lập trên máy, mỗi cái venv riêng biệt
(không đụng dependency nhau — đúng theo lý do license GPL-3.0 của pyvideotrans, gọi qua
subprocess riêng, không import code).

## Phase 1 — Validate tay từng CLI với 1 video mẫu thật ✅ DONE (2026-07-27)

- [x] Tạo video mẫu tự dựng (`samples/sample_test.mp4`, 1280x720, 8s) — bằng ffmpeu
      `testsrc2` làm nền + giọng đọc TTS thật (macOS `say`) + subtitle cứng đốt vào
      (2 dòng, timing khác nhau) + logo giả "DEMO LOGO" góc trên-phải. Tự dựng để có
      ground-truth biết chính xác (không dính bản quyền, không cần đi tìm clip có sẵn).
      Lưu ý: Homebrew ffmpeg bản máy KHÔNG có filter `drawtext`/`subtitles` (build thiếu
      libfreetype) → phải render text ra PNG trong suốt bằng PIL rồi `overlay` filter.
- [x] Chạy `video-subtitle-remover` (`backend.main --inpaint-mode sttn-auto`) xoá subtitle
      cứng — chạy 30s cho 187 frame, dùng MPS (GPU Apple Silicon) tự động. Kiểm tra bằng
      mắt (frame trước/sau): chữ subtitle đã mất hoàn toàn, có chút blur nhẹ ở biên màu
      cứng (do nền test pattern nhân tạo, video thật sẽ mượt hơn). Logo không bị đụng —
      đúng như kỳ vọng (VSR không xử lý logo, chỉ subtitle).
- [x] Chạy `pyvideotrans` `stt` (faster-whisper `small`, CPU) → transcript khớp gần như
      100% với script gốc. `sts` (Google Translate free) dịch sang tiếng Việt đúng nghĩa,
      giữ đúng timing 3 dòng phụ đề.
- [x] Thời gian thực tế trên M4 Pro: VSR ~30s (7.5s video, MPS); STT ~141s wall lần đầu
      (chủ yếu do tải model `small` lần đầu, xử lý thực tế theo log nội bộ chỉ ~41s);
      dịch (`sts`, gọi API online) ~1.5s.

**Kết luận Phase 1:** cả 2 CLI hoạt động đúng độc lập trên máy thật, không cần sửa gì
thêm ở tầng CLI. Rào cản duy nhất gặp phải nằm ngoài 2 repo (ffmpeg thiếu drawtext khi
tự dựng video test) — không ảnh hưởng pipeline thật.

## Phase 2 — Script điều phối thuần CLI (chưa UI) ✅ DONE (2026-07-27)

- [x] Viết `orchestrator.py` (pure stdlib, không cần venv riêng) ở root project, gọi thẳng
      python interpreter của từng venv qua subprocess: VSR
      (`vendor/video-subtitle-remover/videoEnv/bin/python -m backend.main`) và pyvideotrans
      (`vendor/pyvideotrans/.venv/bin/python3 cli.py --task vtv`).
- [x] 4 bước: (1) VSR xoá sub/logo cũ (auto-detect vùng, không cần coords tay) → (2)
      pyvideotrans `vtv` transcribe+dịch+dub (`--subtitle_type 0` để KHÔNG dùng bước burn-sub
      nội bộ của nó) → (3) tự convert srt→ass rồi patch `PlayResX/PlayResY` = đúng độ phân
      giải video thật + font/margin scale theo chiều cao video (fix triệt để bug sai vị trí
      sub phát hiện ở Phase 1) → (4) tự ghép bằng 1 lệnh ffmpeg riêng: video đã xoá sub cũ +
      audio dub mới + sub mới đúng vị trí.
- [x] Test end-to-end trên video thật `7938248522786.mp4`: chạy đúng, không lỗi, ra file
      hoàn chỉnh trong ~1m17s (model đã cache). Sub đã hiển thị đúng vùng an toàn dưới màn
      hình dọc, cỡ chữ hợp lý — xác nhận bằng preview frame.
- [x] Chỗ gắn logo mới: chưa làm (chưa có asset logo cho use-case này), nhưng kiến trúc đã
      chừa đúng vị trí — thêm 1 bước overlay PNG vào `compose_final()` là xong, không cần
      sửa kiến trúc.

**Lưu ý còn tồn:** độ chính xác STT trên audio ồn/giọng nhanh (clip test) vẫn sai như đã
báo — đây là hạn chế của Whisper với audio khó, không phải lỗi của orchestrator. Orchestrator
chỉ đảm bảo pipeline chạy đúng cơ chế; chất lượng transcript phụ thuộc audio đầu vào.

## Phase 3 — Đóng gói UI Gradio ✅ DONE (2026-07-27)

- [x] Venv riêng `ui_env/` (Python 3.12, chỉ có `gradio` + `edge-tts` — nhẹ, không đụng
      2 venv nặng của VSR/pyvideotrans).
- [x] `app.py` import trực tiếp các hàm trong `orchestrator.py` (không gọi lại qua
      subprocess lồng nhau) — Blocks UI: upload video, chọn ngôn ngữ gốc/đích, chọn giọng
      đọc Edge-TTS (tự lọc theo ngôn ngữ đích, gọi 1 lần lúc khởi động rồi cache), chọn
      Whisper model, chọn inpaint mode của VSR, nút "Chạy pipeline".
- [x] Tiến trình hiển thị theo 4 bước (không stream log dòng-theo-dòng của từng lệnh con —
      đủ cho MVP, có thể nâng cấp ở Phase 4 nếu cần).
- [x] Output final lưu vào `outputs/`, tự dọn work-dir tạm sau khi xong.
- [x] Khởi động thật, verify bằng `curl` server trả về đúng HTML shell của Gradio tại
      `http://127.0.0.1:7860`.

**Cách chạy:**
```
cd /Users/mazino/Projects/video_pipeline
source ui_env/bin/activate
python3 app.py
```
Mở `http://127.0.0.1:7860` trên browser.

## Phase 4 — Polish ✅ DONE (2026-07-27)

- [x] **Cache model**: kiểm tra lại — đã hoạt động sẵn từ Phase 0/2, không cần code thêm.
      Whisper models nằm ở `vendor/pyvideotrans/models/models--Systran--faster-whisper-*`,
      persist qua các lần chạy (xác nhận thực tế: lần đầu ~6 phút do tải model, lần sau chỉ
      15-18s).
- [x] **Xử lý lỗi**: thêm `PipelineStageError` (`orchestrator.py`) — mọi lệnh con thất bại
      giờ báo rõ **tên bước** + lý do, thay vì traceback Python thô. Thêm `preflight_checks()`
      kiểm tra ffmpeg/ffprobe/venv tồn tại trước khi chạy, báo lỗi môi trường rõ ràng ngay từ
      đầu. Test thật bằng cách cố tình đưa voice không hợp lệ → xác nhận báo đúng
      `[LỖI ở bước: pyvideotrans transcribe/dịch/dub]` kèm chi tiết, không crash mất kiểm soát.
- [x] **Lưu config mặc định**: thêm `pipeline_config.py` (load/save `config.json`) — dùng
      chung cho cả `orchestrator.py` (CLI, cờ `--save-as-default`) và `app.py` (nút
      "Lưu làm mặc định"). Test CLI không truyền `--source-lang`/`--target-lang` → tự dùng
      default (zh-cn→vi) đúng như mong đợi.
- [x] Fix thêm 1 deprecation warning của Gradio 6 (theme/css chuyển từ `Blocks()` sang
      `launch()`).

**Cả 5 phase của lộ trình ban đầu đã xong.** UI hiện tại theo đúng logic mong muốn; phần
giao diện (màu/theme) người dùng muốn để lại chỉnh sau, không nằm trong Phase 4 kỹ thuật.

## Phase 5 (bổ sung) — Thay UI từ Gradio sang FastAPI + HTML/CSS/JS tự viết ✅ DONE (2026-07-27)

**Lý do:** Gradio là component library đóng gói sẵn (Svelte) — chỉ chỉnh được màu/border/font
qua CSS, không sửa được cấu trúc HTML bên trong (nút upload, video player, dropdown), nên
không thể khớp 100% với ảnh mockup người dùng cung cấp (icon riêng từng dòng, khung upload
dashed, nút "Click to Upload" dạng pill, icon rỗng riêng cho từng khung kết quả). Đã thử tối
đa với Gradio (2 vòng chỉnh CSS) rồi mới đề xuất chuyển stack — người dùng chọn phương án
FastAPI + HTML/CSS/JS tự viết (option Recommended trong 3 lựa chọn đưa ra, so với NiceGUI và
Streamlit).

- [x] `legacy_gradio_app.py` — giữ lại bản Gradio cũ (không xoá, phòng khi cần đối chiếu),
      không còn dùng để chạy UI chính.
- [x] Venv riêng `web_env/` (Python 3.12): `fastapi`, `uvicorn[standard]`, `python-multipart`,
      `edge-tts`.
- [x] `web_server.py` — backend FastAPI, tái dùng 100% logic có sẵn (`orchestrator.py`,
      `pipeline_config.py`, không sửa gì): `/api/config`, `/api/voices`, `/api/run` (nhận
      upload + chạy pipeline trong background thread), `/api/progress/{job_id}` (SSE stream
      log theo thời gian thực), `/outputs/{filename}` (serve video kết quả).
- [x] `web_static/index.html` + `style.css` + `app.js` — UI thuần HTML/CSS/JS, tự code từng
      phần tử (dropzone kéo-thả thật, nút "Click to Upload" pill thật, icon rỗng riêng cho
      từng khung, select tự style) → khớp mockup sát hơn nhiều so với bản Gradio, không còn bị
      giới hạn bởi cấu trúc component có sẵn.
- [x] Test thật end-to-end qua UI mới (Playwright): upload video thật → preview hiện đúng →
      bấm "Chạy pipeline" → log SSE cập nhật đúng 4 bước theo thời gian thực → video kết quả
      hiện lên phát được → nút "Tải xuống" hoạt động. Chạy trơn tru, không lỗi.

**Cách chạy UI mới:**
```
cd /Users/mazino/Projects/video_pipeline
source web_env/bin/activate
python3 web_server.py
```
Mở `http://127.0.0.1:7860`.
