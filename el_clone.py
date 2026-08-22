#!/usr/bin/env python3
"""
Tao dub bang ElevenLabs bang cach GOI 1 LAN /with-timestamps cho ca bai roi cat
tung doan theo alignment -> KHONG lech ngu dieu (khac han goi rieng tung doan).

Chay bang PVT_PY (venv pyvideotrans co elevenlabs/numpy/soundfile). Xem chi tiet
benh + cach sua trong HANDOFF.md. Slice audio bang ffmpeg (-ss SAU -i).

    <pvt_py> el_clone.py --srt vi.srt --out dub.wav --out-srt clone.srt \
        --api-key KEY --voice-id VID --model eleven_v3 --speed 1.0
"""
import argparse, base64, json, re, subprocess, sys, tempfile, urllib.request
from pathlib import Path
import numpy as np
import soundfile as sf

MAX_CHARS = 2900          # gioi han an toan cho v3
SEC_PER_CHAR_TAG = 0.12   # nguong: >0.12s/ky tu -> the cam xuc bi DOC TO
EDGE_KEEP = 0.12          # chua 0.12s hai dau moi doan
GAP = 0.15
_TS = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)")


def _sec_to_ts(t):
    h=int(t//3600); m=int(t%3600//60); s=int(t%60); ms=int(round((t-int(t))*1000))
    if ms==1000: s+=1; ms=0
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_srt(p):
    segs=[]
    for b in re.split(r"\n\s*\n", Path(p).read_text(encoding="utf-8-sig").strip()):
        L=[x for x in b.splitlines() if x.strip()]
        tl=next((x for x in L if "-->" in x), None)
        if not tl: continue
        txt=" ".join(L[L.index(tl)+1:]).strip()
        if txt: segs.append(txt)
    return segs


def chunk_segments(segs):
    """Gom cac doan thanh chunk <=MAX_CHARS, moi chunk giu list (text, off, length)."""
    chunks=[]; cur=[]; parts=[]; off=0
    for t in segs:
        add=(2 if parts else 0)+len(t)
        if parts and off+add>MAX_CHARS:
            chunks.append((("\n\n".join(parts)),cur)); cur=[]; parts=[]; off=0
            add=len(t)
        if parts: off+=2
        cur.append((t, off, len(t))); parts.append(t); off+=len(t)
    if parts: chunks.append((("\n\n".join(parts)),cur))
    return chunks


def call_el(text, api_key, voice_id, model, speed):
    body={"text":text,"model_id":model,
          "voice_settings":{"stability":0.5,"similarity_boost":0.75,"speed":speed}}
    req=urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps",
        data=json.dumps(body).encode(), method="POST",
        headers={"xi-api-key":api_key,"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        d=json.loads(r.read())
    al=d["alignment"]
    return (base64.b64decode(d["audio_base64"]),
            al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"])


def spoken_tags_ok(text, chars, st, et):
    """True neu KHONG co the cam xuc bi doc to. Kiem tung [tag]."""
    if "".join(chars) != text:
        return None  # lech alignment -> bao loi rieng
    for m in re.finditer(r"\[[^\]]+\]", text):
        a,b=m.start(),m.end()
        if b<=len(st) and (et[b-1]-st[a])/max(1,b-a) > SEC_PER_CHAR_TAG:
            return False
    return True


def main():
    ap=argparse.ArgumentParser()
    for k in ("srt","out","api-key","voice-id"): ap.add_argument("--"+k, required=True)
    ap.add_argument("--out-srt", default="")
    ap.add_argument("--model", default="eleven_v3")
    ap.add_argument("--speed", type=float, default=1.0)
    a=ap.parse_args()

    segs=parse_srt(Path(a.srt))
    if not segs: sys.exit("[el_clone] srt rong")
    api_key=getattr(a,"api_key"); voice_id=getattr(a,"voice_id")

    sr=None; rendered=[]  # (text, np_audio)
    for ci,(ctext,items) in enumerate(chunk_segments(segs)):
        # goi + tu doc lai neu the cam xuc bi doc to (toi da 3 lan)
        for attempt in range(3):
            mp3,chars,st,et=call_el(ctext,api_key,voice_id,a.model,a.speed)
            ok=spoken_tags_ok(ctext,chars,st,et)
            if ok is None:
                sys.exit(f"[el_clone] alignment lech chunk {ci} (join != text)")
            if ok: break
            print(f"[el_clone] chunk {ci}: the cam xuc bi doc to, doc lai ({attempt+1})", flush=True)
        # ghi mp3 chunk -> wav de slice
        with tempfile.TemporaryDirectory() as td:
            mp3p=Path(td)/"c.mp3"; wavp=Path(td)/"c.wav"; mp3p.write_bytes(mp3)
            subprocess.run(["ffmpeg","-y","-i",str(mp3p),str(wavp)],
                           check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            for text,off,ln in items:
                t0=st[off]+0.0; t1=et[off+ln-1]
                t0=max(0.0,t0-EDGE_KEEP*0); # dung dung char range -> da loai nghi \n\n
                segp=Path(td)/"s.wav"
                subprocess.run(["ffmpeg","-y","-i",str(wavp),"-ss",f"{t0:.3f}","-to",f"{t1:.3f}",str(segp)],
                               check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                aud,cur=sf.read(str(segp),dtype="float32")
                if aud.ndim>1: aud=aud.mean(axis=1)
                sr=cur; rendered.append((text,aud))
        print(f"[el_clone] chunk {ci}/{len(chunk_segments(segs))} xong", flush=True)

    # Ghep noi tiep + xuat srt (giong f5_clone)
    parts=[]; blocks=[]; cursor=0.0
    for i,(text,aud) in enumerate(rendered):
        d=len(aud)/sr
        parts.append(aud); parts.append(np.zeros(int(GAP*sr),dtype=np.float32))
        blocks.append(f"{i+1}\n{_sec_to_ts(cursor)} --> {_sec_to_ts(cursor+d)}\n{text}\n")
        cursor+=d+GAP
    track=np.concatenate(parts) if parts else np.zeros(1,dtype=np.float32)
    pk=float(np.max(np.abs(track))) if track.size else 0.0
    if pk>1.0: track=track/pk*0.98
    sf.write(a.out, track, sr)
    if a.out_srt: Path(a.out_srt).write_text("\n".join(blocks),encoding="utf-8")
    print(f"[el_clone] XONG -> {a.out} ({len(track)/sr:.1f}s)", flush=True)


if __name__=="__main__":
    main()
