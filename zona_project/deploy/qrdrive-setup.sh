#!/usr/bin/env bash
# QR Drive mikroservisini o'rnatish/yangilash (install.sh va update.sh chaqiradi; qayta ishga tushirish xavfsiz).
# Uch mustaqil systemd servis: qrdrive-api (127.0.0.1:8100), qrdrive-worker, qrdrive-bot.
# Bittasi to'xtasa, qolganlari va Zona ishlashda davom etadi.
set -euo pipefail

APP=/opt/zona
SVC=$APP/services/qrdrive
DATA=/var/lib/zona/qrdrive
ZONA_ENV=/etc/zona/zona.env
QR_ENV=/etc/zona/qrdrive.env
DOMAIN="${DOMAIN:-}"

if [[ $EUID -ne 0 ]]; then echo "sudo bilan ishga tushiring"; exit 1; fi
gen() { python3 -c "import secrets; print(secrets.token_urlsafe(50))"; }

# 1) Umumiy JWT kaliti: Zona tokenlarni shu bilan imzolaydi, QR Drive shu bilan tekshiradi (SSO, tarmoqsiz)
if ! grep -q '^ZONA_JWT_SECRET=..*' "$ZONA_ENV"; then
  echo "ZONA_JWT_SECRET=$(gen)" >> "$ZONA_ENV"
  echo "  ZONA_JWT_SECRET qo'shildi (foydalanuvchilar bir marta qayta kiradi)"
  systemctl is-active --quiet zona-backend && systemctl restart zona-backend || true
fi
JWT=$(grep '^ZONA_JWT_SECRET=' "$ZONA_ENV" | tail -1 | cut -d= -f2-)

# 2) QR Drive muhiti
if [[ ! -f "$QR_ENV" ]]; then
  if [[ -z "$DOMAIN" ]]; then
    DOMAIN=$(grep '^ZONA_FRONTEND_URL=' "$ZONA_ENV" | cut -d= -f2- | sed -E 's|^https?://||; s|/.*$||')
  fi
  SCHEME=$(grep -q '^DJANGO_SECURE_COOKIES=1' "$ZONA_ENV" && echo https || echo http)
  sed -e "s|__DOMAIN__|$DOMAIN|g" -e "s|__SCHEME__|$SCHEME|g" \
      -e "s|QRDRIVE_MASTER_KEY=__GENERATE__|QRDRIVE_MASTER_KEY=$(gen)|" \
      -e "s|QRDRIVE_SSO_SECRET=__SSO__|QRDRIVE_SSO_SECRET=$JWT|" \
      "$APP/deploy/qrdrive.env.example" > "$QR_ENV"
  echo "  $QR_ENV yaratildi. QRDRIVE_MASTER_KEY ni alohida saqlab qo'ying!"
else
  # SSO kaliti Zona bilan bir xil bo'lsin
  if ! grep -q "^QRDRIVE_SSO_SECRET=$JWT\$" "$QR_ENV"; then
    sed -i "s|^QRDRIVE_SSO_SECRET=.*|QRDRIVE_SSO_SECRET=$JWT|" "$QR_ENV"
  fi
fi
chown root:zona "$QR_ENV"
chmod 640 "$QR_ENV"
mkdir -p "$DATA"
chown -R zona:zona "$DATA"

# 3) Alohida Python muhiti (Zona paketlaridan mustaqil)
[[ -x "$SVC/.venv/bin/python" ]] || sudo -u zona -H python3 -m venv "$SVC/.venv"
sudo -u zona -H "$SVC/.venv/bin/pip" install -q --upgrade pip wheel
sudo -u zona -H "$SVC/.venv/bin/pip" install -q -e "$SVC"

# 4) systemd
cp "$APP"/deploy/systemd/qrdrive-*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable qrdrive-api qrdrive-worker qrdrive-bot >/dev/null
systemctl restart qrdrive-api qrdrive-worker qrdrive-bot
echo "  QR Drive: api, worker, bot ishga tushirildi"
