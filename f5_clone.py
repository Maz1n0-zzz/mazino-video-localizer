#!/usr/bin/env python3
"""
Tao track audio dub bang giong CLONE (F5-TTS) theo timing cua file .srt da dich.

CHAY BANG f5env (moi truong rieng co f5-tts), KHONG phai web_env/pyvideotrans venv:
    f5env/bin/python f5_clone.py --ref ref.wav --ref-text "..." \
        --srt vi.srt --out dub.wav --model-dir <thu muc co model_last.pt + vocab.txt>

Y tuong: pyvideotrans lo transcribe+dich ra vi.srt (co timestamp + text tieng Viet
tung cau). Script nay doc vi.srt, dung F5 sinh tung cau bang giong clone, dat dung
vi tri thoi gian roi ghep thanh 1 track audio khop timing -> thay cho ban dub
Edge-TTS. Timing bam theo srt (giong co che voice_autorate cua pyvideotrans).
"""
import argparse
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import soundfile as sf

# Gioi han toc do khi nen cho vua slot (tranh giong "chipmunk"). Neu cau qua dai
# so voi slot, chi nen toi muc nay roi cho phep tran sang chut, khong nen qua.
MAX_SPEEDUP = 1.8


def _fit_duration(aud, sr, target_sec):
    """Neu audio dai hon slot -> nen (tang toc, giu cao do) bang ffmpeg atempo.
    Ngan hon slot -> giu nguyen (se co khoang lang sau). Tra ve audio da chinh."""
    cur = len(aud) / sr
    if cur <= target_sec * 1.05 or target_sec <= 0:
        return aud
    factor = min(cur / target_sec, MAX_SPEEDUP)
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "s.wav"
        dst = Path(td) / "d.wav"
        sf.write(str(src), aud, sr)
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(src), "-filter:a", f"atempo={factor:.4f}", str(dst)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        out, _ = sf.read(str(dst), dtype="float32")
    return out

_TS = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)")


def _ts_to_sec(ts: str) -> float:
    h, m, s, ms = _TS.match(ts.strip()).groups()
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_srt(path: Path):
    """Tra ve list (start_sec, end_sec, text) tu file .srt."""
    blocks = re.split(r"\n\s*\n", Path(path).read_text(encoding="utf-8-sig").strip())
    segs = []
    for b in blocks:
        lines = [l for l in b.splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        # dong dau co the la so thu tu; tim dong chua "-->"
        ts_line = next((l for l in lines if "-->" in l), None)
        if not ts_line:
            continue
        start_s, end_s = ts_line.split("-->")
        text_lines = lines[lines.index(ts_line) + 1:]
        text = " ".join(text_lines).strip()
        if not text:
            continue
        segs.append((_ts_to_sec(start_s), _ts_to_sec(end_s), text))
    return segs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True, help="File giong mau (wav/mp3)")
    ap.add_argument("--ref-text", default="", help="Loi thoai cua giong mau (viet thuong). Rong = F5 tu transcribe")
    ap.add_argument("--srt", required=True, help="File .srt da dich (tieng Viet)")
    ap.add_argument("--out", required=True, help="File wav dub xuat ra")
    ap.add_argument("--model-dir", required=True, help="Thu muc chua model_last.pt + vocab.txt")
    ap.add_argument("--device", default="mps", help="mps / cuda / cpu")
    ap.add_argument("--model-name", default="F5TTS_Base")
    args = ap.parse_args()

    from f5_tts.api import F5TTS

    model_dir = Path(args.model_dir)
    ckpt = model_dir / "model_last.pt"
    vocab = model_dir / "vocab.txt"
    for p in (ckpt, vocab):
        if not p.exists():
            sys.exit(f"[f5_clone] Thieu file: {p}")

    segs = parse_srt(Path(args.srt))
    if not segs:
        sys.exit(f"[f5_clone] Khong doc duoc cau nao tu {args.srt}")

    print(f"[f5_clone] Nap model F5 ({args.device})...", flush=True)
    t0 = time.time()
    f5 = F5TTS(model=args.model_name, ckpt_file=str(ckpt), vocab_file=str(vocab), device=args.device)
    print(f"[f5_clone] Nap xong {time.time()-t0:.1f}s. Sinh {len(segs)} cau...", flush=True)

    ref_text = args.ref_text.strip().lower()
    sr = None
    rendered = []  # (start_sec, np_audio)
    for i, (start_s, end_s, text) in enumerate(segs):
        slot = max(0.3, end_s - start_s)
        gen_text = text.strip().lower()  # model VN train o dang lowercase
        t1 = time.time()
        # Sinh o toc do tu nhien (KHONG dung fix_duration - no tinh ca giong mau
        # nen lech timing), roi tu nen cho vua slot bang atempo.
        wav, cur_sr, _ = f5.infer(
            ref_file=args.ref, ref_text=ref_text, gen_text=gen_text,
            remove_silence=True,
        )
        sr = cur_sr
        aud = np.asarray(wav, dtype=np.float32)
        nat = len(aud) / sr
        aud = _fit_duration(aud, sr, slot)
        rendered.append((start_s, aud))
        print(f"[f5_clone] cau {i+1}/{len(segs)} slot={slot:.1f}s nat={nat:.1f}s -> {len(aud)/sr:.1f}s  ({time.time()-t1:.1f}s)", flush=True)

    # Ghep len 1 timeline im lang theo dung start time cua tung cau
    total_end = 0.0
    for start_s, aud in rendered:
        total_end = max(total_end, start_s + len(aud) / sr)
    track = np.zeros(int((total_end + 0.5) * sr), dtype=np.float32)
    for start_s, aud in rendered:
        off = int(start_s * sr)
        end = min(off + len(aud), len(track))
        track[off:end] += aud[: end - off]
    # chong clip
    peak = float(np.max(np.abs(track))) if track.size else 0.0
    if peak > 1.0:
        track = track / peak * 0.98

    sf.write(args.out, track, sr)
    print(f"[f5_clone] XONG -> {args.out}  ({len(track)/sr:.1f}s)", flush=True)


if __name__ == "__main__":
    main()
