"""
Tu dien phien am tuy chinh cho TTS (EdgeTTS khong ho tro SSML lang-switch cho
giong khong phai "Multilingual", va thu vien edge_tts tu escape moi SSML gui
vao - da xac nhan qua nghien cuu thuc te - nen day la cach free duy nhat de
sua cach doc sai cac tu tieng Anh xen trong cau tieng Viet).

File dict nam ngoai PyInstaller bundle (giong cfg.json), de nguoi dung tu
chinh sua truc tiep tren may da cai, khong can build lai:
    <ROOT_DIR>/videotrans/pronounce_dict.json
"""
import json
import re
from pathlib import Path

from videotrans.configure.config import ROOT_DIR, logger

_DICT_PATH = Path(f"{ROOT_DIR}/videotrans/pronounce_dict.json")

_DEFAULT_DICT = {
    "Claude": "Cờ-lốt",
}

_cached_dict = None
_cached_pattern = None


def _load():
    global _cached_dict, _cached_pattern
    if _cached_dict is not None:
        return _cached_dict, _cached_pattern

    if not _DICT_PATH.exists():
        try:
            _DICT_PATH.parent.mkdir(parents=True, exist_ok=True)
            _DICT_PATH.write_text(
                json.dumps(_DEFAULT_DICT, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as e:
            logger.warning(f"Khong tao duoc pronounce_dict.json, bo qua tinh nang phien am: {e}")
            _cached_dict, _cached_pattern = {}, None
            return _cached_dict, _cached_pattern

    try:
        mapping = json.loads(_DICT_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"Khong doc duoc pronounce_dict.json ({e}), bo qua tinh nang phien am")
        mapping = {}

    if mapping:
        lower_map = {k.lower(): v for k, v in mapping.items()}
        # Tu dai den ngan de tranh 1 tu dai bi khop nham boi tu ngan la tien to cua no.
        pattern = re.compile(
            r"(?<!\w)(" + "|".join(re.escape(k) for k in sorted(mapping, key=len, reverse=True)) + r")(?!\w)",
            re.IGNORECASE,
        )
    else:
        lower_map, pattern = {}, None

    _cached_dict, _cached_pattern = lower_map, pattern
    return _cached_dict, _cached_pattern


def apply_pronounce_dict(text: str) -> str:
    """Thay cac tu trong tu dien bang cach viet gan dung am tieng Viet truoc khi dua vao TTS."""
    if not text:
        return text
    lower_map, pattern = _load()
    if not pattern:
        return text
    return pattern.sub(lambda m: lower_map[m.group(0).lower()], text)
