#!/usr/bin/env bash
# Zona: kodni yangilash. Ishchi baza (/var/lib/zona/db.sqlite3) saqlanadi — faqat migratsiyalar qo'llanadi.
#   sudo bash /opt/zona/deploy/update.sh
set -euo pipefail

APP=/opt/zona
ENVFILE=/etc/zona/zona.env
if [[ $EUID -ne 0 ]]; then echo "sudo bilan ishga tushiring"; exit 1; fi
cd "$APP"
REPO="$(git -C "$APP" rev-parse --show-toplevel)"

echo "==> Yangilashdan oldin zaxira"
sudo -u zona -H bash -c "set -a; source $ENVFILE; set +a; bash $APP/deploy/backup.sh"

echo "==> Kod (git pull)"
sudo -u zona -H git -C "$REPO" pull --ff-only

echo "==> Python paketlar, migratsiya, statik"
sudo -u zona -H "$APP/.venv/bin/pip" install -q -e "$APP[ai,server]"
run_manage() { sudo -u zona -H bash -c "set -a; source $ENVFILE; set +a; cd $APP/backend && $APP/.venv/bin/python manage.py $*"; }
run_manage migrate --noinput
run_manage collectstatic --noinput
# Yangi qo'shilgan matnlar tarjima xotirasida bo'lsa — darhol tarjima qilinadi (AI'siz)
run_manage shell -c "\"from zona import translation; print('tarjima:', translation.translate_pending(use_ai=False))\"" || true

echo "==> QR Drive mikroservisi"
bash "$APP/deploy/qrdrive-setup.sh"

echo "==> Servislar boshqaruv markazi"
bash "$APP/deploy/control-setup.sh"

echo "==> Frontend build"
sudo -u zona -H bash -c "cd $APP/frontend && npm ci && BACKEND_URL=http://127.0.0.1:8000 npm run build"

echo "==> Servislarni qayta ishga tushirish"
cp deploy/systemd/zona-*.service deploy/systemd/zona-backup.timer /etc/systemd/system/
systemctl daemon-reload
systemctl restart zona-backend zona-frontend
sleep 3
systemctl --no-pager --lines=0 status zona-backend zona-frontend qrdrive-api qrdrive-worker qrdrive-bot | grep -E "Active:|●"
echo "Tayyor."
