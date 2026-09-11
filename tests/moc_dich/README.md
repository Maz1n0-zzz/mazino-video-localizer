# Mốc đo cho hai lượt soát sau khi dịch

Cặp phụ đề này là đầu vào chuẩn để đo `soat_glossary_srt()` và `viet_hoa_srt()`.

| File | Nội dung |
|---|---|
| `35889c8e3580_zh-cn_raw.srt` | Bản nhận dạng tiếng Trung, 83 cue |
| `35889c8e3580_vi_translated.srt` | Bản dịch thô, CHƯA qua lượt soát nào |

Chọn job này vì nó chạy ngày 09/09/2026, trước khi lượt soát glossary ra đời,
nên bản dịch còn nguyên lỗi. Đếm được 7 cue thiếu từ bắt buộc, đủ để phân biệt
model tốt với model kém. Các job sau ngày đó đều đã bị lượt soát vá rồi nên
không dùng làm mốc được.

Cách đo: đếm số cue thiếu từ bắt buộc trước và sau khi chạy hai lượt, bằng
chính hàm `_tu_con_thieu()` của dự án.

Kết quả đã đo ngày 11/09/2026:

| Model | Vá được | Thời gian |
|---|---|---|
| qwen2.5:7b | 6/7 | 71 giây |
| qwen2.5:14b | 6/7 | 176 giây |
