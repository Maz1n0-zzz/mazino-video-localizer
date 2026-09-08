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
# Doan ngan hon nguong nay coi nhu ElevenLabs KHONG phat ra tieng cho no.
# Xay ra that: ban dich lot markup ("<cau dich>") hoac chu Han -> EL coi la
# markup, khong doc, don ca cum ve MOT moc thoi gian -> t0 == t1 -> ffmpeg
# "-ss 76.347 -to 76.347" tra ve exit 234 va giet ca job (da mat 47 phut xoa
# sub truoc do). Chen im lang roi bao dong con hon lam do ca me.
MIN_SEG = 0.05            # giay
SILENCE_PER_CHAR = 0.06   # do dai im lang thay the, uoc theo so ky tu
MIN_GAP = 0.05           # khoang ho toi thieu giua hai cau khi phai day cau sau
MAX_TEMPO = 1.6          # nen nhanh toi da; hon nua thi giong meo, tha de tran
_TS = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)")


def _sec_to_ts(t):
    h=int(t//3600); m=int(t%3600//60); s=int(t%60); ms=int(round((t-int(t))*1000))
    if ms==1000: s+=1; ms=0
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _ts_to_sec(s):
    m=_TS.search(s)
    if not m: return 0.0
    h,mi,se,fr=m.groups()
    return int(h)*3600+int(mi)*60+int(se)+int(fr)/(10**len(fr))


def parse_srt(p):
    """-> [(t0_giay, t1_giay, text)].

    Truoc day ham nay VUT BO timestamp va chi tra ve chu, nen ban dub bi ghep
    sat nhau va troi khoi hinh: do tren video that, 130,4s im lang bi nem di,
    cau o phut 3:04 phat ra o giay 81,5 (lech 102,8s) va tu giay 155 tro di
    khong con tieng lan chu. Giu moc thoi gian de dat tung cau dung cho.
    """
    segs=[]
    for b in re.split(r"\n\s*\n", Path(p).read_text(encoding="utf-8-sig").strip()):
        L=[x for x in b.splitlines() if x.strip()]
        tl=next((x for x in L if "-->" in x), None)
        if not tl: continue
        txt=" ".join(L[L.index(tl)+1:]).strip()
        if not txt: continue
        a,_,b2=tl.partition("-->")
        segs.append((_ts_to_sec(a), _ts_to_sec(b2), txt))
    return segs


def chunk_segments(segs):
    """Gom cac doan thanh chunk <=MAX_CHARS, moi chunk giu list (text, off, length)."""
    chunks=[]; cur=[]; parts=[]; off=0
    for t0,t1,t in segs:
        add=(2 if parts else 0)+len(t)
        if parts and off+add>MAX_CHARS:
            chunks.append((("\n\n".join(parts)),cur)); cur=[]; parts=[]; off=0
            add=len(t)
        if parts: off+=2
        cur.append((t0, t1, t, off, len(t))); parts.append(t); off+=len(t)
    if parts: chunks.append((("\n\n".join(parts)),cur))
    return chunks


def _atempo(aud, sr, ratio):
    """Nen nhanh doan audio ma khong doi cao do (atempo cua ffmpeg)."""
    if ratio <= 1.001 or len(aud)==0: return aud
    with tempfile.TemporaryDirectory() as td:
        i=Path(td)/"i.wav"; o=Path(td)/"o.wav"
        sf.write(str(i), aud, sr)
        subprocess.run(["ffmpeg","-y","-i",str(i),"-filter:a",f"atempo={ratio:.4f}",str(o)],
                       check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        out,_=sf.read(str(o),dtype="float32")
        return out.mean(axis=1) if out.ndim>1 else out


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


def main(argv=None):
    """argv=None -> doc sys.argv (chay CLI). Truyen list -> goi duoc TRONG tien
    trinh, khong can python.exe ben ngoai (ban Windows dong goi khong co)."""
    ap=argparse.ArgumentParser()
    for k in ("srt","out","api-key","voice-id"): ap.add_argument("--"+k, required=True)
    ap.add_argument("--out-srt", default="")
    ap.add_argument("--model", default="eleven_v3")
    ap.add_argument("--speed", type=float, default=1.0)
    a=ap.parse_args(argv)

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
            chunk_sr=sf.info(str(wavp)).samplerate
            for c0,c1,text,off,ln in items:
                t0=st[off]+0.0; t1=et[off+ln-1]
                t0=max(0.0,t0-EDGE_KEEP*0); # dung dung char range -> da loai nghi \n\n
                if t1-t0 < MIN_SEG:
                    d=max(0.3, len(text)*SILENCE_PER_CHAR)
                    print(f"[el_clone] CANH BAO: ElevenLabs khong doc doan "
                          f"{t0:.3f}-{t1:.3f}s ({text[:50]!r}) -> chen {d:.2f}s im lang. "
                          f"Thuong do ban dich con markup hoac chu la.", flush=True)
                    sr=chunk_sr
                    rendered.append((c0, c1, text, np.zeros(int(d*chunk_sr), dtype=np.float32)))
                    continue
                segp=Path(td)/"s.wav"
                subprocess.run(["ffmpeg","-y","-i",str(wavp),"-ss",f"{t0:.3f}","-to",f"{t1:.3f}",str(segp)],
                               check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                aud,cur=sf.read(str(segp),dtype="float32")
                if aud.ndim>1: aud=aud.mean(axis=1)
                sr=cur; rendered.append((c0,c1,text,aud))
        print(f"[el_clone] chunk {ci}/{len(chunk_segments(segs))} xong", flush=True)

    # Dat tung cau vao DUNG moc thoi gian cua no tren truc video, khong ghep sat
    # nhau. Cau nao doc dai hon o thoi gian thi cho tran sang khoang lang ke tiep;
    # chi nen nhanh khi cau sau sap toi ma van chua doc xong.
    blocks=[]; placed=[]; prev_end=-MIN_GAP; n_fast=0; n_push=0
    for i,(c0,c1,text,aud) in enumerate(rendered):
        d=len(aud)/sr
        pos=max(c0, prev_end+MIN_GAP)
        if pos > c0+0.001: n_push+=1
        nxt = rendered[i+1][0] if i+1 < len(rendered) else None
        if nxt is not None:
            avail = nxt - pos - MIN_GAP
            if avail > MIN_SEG and d > avail:
                ratio = min(d/avail, MAX_TEMPO)
                aud = _atempo(aud, sr, ratio); d = len(aud)/sr; n_fast += 1
        placed.append((pos, aud))
        blocks.append(f"{i+1}\n{_sec_to_ts(pos)} --> {_sec_to_ts(pos+d)}\n{text}\n")
        prev_end = pos + d

    # Do dai track = het cau cuoi cua SRT (giu nguyen truc thoi gian video).
    end = max([prev_end] + [c1 for _c0,c1,_t,_a in rendered])
    track = np.zeros(int(end*sr)+1, dtype=np.float32)
    for pos, aud in placed:
        i0 = int(pos*sr); n = min(len(aud), len(track)-i0)
        if n > 0: track[i0:i0+n] += aud[:n]
    if n_fast or n_push:
        print(f"[el_clone] {n_fast} cau phai nen nhanh, {n_push} cau bi day muon "
              f"vi cau truoc chua doc xong", flush=True)
    pk=float(np.max(np.abs(track))) if track.size else 0.0
    if pk>1.0: track=track/pk*0.98
    sf.write(a.out, track, sr)
    if a.out_srt: Path(a.out_srt).write_text("\n".join(blocks),encoding="utf-8")
    print(f"[el_clone] XONG -> {a.out} ({len(track)/sr:.1f}s)", flush=True)


if __name__=="__main__":
    main()
