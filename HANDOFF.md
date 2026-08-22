# HANDOFF — Video Localization Pipeline

> Ghi lại trạng thái dự án để tiếp tục ở session sau. Cập nhật: session hiện tại.

## Dự án là gì
Pipeline cá nhân: **xoá sub/logo cũ → transcribe → dịch → dub (giọng) → ghép sub mới đúng vị trí**. Dùng cho re-up video (vd TikTok) sang tiếng Việt.
- Repo GitHub (private→public): `Maz1n0-zzz/mazino-video-localizer`
- Thư mục gốc trên Mac dev: `/Users/mazino/Projects/video_pipeline`
- Người dùng: Mazino (GMT+7, tiếng Việt). Mục tiêu cuối: chạy trên **máy Windows của sếp (RTX 3060)**.

## Kiến trúc
- `vendor/video-subtitle-remover/` (VSR) — xoá sub/logo. Venv: `videoEnv` (Py 3.12).
- `vendor/pyvideotrans/` — transcribe (faster-whisper) + dịch (Google) + dub (Edge-TTS). Venv: `.venv` (Py 3.10).
- `orchestrator.py` — điều phối; hàm chính: `remove_old_subtitles`, `transcribe_translate_dub`, `synthesize_clone_dub`, `build_fixed_ass`, `compose_final`, `transcribe_audio`. Tự phân biệt FROZEN (Windows .exe) vs dev.
- `web_server.py` + `web_static/` (index.html, app.js, style.css) — UI web FastAPI (port 7860). Venv: `web_env`.
- `f5_clone.py` — tạo dub giọng CLONE (F5-TTS), chạy trong venv riêng `f5env`.
- `pipeline_config.py` — config.json (không commit).
- Scripts tiện: `start.command`, `update.command`, `setup-mac.command` (cài full trên Mac mới), `setup-clone.command` (cài F5 clone).

## Chạy trên Mac (dev)
```
cd /Users/mazino/Projects/video_pipeline
web_env/bin/python web_server.py   # rồi mở http://127.0.0.1:7860
```
Restart server: `lsof -ti:7860|xargs kill -9; sleep 1; web_env/bin/python web_server.py >/tmp/mvl_server.log 2>&1 &`

## Tính năng đã xong (bản Mac/git, đã commit tới b1ecba4 + đang có thay đổi CHƯA commit)
1. **Windows installer .exe** qua GitHub Actions (`.github/workflows/build-windows-installer.yml`) — DirectML cho GPU mọi hãng. Tải qua Artifacts (Release bị giới hạn 2GB nên bỏ).
2. **Xoá sub/logo**: chế độ `lama-auto` (AI, xoá logo cố định), `blur` (làm mờ), `sttn-auto`. **PHẢI khoanh vùng bằng tay** trong UI (không auto-detect). Model big-lama chia part 50MB trong git, tự merge khi chạy.
3. **Sub cách đáy %** + **đặt sub vào ô blur** (checkbox, sub đè lên chỗ sub cũ, tự co cỡ chữ).
4. **Từ điển phiên âm TTS** (`vendor/pyvideotrans/videotrans/util/pronounce_dict.py`, file json ngoài bundle) — sửa cách đọc từ tiếng Anh (vd Claude→Cờ-lốt).
5. **Voice clone (F5-TTS tiếng Việt)** — ĐANG HOÀN THIỆN (xem dưới).

## Voice clone F5-TTS — trạng thái hiện tại (CHƯA commit)
- Model VN: `hynt/F5-TTS-Vietnamese-ViVoice` (~5.4GB) tải về `models/f5-vi/` (gitignore). Venv `f5env` (gitignore). Cần `ffmpeg@6` (brew) cho torchcodec.
- **Thư viện giọng** (`clone_voices/voices.json`, gitignore): mỗi giọng có tên + wav mẫu + ref_text. Hiện có "Voice Clone 1". Chọn như preset trong dropdown (engine "Clone giọng").
- Endpoint: `POST/DELETE /api/clone-voices`. UI: nút "➕ Thêm giọng clone mới".
- `f5_clone.py`: sinh từng câu tốc độ tự nhiên (có `--speed`, đang dùng 0.85), nối liền mạch nghỉ 0.18s, xuất srt mới; `compose_final(stretch_video=True)` kéo giãn video khớp giọng.
- Trên Mac F5 rất chậm (~RTF 6, video 1 phút ~10-20 phút). Trên RTX 3060 nhanh hơn ~20-30×.

### Lỗi F5 đã sửa trong session
- File mẫu quá dài (255s) → F5 loạn sinh tiếng lặp "chạy chạy" → **cắt mẫu ngắn**.
- Ghép đặt cứng theo start → chồng tiếng tạp âm → **nối tiếp không chồng**.
- Nén atempo 2× → đọc quá nhanh → **bỏ nén, đọc tự nhiên + kéo giãn video**.
- Lọt câu giọng gốc "đúng là con vua" → **cắt mẫu dừng ở chỗ im lặng** (silencedetect, `/tmp/recut.py`) + `--speed 0.85`.

### VIỆC CÒN LẠI (F5)
- [ ] User nghiệm thu `~/Downloads/F5-v2.mp3` (hết lọt + pace ổn chưa). Nếu còn nhanh → hạ speed thêm.
- [ ] **Sửa endpoint `add_clone_voice` trong web_server.py**: hiện cắt cứng 14s (`-ss 1.5 -t 14`), nên đổi sang cắt theo **silencedetect** (như `/tmp/recut.py`) để giọng mới thêm cũng không lọt tiếng.
- [ ] Chạy nghiệm thu 1 video thật với clone (dài hơn video do kéo giãn — kiểm tra sub có khớp giọng không).
- [ ] Nếu F5 vẫn tệ → cân nhắc **ElevenLabs** (pyvideotrans hỗ trợ sẵn `--tts_type 22`, cần API key trả phí; chất lượng VN ổn hơn).
- [ ] **COMMIT** toàn bộ thay đổi F5 clone (orchestrator.py, web_server.py, f5_clone.py, web_static/*, setup-clone.command, .gitignore) sau khi user OK.
- [ ] **Bản Windows .exe cho F5**: cần đóng gói f5env + torch CUDA + model → installer to (~+3-4GB), sửa workflow + spec. Làm SAU khi bản Mac ổn.

## Session này — ĐANG DỞ, CHƯA COMMIT (tất cả thay đổi local)
Đã làm xong nhưng CHƯA commit (chạy trên server local port 7860):
1. **F5 clone hoàn thiện**: cắt mẫu theo silencedetect (chống lọt tiếng giọng gốc), `--speed 0.85` (đọc từ tốn), sinh tự nhiên + nối tiếp + video kéo giãn khớp giọng. Thư viện giọng có "Voice Clone 1". → User nghiệm thu OK.
2. **ElevenLabs bản CƠ BẢN (per-segment, DÍNH LỖI lệch ngữ điệu — xem dưới)**: engine "elevenlabs" trong UI, nhập API key + Voice ID + chọn model (v2/v3/flash_v2_5/turbo_v2_5). `orchestrator.set_elevenlabs_config()` ghi key vào pyvideotrans params.json + voice_id vào elevenlabs.json, gọi `--tts_type 22`. **Bản này gọi API riêng từng đoạn → lệch ngữ điệu.**
3. **2 loại khối khoanh vùng**: "Khối CHE SUB" (xanh, sub mới đè lên) vs "Khối CHE LOGO" (cam, chỉ blur). Thay checkbox `place_sub_in_region` cũ. Frontend gửi `sub_box` = khối SUB to nhất; web_server nhận `sub_box` trực tiếp.
4. Files đụng: orchestrator.py, web_server.py, web_static/{index.html,app.js}, f5_clone.py, setup-clone.command, .gitignore. → **CẦN COMMIT khi user duyệt.**

## ĐANG LÀM: Fix ElevenLabs v3 lệch ngữ điệu (single-call with-timestamps)
**Bệnh:** engine EL hiện gọi API RIÊNG từng đoạn (pyvideotrans `_elevenlabs.py` → `client.text_to_speech.convert` mỗi subtitle) → mỗi lần model tự chọn lại ngữ điệu mở đầu → đoạn cao đoạn trầm, lộ nhất ở chỗ nối. v3 biểu cảm mạnh nên càng lộ. **KHÔNG phải lỗi âm lượng** (đo chênh 1.43dB, bỏ qua chuẩn hoá âm lượng).

**Đã thử & KHÔNG DÙNG (đừng lặp lại):** `previous_text`/`next_text`→400; `previous_request_ids`/`next_request_ids`→400 `unsupported_model` với v3; đổi v2→đọc VN như người nước ngoài; đổi flash_v2_5→nuốt dấu thanh ("tháng bảy"→"tháng bay").

**Cách sửa (đã chạy được ở project khác `evose-auto-generate-video`):** nối TOÀN BỘ lời thành 1 chuỗi (ngăn `\n\n`, chunk ≤2900 ký tự cho v3), gọi **1 lần** `POST /v1/text-to-speech/{voice_id}/with-timestamps`, cắt từng đoạn theo `alignment` (mốc thời gian TỪNG KÝ TỰ). Cả bài 1 mạch → hết chỗ lệch.

**Bắt buộc:** kiểm `alignment.characters.join("") === text` trước khi cắt (lệch 1 ký tự = cắt giữa từ, âm thầm).

**3 bẫy:**
1. Model tự chèn nghỉ ~0.48s ở `\n\n` — chỉ chừa ~0.12s hai đầu mỗi đoạn, bỏ phần giữa (không thì video phình).
2. v3 thỉnh thoảng ĐỌC TO thẻ cảm xúc (`[curious]`→"CU Arius", ~1/4 lần). Phát hiện: thẻ bị đọc thì mỗi ký tự tốn ~như chữ thường (>0.12s/ký tự); thẻ hiểu đúng cả thẻ chỉ tốn ≤0.069s. **Ngưỡng 0.12s/ký tự.** ĐỪNG dùng TỔNG thời lượng (`[sighs]` thở dài thật 0.48s → sai). Trượt thì đọc lại chunk.
3. ffmpeg `amix` mặc định chia biên độ theo số input → quên `normalize=0` là hạ 6.02dB. (Project này compose_final KHÔNG amix bgm nên gần như N/A — xác nhận lại.)

**Đánh đổi:** mất sinh lại riêng 1 đoạn (sửa 1 chữ = đọc lại cả bài); cache theo VÂN TAY toàn bộ lời (không cache theo đoạn); nhịp chậm ~7% (bù bằng `speed` 0.7–1.2 trong voice_settings).

**Doc + code mẫu (joinTake/generateAlignedTake/sliceRanges/findSpokenTags + ffmpeg `-ss` SAU `-i`):**
https://raw.githubusercontent.com/Maz1n0-zzz/evose-auto-generate-video/main/docs/elevenlabs-v3-lech-ngu-dieu.md

**KẾ HOẠCH IMPLEMENT (đã user duyệt):**
- Tạo `el_clone.py` (giống `f5_clone.py`): đọc vi.srt → join+chunk → gọi with-timestamps 1 lần/chunk → verify alignment → cắt đoạn theo char-range (gọt nghỉ, chừa 0.12s) → phát hiện thẻ bị đọc (>0.12s/ký tự) → đọc lại nếu trượt → ghép dub + xuất srt. Chạy bằng `PVT_PY` (pyvideotrans venv có `elevenlabs` 2.38.1 + numpy + soundfile). Slice audio bằng ffmpeg (`-ss` sau `-i`).
- `orchestrator.py`: thêm `synthesize_elevenlabs_dub(srt, api_key, voice_id, model, speed, work_dir)` trả `(wav, srt)`. BỎ `set_elevenlabs_config` + đường tts_type=22.
- `web_server.py`: engine "elevenlabs" → gọi `synthesize_elevenlabs_dub` (giống nhánh f5clone), dùng clone_srt + `compose_final(stretch_video=True)`.
- UI: thêm ô `speed` cho EL (0.7–1.2).
- **Bước 3 chưa làm: test API thật xem v3 đã hỗ trợ `previous_request_ids` chưa** (đo 20/08/2026) — CẦN API KEY của user. Nếu đã hỗ trợ thì có đường đơn giản hơn.

## Lưu ý quan trọng
- Server đang chạy (port 7860). KHÔNG restart khi có job đang chạy.
- KHÔNG nghe được audio → mọi kiểm tra chất lượng giọng phải nhờ user nghe (hoặc transcribe để đối chiếu nội dung).
- Model >100MB không commit trực tiếp (GitHub chặn) → chia part hoặc setup script tự tải.
