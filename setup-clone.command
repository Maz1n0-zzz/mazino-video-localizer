#!/bin/bash
# ============================================================
#  Cai them tinh nang CLONE GIONG (F5-TTS tieng Viet) tren Mac.
#  Chay 1 lan, SAU khi da cai xong app (setup-mac.command).
#  Tai ve ~6GB (model + thu vien) - can mang on dinh, ~15-30 phut.
# ============================================================
set -u
cd "$(dirname "$0")" || exit 1

say()  { echo ""; echo "=== $* ==="; }
fail() { echo ""; echo "!!! LOI: $*"; echo "!!! Chup man hinh gui lai de kiem tra."; read -p "Nhan Enter de dong..."; exit 1; }

# Nap brew vao PATH
if [ -x /opt/homebrew/bin/brew ]; then eval "$(/opt/homebrew/bin/brew shellenv)"; fi
if [ -x /usr/local/bin/brew ];   then eval "$(/usr/local/bin/brew shellenv)"; fi
command -v uv >/dev/null 2>&1 || fail "Chua co uv - hay chay setup-mac.command truoc"

say "BUOC 1/3: Cai ffmpeg@6 (thu vien F5 doc audio can ban nay, cai song song khong dung cham ffmpeg chinh)"
brew install ffmpeg@6 || fail "Cai ffmpeg@6 that bai"

say "BUOC 2/3: Tao moi truong f5env + cai f5-tts (tai torch + thu vien, lau)"
uv venv --python 3.10 f5env || fail "Tao f5env that bai"
uv pip install --python f5env/bin/python f5-tts || fail "Cai f5-tts that bai"

say "BUOC 3/3: Tai model giong tieng Viet (~5.4GB - LAU nhat, cu de chay)"
mkdir -p models/f5-vi
f5env/bin/python -c "
from huggingface_hub import hf_hub_download
import shutil, os
m = hf_hub_download('hynt/F5-TTS-Vietnamese-ViVoice', 'model_last.pt')
shutil.copy(m, 'models/f5-vi/model_last.pt')
v = hf_hub_download('hynt/F5-TTS-Vietnamese-ViVoice', 'config.json')
shutil.copy(v, 'models/f5-vi/vocab.txt')
print('Model:', os.path.getsize('models/f5-vi/model_last.pt')//1024//1024, 'MB')
" || fail "Tai model that bai"

echo ""
echo "==================================================="
echo "  CAI CLONE GIONG XONG!"
echo "  Mo lai app (start.command). Trong app, o 'Kieu giong doc'"
echo "  chon 'Clone giong tu file mau (F5-TTS)', tai file giong"
echo "  mau len roi chay."
echo ""
echo "  Luu y: tren Mac F5 chay hoi cham (~6x thoi luong audio)."
echo "  Tren may co GPU NVIDIA (vd RTX 3060) se nhanh hon nhieu."
echo "==================================================="
echo ""
read -p "Nhan Enter de dong cua so nay..."
