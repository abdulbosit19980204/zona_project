#!/usr/bin/env bash
# Zona: Ubuntu 22.04 / 24.04 serverga birinchi o'rnatish (gunicorn + nginx + systemd).
#
#   sudo git clone <repo> /opt/zona-src
#   sudo bash /opt/zona-src/zona_project/deploy/install.sh zona.example.uz   # domen yoki server IP
#
# Loyiha papkasi (backend/, frontend/, deploy/) /opt/zona ga symlink qilinadi — servislar shu yo'lni ishlatadi.
#
# Qayta ishga tushirish xavfsiz: mavjud baza, .env va kalitlar saqlanadi.
set -euo pipefail

DOMAIN="${1:-}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"   # loyiha papkasi
APP=/opt/zona
DATA=/var/lib/zona
ENVDIR=/etc/zona
ENVFILE=$ENVDIR/zona.env

if [[ $EUID -ne 0 ]]; then echo "sudo bilan ishga tushiring: sudo bash deploy/install.sh <domen>"; exit 1; fi
if [[ -z "$DOMAIN" ]]; then echo "Domen yoki IP kerak: sudo bash deploy/install.sh zona.example.uz"; exit 1; fi
if [[ ! -d "$SRC/backend" || ! -d "$SRC/frontend" ]]; then echo "Loyiha papkasi topilmadi: $SRC"; exit 1; fi

step() { echo; echo "==> $*"; }

step "Tizim paketlari"
apt-get update -y
apt-get install -y python3 python3-venv python3-dev build-essential git nginx curl ca-certificates gzip

# Next.js 16 uchun Node.js 20.9+ kerak
NODE_MAJOR=$(node -v 2>/dev/null | sed -E 's/^v([0-9]+).*/\1/' || echo 0)
if [[ "${NODE_MAJOR:-0}" -lt 20 ]]; then
  step "Node.js 22 (NodeSource)"
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y nodejs
fi

step "Foydalanuvchi va papkalar"
id zona >/dev/null 2>&1 || useradd --system --home "$DATA" --shell /usr/sbin/nologin zona
mkdir -p "$DATA/backups" "$ENVDIR"
if [[ "$SRC" != "$APP" ]]; then
  if [[ -e "$APP" && ! -L "$APP" ]]; then echo "$APP mavjud va symlink emas — olib tashlang yoki repo'ni shu yerga klonlang"; exit 1; fi
  ln -sfn "$SRC" "$APP"
fi
REPO="$(git -C "$SRC" rev-parse --show-toplevel)"
chown -R zona:zona "$REPO" "$DATA"
cd "$APP"

step "Muhit sozlamalari ($ENVFILE)"
if [[ ! -f "$ENVFILE" ]]; then
  gen() { python3 -c "import secrets; print(secrets.token_urlsafe(50))"; }
  sed -e "s|__DOMAIN__|$DOMAIN|g" \
      -e "s|DJANGO_SECRET_KEY=__GENERATE__|DJANGO_SECRET_KEY=$(gen)|" \
      -e "s|ZONA_ENCRYPTION_KEY=__GENERATE__|ZONA_ENCRYPTION_KEY=$(gen)|" \
      deploy/env.example > "$ENVFILE"
  # HTTPS hali yo'q — avval http orqali ishlashi uchun; certbot'dan keyin 1 qiling
  sed -i "s|^DJANGO_SECURE_COOKIES=1|DJANGO_SECURE_COOKIES=0|" "$ENVFILE"
  echo "  yaratildi. Kalitlarni zaxiralab qo'ying: $ENVFILE"
else
  echo "  mavjud — o'zgartirilmadi"
fi
chown root:zona "$ENVFILE"
chmod 640 "$ENVFILE"

step "Baza"
if [[ ! -f "$DATA/db.sqlite3" ]]; then
  if [[ -f deploy/data/zona.sqlite3 ]]; then
    cp deploy/data/zona.sqlite3 "$DATA/db.sqlite3"
    echo "  deploy/data/zona.sqlite3 dan ko'chirildi (birinchi o'rnatish)"
  else
    echo "  snapshot yo'q — bo'sh baza yaratiladi"
  fi
  chown zona:zona "$DATA"/db.sqlite3 2>/dev/null || true
else
  echo "  ishchi baza mavjud — tegilmadi ($DATA/db.sqlite3)"
fi

step "Python muhiti va paketlar"
sudo -u zona -H python3 -m venv "$APP/.venv"
sudo -u zona -H "$APP/.venv/bin/pip" install --upgrade pip wheel
sudo -u zona -H "$APP/.venv/bin/pip" install -e "$APP[ai,server]"

step "Migratsiya va statik fayllar"
run_manage() { sudo -u zona -H bash -c "set -a; source $ENVFILE; set +a; cd $APP/backend && $APP/.venv/bin/python manage.py $*"; }
run_manage migrate --noinput
run_manage collectstatic --noinput

step "Frontend (npm ci + build)"
sudo -u zona -H bash -c "cd $APP/frontend && npm ci && BACKEND_URL=http://127.0.0.1:8000 npm run build"

step "systemd servislari"
cp deploy/systemd/zona-*.service deploy/systemd/zona-backup.timer /etc/systemd/system/
chmod +x deploy/backup.sh deploy/update.sh
systemctl daemon-reload
systemctl enable --now zona-backend zona-frontend zona-backup.timer
systemctl restart zona-backend zona-frontend

step "nginx"
sed "s|__DOMAIN__|$DOMAIN|g" deploy/nginx/zona.conf > /etc/nginx/sites-available/zona
ln -sf /etc/nginx/sites-available/zona /etc/nginx/sites-enabled/zona
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

step "Tekshiruv"
sleep 3
curl -fsS -o /dev/null -w "  backend: HTTP %{http_code}\n" http://127.0.0.1:8000/api/ || echo "  backend javob bermadi: journalctl -u zona-backend -n 50"
curl -fsS -o /dev/null -w "  frontend: HTTP %{http_code}\n" http://127.0.0.1:3000/login || echo "  frontend javob bermadi: journalctl -u zona-frontend -n 50"

cat <<EOF

Tayyor: http://$DOMAIN
  Kirish: bazadagi mavjud foydalanuvchilar (admin, uzdev) — parollari o'zgarmagan.
  HTTPS (domen bo'lsa):  sudo apt install -y certbot python3-certbot-nginx && sudo certbot --nginx -d $DOMAIN
                         keyin $ENVFILE da DJANGO_SECURE_COOKIES=1 qiling va: sudo systemctl restart zona-backend
  Yangilash:             sudo bash $APP/deploy/update.sh
  Jurnal:                journalctl -u zona-backend -f
EOF
