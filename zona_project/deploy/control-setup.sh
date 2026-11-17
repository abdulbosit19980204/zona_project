#!/usr/bin/env bash
# Servislar boshqaruv markazini o'rnatish (install.sh / update.sh chaqiradi; qayta ishga tushirish xavfsiz).
# Sahifa: https://<domen>/control/   — parol: /etc/zona/control.env (CONTROL_PASSWORD)
set -euo pipefail

APP=/opt/zona
ENV=/etc/zona/control.env
UNITS="zona-backend zona-frontend qrdrive-api qrdrive-worker qrdrive-bot nginx"

if [[ $EUID -ne 0 ]]; then echo "sudo bilan ishga tushiring"; exit 1; fi

if [[ ! -f "$ENV" ]]; then
  PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(14))")
  cat > "$ENV" <<EOF
# Servislar boshqaruv markazi
CONTROL_PASSWORD=$PASS
CONTROL_HOST=127.0.0.1
CONTROL_PORT=8900
CONTROL_CONFIG=$APP/deploy/control.services.json
CONTROL_DATA_DIR=/var/lib/zona/control
EOF
  echo "  Boshqaruv markazi paroli: $PASS   (saqlangan: $ENV)"
fi
chown root:zona "$ENV"
chmod 640 "$ENV"
mkdir -p /var/lib/zona/control
chown zona:zona /var/lib/zona/control

# zona foydalanuvchisi faqat shu servislarni boshqara oladi (boshqa hech narsa emas)
SUDOERS=/etc/sudoers.d/zona-control
{
  echo "# Servislar boshqaruv markazi: faqat Zona servislarini boshqarish va jurnalini o'qish"
  for u in $UNITS; do
    for a in start stop restart; do echo "zona ALL=(root) NOPASSWD: /usr/bin/systemctl $a $u, /bin/systemctl $a $u"; done
    echo "zona ALL=(root) NOPASSWD: /usr/bin/journalctl -u $u *, /bin/journalctl -u $u *"
  done
} > "$SUDOERS.tmp"
visudo -cf "$SUDOERS.tmp" >/dev/null
mv "$SUDOERS.tmp" "$SUDOERS"
chmod 440 "$SUDOERS"

cp "$APP/deploy/systemd/zona-control.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now zona-control >/dev/null
systemctl restart zona-control
echo "  Boshqaruv markazi ishga tushdi: /control/"
