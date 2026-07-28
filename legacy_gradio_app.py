#!/usr/bin/env python3
"""Phase 3: Gradio UI cho pipeline localize video (VSR + pyvideotrans).
Chạy: source ui_env/bin/activate && python3 app.py
"""
import asyncio
import shutil
import subprocess
from pathlib import Path

import gradio as gr

import orchestrator as orch
from pipeline_config import load_config, save_config

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_ROOT / "outputs"
CFG = load_config()

# Evose "Video/App" palette — nền navy/đen sâu, accent Blue->Cyan cho icon/nút/viền.
EVOSE_BG_TOP = "#0b1220"
EVOSE_BG_BOTTOM = "#05070d"
EVOSE_NAVY = "#0f172a"
EVOSE_PANEL = "rgba(15, 23, 42, 0.55)"
EVOSE_BORDER = "rgba(59, 130, 246, 0.18)"
EVOSE_BORDER_SOFT = "rgba(148, 163, 184, 0.18)"
EVOSE_WHITE = "#FFFFFF"
EVOSE_OFFWHITE = "#E7ECF6"
EVOSE_TEXT_SUBDUED = "#94a3b8"
EVOSE_ACCENT_1 = "#1d4ed8"
EVOSE_ACCENT_2 = "#38bdf8"
EVOSE_WARNING = "#F59E0B"
EVOSE_ERROR = "#EF4444"
EVOSE_SUCCESS = "#10B981"

evose_theme = gr.themes.Base(
    primary_hue=gr.themes.colors.blue,
    neutral_hue=gr.themes.colors.slate,
    font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "sans-serif"],
    font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "ui-monospace", "monospace"],
).set(
    body_background_fill=EVOSE_BG_BOTTOM,
    body_background_fill_dark=EVOSE_BG_BOTTOM,
    background_fill_primary=EVOSE_NAVY,
    background_fill_primary_dark=EVOSE_NAVY,
    background_fill_secondary=EVOSE_NAVY,
    background_fill_secondary_dark=EVOSE_NAVY,
    body_text_color=EVOSE_OFFWHITE,
    body_text_color_dark=EVOSE_OFFWHITE,
    body_text_color_subdued=EVOSE_TEXT_SUBDUED,
    body_text_color_subdued_dark=EVOSE_TEXT_SUBDUED,
    border_color_primary=EVOSE_BORDER_SOFT,
    border_color_primary_dark=EVOSE_BORDER_SOFT,
    border_color_accent=EVOSE_ACCENT_2,
    border_color_accent_dark=EVOSE_ACCENT_2,
    link_text_color=EVOSE_ACCENT_2,
    link_text_color_dark=EVOSE_ACCENT_2,
    link_text_color_hover=EVOSE_WHITE,
    link_text_color_hover_dark=EVOSE_WHITE,
    block_background_fill="transparent",
    block_background_fill_dark="transparent",
    block_border_width="0px",
    block_border_width_dark="0px",
    block_label_text_color=EVOSE_TEXT_SUBDUED,
    block_label_text_color_dark=EVOSE_TEXT_SUBDUED,
    block_label_background_fill="transparent",
    block_label_background_fill_dark="transparent",
    block_title_text_color=EVOSE_WHITE,
    block_title_text_color_dark=EVOSE_WHITE,
    block_info_text_color=EVOSE_TEXT_SUBDUED,
    block_info_text_color_dark=EVOSE_TEXT_SUBDUED,
    panel_background_fill="transparent",
    panel_background_fill_dark="transparent",
    panel_border_color="transparent",
    panel_border_color_dark="transparent",
    input_background_fill="rgba(3, 7, 18, 0.75)",
    input_background_fill_dark="rgba(3, 7, 18, 0.75)",
    input_border_color=EVOSE_BORDER,
    input_border_color_dark=EVOSE_BORDER,
    input_border_color_focus=EVOSE_ACCENT_2,
    input_border_color_focus_dark=EVOSE_ACCENT_2,
    button_primary_background_fill=f"linear-gradient(90deg, {EVOSE_ACCENT_1}, {EVOSE_ACCENT_2})",
    button_primary_background_fill_dark=f"linear-gradient(90deg, {EVOSE_ACCENT_1}, {EVOSE_ACCENT_2})",
    button_primary_background_fill_hover=f"linear-gradient(90deg, {EVOSE_ACCENT_2}, {EVOSE_ACCENT_2})",
    button_primary_background_fill_hover_dark=f"linear-gradient(90deg, {EVOSE_ACCENT_2}, {EVOSE_ACCENT_2})",
    button_primary_text_color=EVOSE_WHITE,
    button_primary_text_color_dark=EVOSE_WHITE,
    button_primary_border_color=EVOSE_ACCENT_2,
    button_primary_border_color_dark=EVOSE_ACCENT_2,
    button_secondary_background_fill="rgba(15, 23, 42, 0.7)",
    button_secondary_background_fill_dark="rgba(15, 23, 42, 0.7)",
    button_secondary_text_color=EVOSE_OFFWHITE,
    button_secondary_text_color_dark=EVOSE_OFFWHITE,
    button_secondary_border_color=EVOSE_BORDER,
    button_secondary_border_color_dark=EVOSE_BORDER,
    error_background_fill=EVOSE_ERROR,
    error_background_fill_dark=EVOSE_ERROR,
    error_border_color=EVOSE_ERROR,
    error_border_color_dark=EVOSE_ERROR,
    error_text_color=EVOSE_WHITE,
    error_text_color_dark=EVOSE_WHITE,
    shadow_drop="0 2px 10px 0 rgba(0,0,0,0.35)",
    shadow_drop_lg="0 6px 22px 0 rgba(0,0,0,0.45)",
)

# --- Icon set (Feather-style inline SVG, 1 màu currentColor) ---
def _icon(paths, vb="0 0 24 24"):
    return (f'<svg viewBox="{vb}" fill="none" stroke="currentColor" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round">{paths}</svg>')

ICON_VIDEO = _icon('<rect x="3" y="6" width="12" height="12" rx="2"/><path d="M15 10l4.55-2.27A1 1 0 0 1 21 8.6v6.8a1 1 0 0 1-1.45.87L15 14"/>')
ICON_SETTINGS = _icon('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>')
ICON_TREND = _icon('<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>')
ICON_SHIELD = _icon('<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 12 15 16 10"/>')
ICON_DOWNLOAD = _icon('<path d="M8 17l4 4 4-4"/><path d="M12 12v9"/><path d="M20.88 18.09A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.29"/>')
ICON_GLOBE = _icon('<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>')
ICON_HEADPHONES = _icon('<path d="M3 18v-6a9 9 0 0 1 18 0v6"/><path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z"/>')
ICON_GAUGE = _icon('<path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z"/><path d="M12 12l4-4"/><circle cx="12" cy="12" r="1.5"/>')
ICON_HEART = _icon('<path d="M20.8 4.6c-1.8-1.8-4.7-1.8-6.5 0L12 6.9l-2.3-2.3c-1.8-1.8-4.7-1.8-6.5 0-1.8 1.8-1.8 4.7 0 6.5L12 20.3l8.8-8.8c1.8-1.8 1.8-4.8 0-6.9z"/>')
ICON_PLAY = _icon('<polygon points="5 3 19 12 5 21 5 3"/>')

def icon_label(icon_svg, text):
    return f'<div class="opt-label">{icon_svg}<span>{text}</span></div>'

def card_header(icon_svg, text):
    return f'<div class="card-header"><span class="icon-badge">{icon_svg}</span><span class="card-title">{text}</span></div>'

DECOR_HTML = """
<div class="evo-bg">
  <div class="evo-moon"></div>
  <div class="evo-dots evo-dots-1"></div>
  <div class="evo-dots evo-dots-2"></div>
  <div class="evo-dots evo-dots-3"></div>
  <svg class="evo-lines" viewBox="0 0 220 220" preserveAspectRatio="none">
    <line x1="10" y1="210" x2="210" y2="10" stroke="#38bdf8" stroke-width="1"/>
    <line x1="50" y1="210" x2="210" y2="50" stroke="#38bdf8" stroke-width="1"/>
    <line x1="90" y1="210" x2="210" y2="90" stroke="#38bdf8" stroke-width="1"/>
  </svg>
  <svg class="evo-mountains" viewBox="0 0 1600 260" preserveAspectRatio="none">
    <polygon points="0,260 0,170 180,70 380,160 600,50 850,150 1080,70 1320,165 1600,90 1600,260" fill="#132a4f" opacity="0.55"/>
    <polygon points="0,260 0,215 260,140 520,210 780,120 1040,205 1300,130 1600,195 1600,260" fill="#1b3a6b" opacity="0.5"/>
  </svg>
  <svg class="evo-leaf evo-leaf-1" viewBox="0 0 60 140"><path d="M30 4 C52 32 52 108 30 136 C8 108 8 32 30 4 Z" fill="none" stroke="#38bdf8" stroke-width="1"/><line x1="30" y1="10" x2="30" y2="130" stroke="#38bdf8" stroke-width="1"/></svg>
  <svg class="evo-leaf evo-leaf-2" viewBox="0 0 60 140"><path d="M30 4 C52 32 52 108 30 136 C8 108 8 32 30 4 Z" fill="none" stroke="#38bdf8" stroke-width="1"/><line x1="30" y1="10" x2="30" y2="130" stroke="#38bdf8" stroke-width="1"/></svg>
</div>
"""

EVOSE_CSS = f"""
@import url('https://fonts.googleapis.com/css2?family=Oswald:wght@600;700&display=swap');

.gradio-container {{
    background: radial-gradient(circle at 85% 0%, {EVOSE_BG_TOP} 0%, {EVOSE_BG_BOTTOM} 60%) !important;
    position: relative;
    z-index: 0;
    overflow-x: hidden;
}}
.evo-bg {{
    position: fixed; inset: 0; z-index: -1; overflow: hidden; pointer-events: none;
}}
.evo-moon {{
    position: absolute; top: -90px; right: -60px; width: 300px; height: 300px; border-radius: 50%;
    background: radial-gradient(circle at 35% 35%, #3b5580 0%, #16233f 55%, transparent 75%);
    box-shadow: 0 0 90px 24px rgba(56, 189, 248, 0.10);
}}
.evo-dots {{
    position: absolute;
    background-image: radial-gradient(rgba(148, 163, 184, 0.35) 1.2px, transparent 1.6px);
    background-size: 14px 14px;
}}
.evo-dots-1 {{ top: 26px; right: 300px; width: 110px; height: 90px; }}
.evo-dots-2 {{ bottom: 60px; left: 46%; width: 140px; height: 100px; opacity: 0.6; }}
.evo-dots-3 {{ top: 45%; left: 2%; width: 90px; height: 90px; opacity: 0.35; }}
.evo-lines {{ position: absolute; top: 0; right: 0; width: 220px; height: 220px; opacity: 0.3; }}
.evo-mountains {{ position: absolute; bottom: 0; left: 0; width: 100%; height: 240px; opacity: 0.7; }}
.evo-leaf {{ position: absolute; width: 46px; height: 130px; opacity: 0.35; }}
.evo-leaf-1 {{ bottom: 6px; left: -4px; }}
.evo-leaf-2 {{ top: 30%; right: -4px; transform: scaleX(-1); }}

#evo-header-row {{
    display: flex; align-items: center; gap: 20px;
    padding: 6px 0 22px 0; margin-bottom: 6px; position: relative; z-index: 1;
}}
.evo-header-badge {{
    width: 64px; height: 64px; border-radius: 16px; flex-shrink: 0;
    background: linear-gradient(135deg, {EVOSE_ACCENT_1}, {EVOSE_ACCENT_2});
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 0 26px rgba(56, 189, 248, 0.45);
}}
.evo-header-badge svg {{ width: 30px; height: 30px; color: #fff; }}
.evo-title {{
    font-family: "Oswald", sans-serif; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.03em; font-size: 2.1rem; color: #fff; margin: 0; line-height: 1.1;
}}
.evo-subtitle {{ color: {EVOSE_TEXT_SUBDUED}; font-size: 0.92rem; margin-top: 6px; }}

.card {{
    position: relative; z-index: 1;
    background: {EVOSE_PANEL};
    backdrop-filter: blur(8px);
    border: 1px solid {EVOSE_BORDER};
    border-radius: 20px !important;
    padding: 20px !important;
    overflow: hidden;
}}
.card::after {{
    content: ""; position: absolute; right: -24px; bottom: -20px; width: 170px; height: 120px;
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 150'><polygon points='0,150 40,60 90,110 140,30 200,90 200,150' fill='%23193150'/></svg>");
    background-repeat: no-repeat; opacity: 0.55; pointer-events: none;
}}
.card-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }}
.card-header .icon-badge {{
    width: 28px; height: 28px; border-radius: 8px; flex-shrink: 0;
    background: linear-gradient(135deg, {EVOSE_ACCENT_1}, {EVOSE_ACCENT_2});
    display: flex; align-items: center; justify-content: center;
}}
.card-header .icon-badge svg {{ width: 14px; height: 14px; color: #fff; }}
.card-header .card-title {{
    font-family: "Oswald", sans-serif; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.03em; font-size: 0.92rem; color: {EVOSE_OFFWHITE};
}}

.opt-row {{ display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }}
.opt-label {{
    display: flex; align-items: center; gap: 8px; min-width: 190px; flex-shrink: 0;
    color: #cbd5e1; font-size: 0.88rem;
}}
.opt-label svg {{ width: 15px; height: 15px; color: {EVOSE_ACCENT_2}; flex-shrink: 0; }}
.opt-pill {{ flex: 1; }}

button.primary {{
    border-radius: 999px !important;
    font-family: "Oswald", sans-serif !important;
    text-transform: uppercase !important;
    letter-spacing: 0.04em !important;
    font-weight: 700 !important;
    box-shadow: 0 6px 22px -4px rgba(56, 189, 248, 0.5) !important;
    transition: box-shadow 150ms ease-out, transform 150ms ease-out !important;
    border: none !important;
}}
button.primary::before {{ content: "▶"; margin-right: 8px; font-size: 0.75em; }}
button.primary:hover {{
    box-shadow: 0 8px 28px -4px rgba(56, 189, 248, 0.7) !important;
    transform: translateY(-1px);
}}
button.secondary {{ border-radius: 999px !important; font-weight: 600 !important; }}

#evo-run-btn {{ height: 52px !important; }}
#evo-save-btn {{
    opacity: 0.6; background: transparent !important; border: none !important;
    box-shadow: none !important; margin-top: -4px;
}}
#evo-save-btn:hover {{ opacity: 1; }}

.upload-box {{
    border-style: dashed !important;
    border-color: {EVOSE_BORDER} !important;
    border-width: 1.5px !important;
    background: rgba(3, 7, 18, 0.35) !important;
    border-radius: 14px !important;
}}
.upload-box:hover {{ border-color: {EVOSE_ACCENT_2} !important; }}

#evose-log textarea {{
    font-family: "JetBrains Mono", ui-monospace, monospace !important;
    color: {EVOSE_OFFWHITE} !important;
    background: rgba(3, 7, 18, 0.8) !important;
    border-radius: 14px !important;
    font-size: 0.85rem !important;
}}
label span {{ font-weight: 500 !important; }}
"""
OUTPUT_DIR.mkdir(exist_ok=True)

LANG_CHOICES = [
    ("Tiếng Trung (giản thể)", "zh-cn"),
    ("Tiếng Trung (phồn thể)", "zh-tw"),
    ("Tiếng Anh", "en"),
    ("Tiếng Việt", "vi"),
    ("Tiếng Nhật", "ja"),
    ("Tiếng Hàn", "ko"),
    ("Tiếng Pháp", "fr"),
    ("Tiếng Đức", "de"),
    ("Tiếng Tây Ban Nha", "es"),
    ("Tiếng Nga", "ru"),
    ("Tiếng Thái", "th"),
    ("Tiếng Ý", "it"),
    ("Tiếng Bồ Đào Nha", "pt"),
]
MODEL_CHOICES = ["tiny", "base", "small", "medium", "large-v3"]
INPAINT_CHOICES = ["sttn-auto", "sttn-det", "lama", "propainter", "opencv"]
LOCALE_OVERRIDE = {"zh-cn": "zh-CN", "zh-tw": "zh-TW"}

_ALL_VOICES = []
_DEFAULT_VOICES = {
    "vi": ["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"],
    "en": ["en-US-GuyNeural", "en-US-JennyNeural"],
    "zh-cn": ["zh-CN-XiaoxiaoNeural", "zh-CN-YunyangNeural"],
}


def _fetch_all_voices():
    global _ALL_VOICES
    try:
        import edge_tts
        _ALL_VOICES = asyncio.run(edge_tts.list_voices())
    except Exception as e:
        print(f"[warn] Không tải được danh sách voice Edge-TTS lúc khởi động: {e}")
        _ALL_VOICES = []


_fetch_all_voices()


def voices_for_lang(lang_code):
    prefix = LOCALE_OVERRIDE.get(lang_code, lang_code).lower()
    matched = [v["ShortName"] for v in _ALL_VOICES if v["Locale"].lower().startswith(prefix)]
    if not matched:
        matched = _DEFAULT_VOICES.get(lang_code, [])
    return matched


def on_target_lang_change(target_lang):
    choices = voices_for_lang(target_lang)
    return gr.update(choices=choices, value=choices[0] if choices else None)


def run_pipeline(video_path, source_lang, target_lang, model_name, voice_role, inpaint_mode):
    if not video_path:
        yield "Chưa chọn video đầu vào.", None, None
        return

    input_video = Path(video_path).resolve()
    work_dir = OUTPUT_DIR / f"_work_{input_video.stem}"
    work_dir.mkdir(parents=True, exist_ok=True)

    logs = []

    def log(msg):
        logs.append(msg)
        return "\n".join(logs)

    try:
        orch.preflight_checks()

        yield log("[1/4] Đang xoá sub/logo cũ (video-subtitle-remover)..."), None, None
        cleaned = orch.remove_old_subtitles(input_video, work_dir, inpaint_mode)
        yield log("✓ Xong bước 1/4"), None, None

        yield log("[2/4] Đang transcribe + dịch + dub (pyvideotrans)... "
                   "(lần đầu chạy 1 model mới sẽ mất thêm thời gian tải model)"), None, None
        dub_audio, dub_srt = orch.transcribe_translate_dub(
            input_video, work_dir, source_lang, target_lang, model_name, voice_role,
        )
        yield log("✓ Xong bước 2/4"), None, None

        yield log("[3/4] Đang tạo lại phụ đề đúng vị trí cho video này..."), None, None
        width, height = orch.probe_resolution(cleaned)
        ass_path = orch.build_fixed_ass(dub_srt, work_dir, width, height)
        yield log("✓ Xong bước 3/4"), None, None

        yield log("[4/4] Đang ghép video cuối cùng..."), None, None
        output_path = OUTPUT_DIR / f"{input_video.stem}_{target_lang}.mp4"
        orch.compose_final(cleaned, dub_audio, ass_path, output_path)
        yield log(f"✓ Hoàn tất! File: {output_path}"), str(output_path), str(output_path)
    except orch.PipelineStageError as e:
        yield log(f"[LỖI ở bước: {e.stage}]\n{e.detail}"), None, None
    except Exception as e:
        yield log(f"[LỖI không xác định] {e}"), None, None
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def save_current_as_default(source_lang, target_lang, model_name, voice_role, inpaint_mode):
    save_config(
        source_lang=source_lang, target_lang=target_lang,
        model_name=model_name, voice_role=voice_role, inpaint_mode=inpaint_mode,
    )
    return f"✓ Đã lưu làm mặc định (config.json): {source_lang} → {target_lang}, model={model_name}, voice={voice_role}, inpaint={inpaint_mode}"


with gr.Blocks(title="Video Localization Pipeline") as demo:
    gr.HTML(DECOR_HTML)

    gr.HTML(
        f'<div id="evo-header-row"><div class="evo-header-badge">{ICON_VIDEO}</div>'
        '<div><div class="evo-title">Video Localization Pipeline</div>'
        '<div class="evo-subtitle">Xoá sub/logo cũ → transcribe → dịch → dub → ghép sub mới đúng vị trí.</div></div></div>'
    )

    with gr.Row():
        with gr.Column():
            with gr.Group(elem_classes="card"):
                gr.HTML(card_header(ICON_VIDEO, "Video gốc"))
                video_in = gr.Video(label="", show_label=False, sources=["upload"], elem_classes="upload-box")

            with gr.Group(elem_classes="card"):
                gr.HTML(card_header(ICON_SETTINGS, "Tuỳ chọn ngôn ngữ & mô hình"))

                with gr.Row(elem_classes="opt-row"):
                    gr.HTML(icon_label(ICON_GLOBE, "Ngôn ngữ gốc"))
                    source_lang = gr.Dropdown(
                        choices=LANG_CHOICES, value=CFG["source_lang"],
                        show_label=False, container=False, elem_classes="opt-pill",
                    )
                with gr.Row(elem_classes="opt-row"):
                    gr.HTML(icon_label(ICON_GLOBE, "Ngôn ngữ đích"))
                    target_lang = gr.Dropdown(
                        choices=LANG_CHOICES, value=CFG["target_lang"],
                        show_label=False, container=False, elem_classes="opt-pill",
                    )
                with gr.Row(elem_classes="opt-row"):
                    gr.HTML(icon_label(ICON_HEADPHONES, "Giọng đọc (Edge-TTS)"))
                    voice_role = gr.Dropdown(
                        choices=voices_for_lang(CFG["target_lang"]),
                        value=CFG["voice_role"] if CFG["voice_role"] in voices_for_lang(CFG["target_lang"])
                        else (voices_for_lang(CFG["target_lang"]) or [None])[0],
                        show_label=False, container=False, elem_classes="opt-pill",
                    )
                with gr.Row(elem_classes="opt-row"):
                    gr.HTML(icon_label(ICON_GAUGE, "Whisper model (STT)"))
                    model_name = gr.Dropdown(
                        choices=MODEL_CHOICES, value=CFG["model_name"],
                        show_label=False, container=False, elem_classes="opt-pill",
                    )
                with gr.Row(elem_classes="opt-row"):
                    gr.HTML(icon_label(ICON_HEART, "Chế độ xoá sub cũ (VSR)"))
                    inpaint_mode = gr.Dropdown(
                        choices=INPAINT_CHOICES, value=CFG["inpaint_mode"],
                        show_label=False, container=False, elem_classes="opt-pill",
                    )

            run_btn = gr.Button("Chạy pipeline", variant="primary", elem_id="evo-run-btn")
            save_default_btn = gr.Button("Lưu làm mặc định", variant="secondary", size="sm", elem_id="evo-save-btn")

        with gr.Column():
            with gr.Group(elem_classes="card"):
                gr.HTML(card_header(ICON_TREND, "Tiến trình"))
                log_out = gr.Textbox(show_label=False, lines=10, interactive=False, elem_id="evose-log")

            with gr.Group(elem_classes="card"):
                gr.HTML(card_header(ICON_SHIELD, "Kết quả"))
                video_out = gr.Video(label="", show_label=False, elem_classes="upload-box")

            with gr.Group(elem_classes="card"):
                gr.HTML(card_header(ICON_DOWNLOAD, "Tải file kết quả"))
                file_out = gr.File(label="", show_label=False, elem_classes="upload-box")

    target_lang.change(on_target_lang_change, inputs=target_lang, outputs=voice_role)
    run_btn.click(
        run_pipeline,
        inputs=[video_in, source_lang, target_lang, model_name, voice_role, inpaint_mode],
        outputs=[log_out, video_out, file_out],
    )
    save_default_btn.click(
        save_current_as_default,
        inputs=[source_lang, target_lang, model_name, voice_role, inpaint_mode],
        outputs=log_out,
    )

if __name__ == "__main__":
    demo.queue().launch(theme=evose_theme, css=EVOSE_CSS)
