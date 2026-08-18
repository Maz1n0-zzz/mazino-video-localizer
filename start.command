#!/bin/bash
# Bam-dup (double-click) file nay de MO app.
# Tu dong vao dung thu muc du ban dat folder o dau.
cd "$(dirname "$0")" || exit 1

echo "==================================================="
echo "  MAZINO VIDEO LOCALIZER - dang khoi dong..."
echo ""
echo "  Doi vai giay, trinh duyet se tu mo trang:"
echo "  http://127.0.0.1:7860"
echo "  (Neu khong tu mo, hay tu go dia chi tren vao trinh duyet)"
echo ""
echo "  >> De TAT app: bam Ctrl + C trong cua so nay, roi dong lai."
echo "==================================================="
echo ""

# Tu mo trinh duyet sau 3 giay (cho server kip khoi dong)
(sleep 3 && open "http://127.0.0.1:7860") &

web_env/bin/python web_server.py
