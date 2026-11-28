#!/usr/bin/env bash
# Foydali (foydali.xisobchim.uz): Zona + QR Drive ni bio-lab.uz bilan bir serverga o'rnatish/yangilash.
#
#   cd /root/zona_project && git pull
#   bash zona_project/deploy/foydali/foydali-setup.sh
#
# Qayta ishga tushirish xavfsiz: mavjud bazalar, kalitlar va sozlamalar saqlanadi.
# Boshqa saytlarga tegmaydi: nginx'da faqat «foydali» sayti qo'shiladi (default o'chirilmaydi), pm2'da faqat
# «foydali-frontend» boshqariladi, faqat bo'sh portlar ishlatiladi:
#   8020 backend (gunicorn/uvicorn) · 8120 QR Drive API · 3020 frontend (pm2) · 8920 boshqaruv markazi
set -euo pipefail

DOMAIN="${DOMAIN:-foydali.xisobchim.uz}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"   # loyiha papkasi (backend/, frontend/, services/)
HERE="$SRC/deploy/foydali"
DATA=/var/lib/foydali
ETC=/etc/foydali
USR=foydali
PORTS="8020 8120 3020 8920"

step() { echo; echo "==> $*"; }
gen() { python3 -c "import secrets; print(secrets.token_urlsafe(50))"; }
as_user() { sudo -u "$USR" -H "$@"; }

[[ $EUID -eq 0 ]] || { echo "root sifatida ishga tushiring"; exit 1; }
[[ -d "$SRC/backend" && -d "$SRC/frontend" && -d "$SRC/services/qrdrive" ]] || { echo "Loyiha topilmadi: $SRC"; exit 1; }

# Node/pm2 (nvm orqali o'rnatilgan bo'lishi mumkin — non-interaktiv SSH'da PATH'da bo'lmaydi)
PM2_BIN="$(command -v pm2 || ls -d /root/.nvm/versions/node/*/bin/pm2 2>/dev/null | sort -V | tail -1 || true)"
[[ -n "$PM2_BIN" ]] || { echo "pm2 topilmadi"; exit 1; }
NODE_BIN="$(dirname "$PM2_BIN")"
export PATH="$NODE_BIN:$PATH"
node -v >/dev/null

step "Portlar (faqat bo'sh yoki o'zimizniki bo'lishi kerak)"
for p in $PORTS; do
  owner=$(ss -ltnpH "sport = :$p" 2>/dev/null | head -1)
  if [[ -n "$owner" ]]; then
    case "$p" in
      3020) pm2 jlist 2>/dev/null | grep -q '"name":"foydali-frontend"' || { echo "  $p band (boshqa dastur): $owner"; exit 1; } ;;
      *) systemctl is-active --quiet "foydali-$( [[ $p == 8020 ]] && echo backend || ([[ $p == 8120 ]] && echo qrdrive-api) || echo control)" \
           || { echo "  $p band (boshqa dastur): $owner"; exit 1; } ;;
    esac
    echo "  $p — foydali servisi (yangilanadi)"
  else
    echo "  $p — bo'sh"
  fi
done

step "Tizim paketlari (faqat yetishmaganlari; boshqa paketlar yangilanmaydi)"
need=()
for pkg in python3-venv python3-dev build-essential libarchive-tools sqlite3; do
  dpkg -s "$pkg" >/dev/null 2>&1 || need+=("$pkg")
done
if ((${#need[@]})); then apt-get update -qq; DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${need[@]}"; fi
# RAR/7z arxivlari uchun (bo'lmasa bsdtar yetarli)
dpkg -s 7zip >/dev/null 2>&1 || DEBIAN_FRONTEND=noninteractive apt-get install -y -qq 7zip >/dev/null 2>&1 || true
# Support bot: rasmdagi matnni o'qish (OCR, ixtiyoriy — bo'lmasa bot rasmsiz ishlaydi)
dpkg -s ffmpeg >/dev/null 2>&1 || DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ffmpeg >/dev/null 2>&1 || true  # javob videolarini siqish
dpkg -s tesseract-ocr-uzb >/dev/null 2>&1 || DEBIAN_FRONTEND=noninteractive apt-get install -y -qq tesseract-ocr tesseract-ocr-rus tesseract-ocr-uzb tesseract-ocr-uzb-cyrl >/dev/null 2>&1 || true
# Redis: backend bir nechta worker bilan ishlashi uchun (WebSocket + umumiy kesh). O'zimizning foydali-redis servisi
# ishlatiladi (faqat unix socket); paket bilan kelgan tizim nusxasi (TCP 6379) faqat biz o'rnatgan bo'lsak o'chiriladi.
if ! dpkg -s redis-server >/dev/null 2>&1; then
  if DEBIAN_FRONTEND=noninteractive apt-get install -y -qq redis-server >/dev/null 2>&1; then
    systemctl disable --now redis-server >/dev/null 2>&1 || true
  else
    echo "  ! redis-server o'rnatilmadi — backend 1 worker bilan ishlaydi"
  fi
fi

step "Foydalanuvchi va papkalar"
id "$USR" >/dev/null 2>&1 || useradd --system --home "$DATA" --shell /usr/sbin/nologin "$USR"
install -d -m 750 -o "$USR" -g "$USR" "$DATA" "$DATA/qrdrive" "$DATA/control" "$DATA/backups"
install -d -m 750 -o root -g "$USR" "$ETC"
# servislar kodni /root ichidan o'qiydi (faqat o'qish); /root ga kirish huquqi (x) yetarli
chmod o+x /root

step "Muhit fayllari ($ETC)"
if [[ ! -f "$ETC/foydali.env" ]]; then
  JWT=$(gen)
  cat > "$ETC/foydali.env" <<EOF
# Foydali — Zona backend muhiti. Kalitlarni zaxiralab qo'ying (o'zgarsa: foydalanuvchilar qayta kiradi / AI kalitlari qayta kiritiladi)
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=$(gen)
ZONA_ENCRYPTION_KEY=$(gen)
ZONA_JWT_SECRET=$JWT
DJANGO_ALLOWED_HOSTS=$DOMAIN,127.0.0.1,localhost
DJANGO_CSRF_TRUSTED_ORIGINS=https://$DOMAIN,http://$DOMAIN
ZONA_FRONTEND_URL=https://$DOMAIN
ZONA_CORS_ORIGINS=https://$DOMAIN
# HTTPS (certbot) muvaffaqiyatli bo'lgach skript 1 qiladi
DJANGO_SECURE_COOKIES=0
ZONA_DB_PATH=$DATA/db.sqlite3
ZONA_BOT_API_KEY=
ZONA_GEMINI_API_KEY=
DJANGO_LOG_LEVEL=INFO
EOF
  echo "  foydali.env yaratildi"
fi
# Bir nechta backend worker'i (Redis bo'lsa). O'chirish: ZONA_WEB_WORKERS=1 (yoki ZONA_REDIS_URL= bo'sh) — qayta yozilmaydi
if [[ -x /usr/bin/redis-server ]]; then
  grep -q '^ZONA_REDIS_URL=' "$ETC/foydali.env" || echo 'ZONA_REDIS_URL=unix:///run/foydali-redis/redis.sock' >> "$ETC/foydali.env"
  grep -q '^ZONA_WEB_WORKERS=' "$ETC/foydali.env" || echo 'ZONA_WEB_WORKERS=3' >> "$ETC/foydali.env"
fi
JWT=$(grep '^ZONA_JWT_SECRET=' "$ETC/foydali.env" | cut -d= -f2-)
if [[ ! -f "$ETC/foydali-qrdrive.env" ]]; then
  cat > "$ETC/foydali-qrdrive.env" <<EOF
# Foydali — QR Drive muhiti. Qolgan sozlamalar (bot tokeni, NAS, ...) — panelda: QR Drive -> Sozlamalar
QRDRIVE_DEBUG=0
# Bazadagi maxfiylarni (bot tokeni, NAS paroli) shifrlash kaliti — O'ZGARTIRMANG, zaxiralab qo'ying
QRDRIVE_MASTER_KEY=$(gen)
QRDRIVE_SSO_SECRET=$JWT
QRDRIVE_DATA_DIR=$DATA/qrdrive
QRDRIVE_PUBLIC_BASE_URL=https://$DOMAIN
QRDRIVE_HOST=127.0.0.1
QRDRIVE_PORT=8120
TZ=Asia/Tashkent
QRDRIVE_LOG_LEVEL=INFO
EOF
  echo "  foydali-qrdrive.env yaratildi"
else
  sed -i "s|^QRDRIVE_SSO_SECRET=.*|QRDRIVE_SSO_SECRET=$JWT|" "$ETC/foydali-qrdrive.env"
fi
if [[ ! -f "$ETC/foydali-control.env" ]]; then
  cat > "$ETC/foydali-control.env" <<EOF
# Foydali — kuzatuv markazi (https://$DOMAIN/control/). Kirish FAQAT bir martalik kod bilan (doimiy parol yo'q):
# kod egasining Telegram'iga keladi (CONTROL_TG_TOKEN, CONTROL_TG_CHAT_ID) yoki serverda: foydali-control-code
CONTROL_AUTH=otp
CONTROL_HOST=127.0.0.1
CONTROL_PORT=8920
CONTROL_CONFIG=$ETC/foydali-control.services.json
CONTROL_DATA_DIR=$DATA/control
EOF
  echo "  Kuzatuv markazi: kirish kodi — Telegram orqali yoki serverda: foydali-control-code"
fi
# doimiy parol ishlatilmaydi va saqlanmaydi (eski o'rnatishlardan qolgan bo'lsa — olib tashlanadi)
sed -i '/^CONTROL_PASSWORD=/d' "$ETC/foydali-control.env"
grep -q '^CONTROL_AUTH=' "$ETC/foydali-control.env" || echo 'CONTROL_AUTH=otp' >> "$ETC/foydali-control.env"
rm -f "$DATA/control/initial-password.txt"
cat > /usr/local/sbin/foydali-control-code <<EOF
#!/bin/bash
# Favqulodda: kuzatuv markaziga bir martalik kirish kodi (Telegram ishlamasa). Faqat root.
exec sudo -u $USR env CONTROL_AUTH=otp python3 $SRC/services/control/control.py --data $DATA/control --issue-code
EOF
chmod 700 /usr/local/sbin/foydali-control-code
chown root:"$USR" "$ETC"/*.env
chmod 640 "$ETC"/*.env
sed "s|bind = .*|bind = \"127.0.0.1:8020\"|" "$SRC/deploy/gunicorn.conf.py" > "$ETC/foydali-gunicorn.conf.py"
cp "$HERE/foydali-control.services.json" "$ETC/foydali-control.services.json"
sed "s|__SRC__|$SRC|g" "$HERE/foydali.ecosystem.config.cjs" > "$ETC/foydali.ecosystem.config.cjs"

step "Zona baza"
if [[ ! -f "$DATA/db.sqlite3" && -f "$SRC/deploy/data/zona.sqlite3" ]]; then
  cp "$SRC/deploy/data/zona.sqlite3" "$DATA/db.sqlite3"
  echo "  deploy/data/zona.sqlite3 dan ko'chirildi (birinchi o'rnatish)"
fi
[[ -f "$DATA/db.sqlite3" ]] && chown "$USR:$USR" "$DATA/db.sqlite3"

step "Backend: Python muhiti"
[[ -x "$SRC/.venv/bin/python" ]] || python3 -m venv "$SRC/.venv"
"$SRC/.venv/bin/pip" install -q --upgrade pip wheel
"$SRC/.venv/bin/pip" install -q -e "$SRC[ai,server,support,semantic]"

step "Backend: migratsiya va statik fayllar"
manage() { bash -c "set -a; source $ETC/foydali.env; set +a; cd $SRC/backend && $*"; }
as_user bash -c "set -a; source $ETC/foydali.env; set +a; cd $SRC/backend && $SRC/.venv/bin/python manage.py migrate --noinput"
manage "$SRC/.venv/bin/python manage.py collectstatic --noinput -v0"

step "QR Drive: Python muhiti"
[[ -x "$SRC/services/qrdrive/.venv/bin/python" ]] || python3 -m venv "$SRC/services/qrdrive/.venv"
"$SRC/services/qrdrive/.venv/bin/pip" install -q --upgrade pip wheel
"$SRC/services/qrdrive/.venv/bin/pip" install -q -e "$SRC/services/qrdrive"

step "Frontend: npm ci + build (BACKEND_URL/QRDRIVE_URL build paytida yoziladi)"
cd "$SRC/frontend"
npm ci --no-audit --no-fund --loglevel=error
# Next.js ba'zan yangilanish tavsiyasini ko'rsatish uchun buildni bir marta to'xtatadi (SecurityFatalError) —
# shunda bir marta qayta urinamiz; ikkinchisi ham xato bo'lsa skript to'xtaydi.
nbuild() { NEXT_TELEMETRY_DISABLED=1 BACKEND_URL=http://127.0.0.1:8020 QRDRIVE_URL=http://127.0.0.1:8120 npm run build; }
nbuild || { echo "  build qayta urinilmoqda"; nbuild; }
cd "$SRC"

step "systemd servislari"
for f in "$HERE"/systemd/*; do sed "s|__SRC__|$SRC|g" "$f" > "/etc/systemd/system/$(basename "$f")"; done
systemctl daemon-reload
if [[ -x /usr/bin/redis-server ]]; then systemctl enable foydali-redis >/dev/null 2>&1; systemctl restart foydali-redis; fi
for u in foydali-backend foydali-qrdrive-api foydali-qrdrive-worker foydali-qrdrive-bot foydali-support-bot foydali-prbc; do
  systemctl enable "$u" >/dev/null 2>&1; systemctl restart "$u"
done
systemctl enable --now foydali-backup.timer >/dev/null 2>&1
systemctl enable --now foydali-close-review.timer >/dev/null 2>&1

step "Frontend: pm2 (foydali-frontend, 3020) — boshqa pm2 jarayonlariga tegilmaydi"
if pm2 describe foydali-frontend >/dev/null 2>&1; then
  pm2 restart foydali-frontend --update-env >/dev/null
else
  pm2 start "$ETC/foydali.ecosystem.config.cjs" --only foydali-frontend >/dev/null
fi
pm2 save >/dev/null
echo "  pm2: foydali-frontend ishga tushirildi"

step "Boshqaruv markazi (faqat foydali servislarini boshqara oladi)"
sed "s|__NODE_BIN__|$NODE_BIN|g" "$HERE/foydali-pm2.sh" > /usr/local/sbin/foydali-pm2
chmod 755 /usr/local/sbin/foydali-pm2
{
  echo "# Foydali boshqaruv markazi: faqat foydali-* servislarini boshqarish va jurnalini o'qish"
  for u in foydali-backend foydali-redis foydali-qrdrive-api foydali-qrdrive-worker foydali-qrdrive-bot foydali-support-bot foydali-prbc; do
    for a in start stop restart; do echo "$USR ALL=(root) NOPASSWD: /usr/bin/systemctl $a $u"; done
    for n in 300 800 3000; do echo "$USR ALL=(root) NOPASSWD:NOEXEC: /usr/bin/journalctl -u $u -n $n --no-pager -o short-iso"; done
  done
  echo "$USR ALL=(root) NOPASSWD: /usr/local/sbin/foydali-pm2 *"
  # kuzatuv va xavfsizlik markazi — FAQAT O'QISH (NOEXEC: journalctl sahifalovchisidan shell'ga chiqib bo'lmaydi)
  for u in biolab biolab-ci nginx ssh; do
    for n in 300 800 3000; do echo "$USR ALL=(root) NOPASSWD:NOEXEC: /usr/bin/journalctl -u $u -n $n --no-pager -o short-iso"; done
  done
  echo "$USR ALL=(root) NOPASSWD:NOEXEC: /usr/bin/journalctl -u ssh --since -24h --no-pager -q -o short-iso"
  echo "$USR ALL=(root) NOPASSWD:NOEXEC: /usr/bin/journalctl -u ssh --since -7d --no-pager -q -o short-iso --grep Accepted"
  # ufw ichida iptables'ni chaqiradi (NOEXEC bloklaydi); faqat holatni o'qiydi, sahifalovchi ochmaydi
  echo "$USR ALL=(root) NOPASSWD: /usr/sbin/ufw status verbose"
  echo "$USR ALL=(root) NOPASSWD:NOEXEC: /usr/sbin/sshd -T"
} > /etc/sudoers.d/foydali-control.tmp
visudo -cf /etc/sudoers.d/foydali-control.tmp >/dev/null
mv /etc/sudoers.d/foydali-control.tmp /etc/sudoers.d/foydali-control
chmod 440 /etc/sudoers.d/foydali-control
systemctl enable foydali-control >/dev/null 2>&1; systemctl restart foydali-control

step "nginx (faqat foydali sayti; boshqa saytlar o'zgarmaydi)"
SITE=/etc/nginx/sites-available/foydali
if [[ -f "$SITE" ]] && grep -q "managed by Certbot" "$SITE"; then
  echo "  sertifikatli sayt mavjud — o'zgartirilmadi (yangilash: README)"
else
  sed "s|__DOMAIN__|$DOMAIN|g" "$HERE/foydali.nginx.conf" > "$SITE"
fi
ln -sf "$SITE" /etc/nginx/sites-enabled/foydali
nginx -t
systemctl reload nginx

step "HTTPS (Let's Encrypt)"
if [[ ! -d "/etc/letsencrypt/live/$DOMAIN" ]]; then
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --redirect --register-unsafely-without-email \
    && echo "  sertifikat olindi" || echo "  ❗ certbot muvaffaqiyatsiz — sayt hozircha http orqali ishlaydi"
fi
if [[ -d "/etc/letsencrypt/live/$DOMAIN" ]] && grep -q '^DJANGO_SECURE_COOKIES=0' "$ETC/foydali.env"; then
  sed -i 's|^DJANGO_SECURE_COOKIES=0|DJANGO_SECURE_COOKIES=1|' "$ETC/foydali.env"
  systemctl restart foydali-backend
fi

step "Tekshiruv"
sleep 4
chk() { code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$2" || true); printf '  %-24s %s  %s\n' "$1" "$code" "$2"; }
chk backend      http://127.0.0.1:8020/api/auth/login/
chk qrdrive-api  http://127.0.0.1:8120/qrdrive/health
chk frontend     http://127.0.0.1:3020/login
chk control      http://127.0.0.1:8920/
chk "sayt (https)" "https://$DOMAIN/login"
for u in foydali-backend foydali-redis foydali-qrdrive-api foydali-qrdrive-worker foydali-qrdrive-bot foydali-support-bot foydali-prbc foydali-control; do
  printf '  %-24s %s\n' "$u" "$(systemctl is-active "$u")"
done
echo
echo "Tayyor: https://$DOMAIN   ·   boshqaruv markazi: https://$DOMAIN/control/"
