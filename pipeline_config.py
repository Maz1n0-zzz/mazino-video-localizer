"""Config mặc định dùng chung cho orchestrator.py (CLI) và app.py (Gradio UI)."""
import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"

DEFAULTS = {
    "source_lang": "zh-cn",
    "target_lang": "vi",
    "model_name": "medium",
    "voice_role": "vi-VN-HoaiMyNeural",
    # lama-auto: xoá logo/sub CỐ ĐỊNH bằng AI (đúng nhu cầu re-up TikTok). sttn-auto
    # cũ KHÔNG xoá được logo cố định — xem web_server.INPAINT_CHOICES.
    "inpaint_mode": "lama-auto",
    # Khoảng cách phụ đề mới tới đáy video (% chiều cao) — vùng an toàn TikTok.
    "subtitle_bottom_pct": 15,
    # Âm lượng TIẾNG GỐC giữ lại trong video cuối, tính theo % so với ban đầu.
    # 0 = tắt hẳn tiếng gốc (hành vi cũ), 100 = giữ nguyên. Mặc định 30% để nhạc
    # nền/tiếng động hiện trường còn nghe được nhưng không lấn giọng dub.
    "original_volume_pct": 30,
    # Engine dịch. Đo trên 58 cue thật của 1 video: Google sai bản chất (块钱 ->
    # "đô la", 张若雪 -> "Zhang Ruoxue", 白天蓬 -> "Trời nóng vào ban ngày",
    # xưng hô "Bạn" cho nhóm bạn trẻ). Gemini 0 lỗi bỏ dịch và hiểu được ý mỉa
    # mai; Qwen14b kém hơn 1 bậc nhưng không giới hạn quota -> để dự phòng.
    "trans_engine": "gemini",
    # Thể loại nội dung. Nạp bộ xưng hô + thuật ngữ riêng vào HAI lượt soát chạy
    # bằng qwen. Rỗng = không chỉ định, giữ nguyên hành vi cũ. Danh sách khoá hợp
    # lệ xem orchestrator.THE_LOAI.
    "the_loai": "",
}


def load_config():
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return {**DEFAULTS, **data}
        except Exception:
            pass
    return dict(DEFAULTS)


def save_config(**updates):
    merged = {**load_config(), **updates}
    CONFIG_PATH.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    return merged
