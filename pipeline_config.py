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
