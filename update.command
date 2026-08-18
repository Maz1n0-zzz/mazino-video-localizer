#!/bin/bash
# Bam-dup (double-click) file nay de CAP NHAT phien ban moi nhat.
cd "$(dirname "$0")" || exit 1

echo "==================================================="
echo "  Dang tai ban cap nhat moi nhat tu GitHub..."
echo "==================================================="
echo ""

git pull

echo ""
if [ $? -eq 0 ]; then
  echo "==================================================="
  echo "  DA CAP NHAT XONG!"
  echo "  Dong cua so nay, roi mo lai app bang cach"
  echo "  bam-dup file 'start.command'."
  echo "==================================================="
else
  echo "==================================================="
  echo "  Co loi khi cap nhat. Chup man hinh gui lai de kiem tra."
  echo "==================================================="
fi
echo ""
read -p "Nhan phim Enter de dong cua so nay..."
