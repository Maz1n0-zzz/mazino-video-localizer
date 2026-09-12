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
# Tran nen khi chi muon cau doc gon trong O CUA CHINH NO. Thap hon MAX_TEMPO
# nhieu vi day la truong hop thuong, tai phai khong nhan ra.
# 1,20 la muc PeiPei Dub dat mac dinh. Da thu 1,20 tren video that 12/9/2026:
# Mazino nghe ra ngay "voice moi chay nhanh hon voice goc". Ha ve 1,10.
# Doi lai vai cau se tran sang khoang lang phia sau - chap nhan duoc, vi buoc
# rut gon ban dich (_RUT_GON_PROMPT) lo phan con lai.
TRAN_NEN_O = 1.10

# --- Do 12/9/2026 tren video that (64 cue, 295s) ---
# Bien o cua TEN VAD KHONG phai bien tieng noi: no ep moi doan dai toi thieu
# 1000ms bang cach nuot doan ngan ben canh (videotrans/process/vad.py:185
# `seg[0] = prev[0]`), roi chan tren o 5s. Ket qua 44/64 cue dai >=4s va 96%
# thoi luong video nam trong mot o nao do. Giong Viet neo vao DAU O nen doc
# xong som: 29 cue thua >0,8s, cong lai 73,5s chet. Mazino nghe ra la "voice
# moi khong de dung thoi diem voice goc".
# Cach chua: do nang luong ban GOC trong tung o de tim doan THAT SU co tieng,
# roi dat cau tieng Viet vao doan do.
KHUNG_FRAME_MS = 20           # do dai 1 khung khi do nang luong
KHUNG_MIN_RUN_MS = 100        # phai keu lien tuc chung nay moi tinh la tieng noi
KHUNG_TUONG_PHAN_DB = 8.0     # nen/dinh chenh duoi muc nay -> khong du tin, bo qua
KHUNG_MIN_DICH = 0.15         # dich duoi muc nay thi thoi, tranh rung vat
KHUNG_MIN_SPAN = 0.20         # cua so ngan hon muc nay -> khong tin
# Cue nguon CHI co tieng cuoi thi khong long tieng: chen "Ha ha ha" tieng Viet
# dai 0,4s vao o 7,5s chi tao them 7,1s im lang, trong khi tieng cuoi goc van
# con trong nen (original_volume_pct) va nghe tu nhien hon.
_CUOI_RE = re.compile(r"^[\u54c8\u563f\u5475\u563b]{2,}$")
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


def chi_tieng_cuoi(text_goc):
    """True khi cue NGUON chi gom tieng cuoi (哈哈, 嘿嘿...). Cue nhu vay bo qua,
    khong long tieng. Chi nhan dien tren ban goc: ban dich da thanh "Ha ha ha"
    nen khong con phan biet duoc voi loi thoai that."""
    if not text_goc:
        return False
    loi = re.sub(r"[\s\W_]+", "", text_goc, flags=re.UNICODE)
    return bool(_CUOI_RE.match(loi))


def doc_mono(path, sr_dich=16000):
    """Rut audio 1 kenh tu video hoac wav bat ky -> (mang float32, sample rate).

    16kHz la du: ta chi do NANG LUONG theo khung 20ms, khong nhan dang gi.
    """
    with tempfile.TemporaryDirectory() as td:
        w = Path(td) / "g.wav"
        subprocess.run(["ffmpeg", "-y", "-i", str(path), "-vn", "-ac", "1",
                        "-ar", str(sr_dich), str(w)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        x, sr = sf.read(str(w), dtype="float32")
    if x.ndim > 1:
        x = x.mean(axis=1)
    return x, sr


def khung_mot_cue(x, sr, c0, c1):
    """Tim doan THAT SU co tieng noi ben trong o [c0,c1] cua ban goc.

    -> (s0, s1) tuyet doi tren truc video, hoac None khi khong du tuong phan de
    tin (nhac nen to, tieng on deu). None nghia la "giu nguyen o cu", khong phai
    "khong co tieng": tha khong dich con hon dich sai cho.
    """
    i0 = max(0, int(c0 * sr)); i1 = min(len(x), int(c1 * sr))
    if i1 - i0 < int(0.2 * sr):
        return None
    n = max(1, int(sr * KHUNG_FRAME_MS / 1000))
    m = (i1 - i0) // n
    if m < 5:
        return None
    r = x[i0:i0 + m * n].reshape(m, n)
    db = 20.0 * np.log10(np.sqrt((r * r).mean(axis=1)) + 1e-9)
    nen = float(np.percentile(db, 20)); dinh = float(np.percentile(db, 95))
    if dinh - nen < KHUNG_TUONG_PHAN_DB:
        return None
    to = db > (nen + 0.5 * (dinh - nen))

    # Chi tinh la tieng noi khi keu lien tuc >= KHUNG_MIN_RUN_MS, de tieng go
    # hay tieng dong 1 khung khong keo cua so rong ra vo ich.
    can = max(1, int(KHUNG_MIN_RUN_MS / KHUNG_FRAME_MS))
    dau = cuoi = None; chay = None
    for k in range(m + 1):
        if k < m and to[k]:
            if chay is None:
                chay = k
            continue
        if chay is not None and k - chay >= can:
            if dau is None:
                dau = chay
            cuoi = k
        chay = None
    if dau is None:
        return None

    s0 = c0 + dau * n / sr
    s1 = min(c1, c0 + cuoi * n / sr)
    if s1 - s0 < KHUNG_MIN_SPAN:
        return None
    if s0 - c0 < KHUNG_MIN_DICH:
        s0 = c0
    return (s0, s1)


def khung_tieng_noi(goc_path, segs):
    """-> list cung do dai segs, moi phan tu la (s0,s1) hoac None.

    Loi doc/giai ma khong duoc giet job: tra toan None de dat_cau chay y het
    truoc day.
    """
    try:
        x, sr = doc_mono(goc_path)
    except Exception as e:
        print(f"[el_clone] CANH BAO: khong doc duoc audio goc ({e}) -> "
              f"dat cau theo dau o nhu cu", flush=True)
        return [None] * len(segs)
    return [khung_mot_cue(x, sr, c0, c1) for c0, c1, _t in segs]


def dat_cau(rendered, sr, nen=_atempo, khung=None):
    """Dat tung cau vao dung moc thoi gian cua no tren truc video.

    Khong ghep sat nhau. Cau nao doc dai hon o cua no thi nen lai cho vua, tran
    TRAN_NEN_O. Chi khi cau sau sap toi ma van chua doc xong moi duoc nen toi
    MAX_TEMPO. `nen` tach ra lam tham so de test khoi phai goi ffmpeg.

    `khung[i]` = (s0,s1) doan THAT SU co tieng trong o thu i cua ban goc, do bang
    khung_tieng_noi(). None hoac khong truyen -> dung ca o, tuc y het hanh vi cu.

    -> (placed, blocks, n_fast, n_push, n_kich_tran, n_dich, tong_dich)
    """
    blocks=[]; placed=[]; prev_end=-MIN_GAP; n_fast=0; n_push=0; n_kich_tran=0
    n_dich=0; tong_dich=0.0
    for i,(c0,c1,text,aud) in enumerate(rendered):
        d0=len(aud)/sr
        # Chi can chinh khi DO DUOC doan co tieng. Do that bai nghia la nhac nen
        # to hoac on deu: luc do khong biet gi hon dau o, va doan giua o la danh
        # bac. Giu nguyen cach cu.
        k = khung[i] if khung else None
        if k:
            s0, s1 = k
            # Cau ngan hon doan co tieng -> dat vao GIUA doan do, sai so chia deu
            # hai dau thay vi don het ve cuoi. Cau dai hon -> bat dau ngay dau.
            span = max(MIN_SEG, s1-s0)
            moc = s0 if d0 >= span else s0 + (span-d0)/2
        else:
            moc = c0
        pos=max(moc, prev_end+MIN_GAP)
        if pos > moc+0.001: n_push+=1
        if moc > c0+0.001: n_dich+=1; tong_dich += moc-c0

        # Muc tieu 1: doc xong TRONG O CUA CHINH CAU, de giong moi nam dung tren
        # giong goc. Cach cu chi nen khi cau sau sap toi, nen cau nao co khoang
        # lang phia sau la duoc tran thoai mai, va cai tran do day moi cau sau di
        # muon theo day chuyen. Do tren video that 64 cue: cach cu de 21 cau tran
        # o; them muc tieu nay va cat ngan ban dich thi con 5.
        # Do phong theo vi tri CU (dau o), khong theo vi tri da dich: dich cau
        # muon hon la vi tieng goc bat dau muon, khong phai ly do de nen gat hon.
        # Tran ra sau c1 dung bang phan da dich - do la khoang lang trong ban goc.
        o_rieng = max(MIN_SEG, c1 - max(c0, prev_end + MIN_GAP))
        ty_le = 1.0
        if d0 > o_rieng:
            ty_le = min(d0/o_rieng, TRAN_NEN_O)
            if d0/o_rieng > TRAN_NEN_O: n_kich_tran += 1

        # Muc tieu 2, khan cap: cau sau sap toi ma van chua doc xong. Chi luc nay
        # moi duoc nen toi MAX_TEMPO - giong hoi meo con hon hai cau chong nhau.
        # Gop chung mot he so roi nen MOT lan, khong nen hai lan chong nhau.
        nxt = rendered[i+1][0] if i+1 < len(rendered) else None
        if nxt is not None:
            avail = nxt - pos - MIN_GAP
            if avail > MIN_SEG and d0/ty_le > avail:
                ty_le = min(max(ty_le, d0/avail), MAX_TEMPO)

        if ty_le > 1.001:
            aud = nen(aud, sr, ty_le); n_fast += 1
        d = len(aud)/sr
        placed.append((pos, aud))
        blocks.append(f"{i+1}\n{_sec_to_ts(pos)} --> {_sec_to_ts(pos+d)}\n{text}\n")
        prev_end = pos + d
    return placed, blocks, n_fast, n_push, n_kich_tran, n_dich, tong_dich


def main(argv=None):
    """argv=None -> doc sys.argv (chay CLI). Truyen list -> goi duoc TRONG tien
    trinh, khong can python.exe ben ngoai (ban Windows dong goi khong co)."""
    ap=argparse.ArgumentParser()
    for k in ("srt","out","api-key","voice-id"): ap.add_argument("--"+k, required=True)
    ap.add_argument("--out-srt", default="")
    ap.add_argument("--model", default="eleven_v3")
    ap.add_argument("--speed", type=float, default=1.0)
    # Hai co nay deu KHONG bat buoc: thieu thi chay y het ban cu.
    ap.add_argument("--goc", default="", help="video/audio GOC de do doan co tieng noi")
    ap.add_argument("--srt-goc", default="", help="srt ngon ngu nguon, de bo qua cue chi co tieng cuoi")
    a=ap.parse_args(argv)

    segs=parse_srt(Path(a.srt))
    if not segs: sys.exit("[el_clone] srt rong")

    srt_goc=getattr(a,"srt_goc")
    if srt_goc and Path(srt_goc).exists():
        # Khop theo moc bat dau (ms): pyvideotrans giu nguyen timing khi dich.
        goc={int(round(t0*1000)): t for t0,_t1,t in parse_srt(Path(srt_goc))}
        truoc=len(segs)
        segs=[x for x in segs if not chi_tieng_cuoi(goc.get(int(round(x[0]*1000)),""))]
        if len(segs) < truoc:
            print(f"[el_clone] bo qua {truoc-len(segs)} cue chi co tieng cuoi "
                  f"-> giu tieng cuoi goc", flush=True)
    if not segs: sys.exit("[el_clone] srt rong sau khi loc")
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

    khung = khung_tieng_noi(a.goc, [(c0,c1,t) for c0,c1,t,_a in rendered]) if a.goc else None
    placed, blocks, n_fast, n_push, n_kich_tran, n_dich, tong_dich = dat_cau(
        rendered, sr, khung=khung)
    if khung:
        do = sum(1 for k in khung if k)
        print(f"[el_clone] do duoc doan co tieng o {do}/{len(khung)} cue; "
              f"{n_dich} cau dich muon hon dau o, trung binh "
              f"{(tong_dich/n_dich if n_dich else 0):.2f}s", flush=True)
    prev_end = max([p + len(a)/sr for p, a in placed], default=0.0)

    # Do dai track = het cau cuoi cua SRT (giu nguyen truc thoi gian video).
    end = max([prev_end] + [c1 for _c0,c1,_t,_a in rendered])
    track = np.zeros(int(end*sr)+1, dtype=np.float32)
    for pos, aud in placed:
        i0 = int(pos*sr); n = min(len(aud), len(track)-i0)
        if n > 0: track[i0:i0+n] += aud[:n]
    if n_fast or n_push:
        print(f"[el_clone] {n_fast} cau phai nen nhanh, {n_push} cau bi day muon "
              f"vi cau truoc chua doc xong, {n_kich_tran} cau dai qua ca tran nen "
              f"{TRAN_NEN_O} (ban dich con dai so voi o)", flush=True)
    pk=float(np.max(np.abs(track))) if track.size else 0.0
    if pk>1.0: track=track/pk*0.98
    sf.write(a.out, track, sr)
    if a.out_srt: Path(a.out_srt).write_text("\n".join(blocks),encoding="utf-8")
    print(f"[el_clone] XONG -> {a.out} ({len(track)/sr:.1f}s)", flush=True)


if __name__=="__main__":
    main()
