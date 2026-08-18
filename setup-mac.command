#!/bin/bash
# ============================================================
#  Mazino Video Localizer - TU DONG CAI DAT tren Mac
#  Chay 1 lan tren may Mac moi. Tu cai: Homebrew, ffmpeg, git,
#  uv, tai code, dung 3 moi truong Python. Mat ~20-40 phut.
# ============================================================
set -u

REPO_URL="https://github.com/Maz1n0-zzz/mazino-video-localizer.git"
INSTALL_DIR="$HOME/mazino-video-localizer"

say()  { echo ""; echo "=== $* ==="; }
fail() { echo ""; echo "!!! LOI: $* "; echo "!!! Chup man hinh cho nay gui lai de kiem tra."; read -p "Nhan Enter de dong..."; exit 1; }

say "BUOC 1/6: Kiem tra / cai Homebrew (trinh quan ly cai dat)"
if ! command -v brew >/dev/null 2>&1; then
  echo "Chua co Homebrew - dang cai (co the hoi mat khau may cua ban, cu go vao)..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || fail "Cai Homebrew that bai"
fi
# Nap brew vao PATH cho ca may Apple Silicon (/opt/homebrew) lan Intel (/usr/local)
if [ -x /opt/homebrew/bin/brew ]; then eval "$(/opt/homebrew/bin/brew shellenv)"; fi
if [ -x /usr/local/bin/brew ];   then eval "$(/usr/local/bin/brew shellenv)"; fi
command -v brew >/dev/null 2>&1 || fail "Khong tim thay brew sau khi cai"

say "BUOC 2/6: Cai git va uv"
brew install git uv || fail "Cai git/uv that bai"

say "BUOC 3/6: Cai ffmpeg (ban day du co libass) - buoc nay LAU nhat, co the 20-30 phut, cu de chay"
brew tap homebrew-ffmpeg/ffmpeg
brew install homebrew-ffmpeg/ffmpeg/ffmpeg || fail "Cai ffmpeg that bai"

say "BUOC 4/6: Tai code ve $INSTALL_DIR"
if [ -d "$INSTALL_DIR/.git" ]; then
  echo "Da co san - dang cap nhat ban moi nhat..."
  git -C "$INSTALL_DIR" pull || fail "Cap nhat code that bai"
else
  git clone "$REPO_URL" "$INSTALL_DIR" || fail "Tai code that bai"
fi
cd "$INSTALL_DIR" || fail "Khong vao duoc thu muc code"

say "BUOC 5/6: Dung moi truong Python (tai thu vien - mat vai phut)"
echo "-> pyvideotrans (transcribe/dich/dub)"
( cd vendor/pyvideotrans && uv sync ) || fail "Setup pyvideotrans that bai"
echo "-> Sua thu vien soundfile (loi hay gap tren Mac)"
uv pip install --python vendor/pyvideotrans/.venv/bin/python --force-reinstall --no-cache soundfile==0.13.1 || echo "(Bo qua neu loi - se sua sau)"
echo "-> video-subtitle-remover (xoa sub/logo)"
( cd vendor/video-subtitle-remover \
  && uv venv --python 3.12 videoEnv \
  && uv pip install --python videoEnv/bin/python paddlepaddle==3.0.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/ \
  && uv pip install --python videoEnv/bin/python torch==2.7.0 torchvision==0.22.0 \
  && uv pip install --python videoEnv/bin/python -r requirements.txt ) || fail "Setup video-subtitle-remover that bai"
echo "-> web (giao dien app)"
( uv venv --python 3.12 web_env \
  && uv pip install --python web_env/bin/python fastapi "uvicorn[standard]" python-multipart edge-tts ) || fail "Setup web that bai"

say "BUOC 6/6: HOAN TAT!"
echo ""
echo "==================================================="
echo "  CAI DAT XONG! App nam trong thu muc:"
echo "  $INSTALL_DIR"
echo ""
echo "  De MO app: vao thu muc do, bam-dup file 'start.command'."
echo "  De CAP NHAT sau nay: bam-dup file 'update.command'."
echo "==================================================="
echo ""
# Mo thu muc trong Finder cho de thay
open "$INSTALL_DIR" 2>/dev/null
read -p "Nhan Enter de dong cua so nay..."
