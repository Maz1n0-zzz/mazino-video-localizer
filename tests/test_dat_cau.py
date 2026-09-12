#!/usr/bin/env python3
"""Test dat cau dub cua el_clone.py. Chay bang venv pyvideotrans (co numpy+soundfile):

    vendor/pyvideotrans/.venv/bin/python3 tests/test_dat_cau.py

Khong goi mang, khong goi ffmpeg: `nen` duoc thay bang ham gia, con khung tieng
noi dung tin hieu tu dung san.
"""
import sys
from pathlib import Path

import numpy as np

DU_AN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DU_AN))
import el_clone as el  # noqa: E402

SR = 1000  # thap cho nhanh; dat_cau chi lam viec voi len(aud)/sr


def nen_gia(aud, sr, ratio):
    """Thay _atempo: cat bot mau theo dung ty le, khong goi ffmpeg."""
    return np.zeros(max(1, int(round(len(aud) / ratio))), dtype=np.float32)


def cau(c0, c1, giay, text="x"):
    return (c0, c1, text, np.zeros(int(giay * SR), dtype=np.float32))


loi = []


def check(dieu_kien, mo_ta):
    print(("  OK   " if dieu_kien else "  HONG ") + mo_ta)
    if not dieu_kien:
        loi.append(mo_ta)


# --- 1. khong truyen khung -> y het hanh vi cu -------------------------------
r = [cau(0.0, 5.0, 1.8), cau(5.0, 10.0, 2.0)]
placed, blocks, n_fast, n_push, n_tran, n_dich, tong = el.dat_cau(r, SR, nen=nen_gia)
check([round(p, 3) for p, _ in placed] == [0.0, 5.0], "khong co khung: cau neo dau o")
check(n_dich == 0 and tong == 0.0, "khong co khung: khong cau nao bi dich")
check(n_fast == 0, "khong co khung: khong phai nen cau nao")

# --- 2. cau ngan hon doan co tieng -> vao GIUA doan do -----------------------
# O 0-5s nhung tieng goc chi o 3,0-4,6s. Cau tieng Viet dai 1,0s.
r = [cau(0.0, 5.0, 1.0)]
placed, *_rest = el.dat_cau(r, SR, nen=nen_gia, khung=[(3.0, 4.6)])
pos = placed[0][0]
check(abs(pos - 3.3) < 0.01, f"cau ngan: dat giua doan co tieng (pos={pos:.2f}, cho 3,30)")
check(3.0 <= pos and pos + 1.0 <= 4.6 + 1e-6, "cau ngan: nam tron trong doan co tieng")

# --- 3. cau dai hon doan co tieng -> bat dau ngay dau doan -------------------
r = [cau(0.0, 5.0, 3.0)]
placed, *_rest = el.dat_cau(r, SR, nen=nen_gia, khung=[(1.2, 2.0)])
check(abs(placed[0][0] - 1.2) < 0.01, "cau dai: bat dau ngay dau doan co tieng")

# --- 4. dich muon KHONG duoc lam cau bi nen gat hon --------------------------
# Cung mot cau 4,5s trong o 0-5s: mot lan khong khung, mot lan khung bat dau
# muon. Do dai sau khi dat phai y het nhau.
r1 = [cau(0.0, 5.0, 4.5), cau(9.0, 12.0, 1.0)]
r2 = [cau(0.0, 5.0, 4.5), cau(9.0, 12.0, 1.0)]
p1, *_ = el.dat_cau(r1, SR, nen=nen_gia)
p2, *_ = el.dat_cau(r2, SR, nen=nen_gia, khung=[(2.0, 4.0), None])
check(len(p1[0][1]) == len(p2[0][1]),
      f"dich muon khong nen gat hon ({len(p1[0][1])} vs {len(p2[0][1])} mau)")

# --- 5. khong bao gio nen qua MAX_TEMPO --------------------------------------
r = [cau(0.0, 1.0, 8.0), cau(1.2, 2.0, 6.0)]
placed, _b, n_fast, *_ = el.dat_cau(r, SR, nen=nen_gia, khung=None)
for i, (_pos, aud) in enumerate(placed):
    ty = len(r[i][3]) / max(1, len(aud))
    check(ty <= el.MAX_TEMPO + 0.02, f"cau {i}: ty le nen {ty:.2f} <= {el.MAX_TEMPO}")

# --- 6. thu tu thoi gian khong bao gio dao nguoc -----------------------------
r = [cau(0.0, 5.0, 1.0), cau(5.0, 10.0, 1.0), cau(10.0, 15.0, 1.0)]
placed, *_rest = el.dat_cau(r, SR, nen=nen_gia,
                            khung=[(4.0, 4.8), (5.0, 6.0), (10.0, 14.0)])
moc = [p for p, _ in placed]
check(moc == sorted(moc), f"moc bat dau tang dan: {[round(x,2) for x in moc]}")

# --- 7. loc cue chi co tieng cuoi -------------------------------------------
check(el.chi_tieng_cuoi("哈哈哈哈。") is True, "nhan ra cue chi co tieng cuoi")
check(el.chi_tieng_cuoi("嘿嘿") is True, "nhan ra 嘿嘿")
check(el.chi_tieng_cuoi("滚哎呀。") is False, "KHONG loc cue co loi thoai that")
check(el.chi_tieng_cuoi("谢谢一样哎。") is False, "KHONG loc 谢谢一样哎")
check(el.chi_tieng_cuoi("哈") is False, "mot chu 哈 le thi khong loc")
check(el.chi_tieng_cuoi("") is False, "cue rong thi khong loc")

# --- 8. do doan co tieng tren tin hieu tu dung -------------------------------
sr = 16000
x = np.random.default_rng(0).normal(0, 0.001, 10 * sr).astype(np.float32)  # nen im
t = np.arange(int(1.5 * sr)) / sr
x[int(6.0 * sr):int(7.5 * sr)] += (0.3 * np.sin(2 * np.pi * 200 * t)).astype(np.float32)
k = el.khung_mot_cue(x, sr, 5.0, 10.0)
check(k is not None, "do duoc doan co tieng trong o im lang")
if k:
    check(abs(k[0] - 6.0) < 0.15, f"diem bat dau ~6,0s (do duoc {k[0]:.2f})")
    check(abs(k[1] - 7.5) < 0.15, f"diem ket thuc ~7,5s (do duoc {k[1]:.2f})")

# nen deu, khong tuong phan -> phai tra None chu khong doan bua
x2 = np.random.default_rng(1).normal(0, 0.1, 10 * sr).astype(np.float32)
check(el.khung_mot_cue(x2, sr, 5.0, 10.0) is None, "nen deu -> tra None, khong doan bua")

print()
if loi:
    print(f"HONG {len(loi)} muc:")
    for m in loi:
        print("   -", m)
    sys.exit(1)
print("TAT CA QUA")
