#!/usr/bin/env bash
# Lokal Telegram Bot API server (telegram-bot-api): botga 2000 MB gacha fayl yuborish imkonini beradi.
# Rasmiy api.telegram.org botlarga 20 MB dan katta faylni bermaydi.
#
# Ishlatish (bir marta, qayta ishga tushirish xavfsiz):
#   1) https://my.telegram.org -> «API development tools» -> api_id va api_hash oling
#   2) sudo bash deploy/telegram-bot-api-setup.sh            # birinchi marta /etc/zona/telegram-bot-api.env yaratadi
#      /etc/zona/telegram-bot-api.env ga TELEGRAM_API_ID va TELEGRAM_API_HASH ni yozing
#   3) sudo bash deploy/telegram-bot-api-setup.sh            # yig'adi (birinchi marta 10–30 daqiqa), servisni yoqadi
#   4) Panel -> QR Drive -> Sozlamalar -> Bot:
#        «Rasmiy serverdan chiqish (logOut)» -> Bot API server: http://127.0.0.1:8081 -> «Lokal rejim» yoqing -> Saqlash
#        «Maksimal fayl hajmi» ni kerakli qiymatga (masalan 2000 MB) oshiring
# Bot va worker sozlama o'zgarishini o'zi sezadi — qayta ishga tushirish shart emas.
set -euo pipefail

ENV=/etc/zona/telegram-bot-api.env
SRC=/opt/telegram-bot-api-src
BIN=/usr/local/bin/telegram-bot-api
DATA=/var/lib/zona/telegram-bot-api   # worker fayllarni shu yerdan o'qiydi (qrdrive servislarida ReadWritePaths=/var/lib/zona)
APP=/opt/zona

if [[ $EUID -ne 0 ]]; then echo "sudo bilan ishga tushiring"; exit 1; fi

# 1) api_id / api_hash
if [[ ! -f "$ENV" ]]; then
  install -d -m 750 -o root -g zona /etc/zona
  cat > "$ENV" <<'EOF'
# https://my.telegram.org -> API development tools
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
EOF
  chmod 640 "$ENV"; chown root:zona "$ENV"
  echo "$ENV yaratildi. TELEGRAM_API_ID va TELEGRAM_API_HASH ni yozing va skriptni qayta ishga tushiring."
  exit 0
fi
# shellcheck disable=SC1090
source "$ENV"
if [[ -z "${TELEGRAM_API_ID:-}" || -z "${TELEGRAM_API_HASH:-}" ]]; then
  echo "$ENV da TELEGRAM_API_ID va TELEGRAM_API_HASH bo'sh. https://my.telegram.org dan oling."; exit 1
fi

# 2) Yig'ish (faqat birinchi marta yoki --rebuild bilan)
if [[ ! -x "$BIN" || "${1:-}" == "--rebuild" ]]; then
  echo "telegram-bot-api yig'ilmoqda (10–30 daqiqa, ~2 GB RAM kerak)…"
  apt-get update -qq
  apt-get install -y -qq make git zlib1g-dev libssl-dev gperf cmake g++
  if [[ -d "$SRC/.git" ]]; then
    git -C "$SRC" pull -q && git -C "$SRC" submodule update --init --recursive -q
  else
    git clone -q --recursive https://github.com/tdlib/telegram-bot-api.git "$SRC"
  fi
  cmake -S "$SRC" -B "$SRC/build" -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local >/dev/null
  cmake --build "$SRC/build" --target install -j"$(nproc)"
fi

# 3) Servis
install -d -o zona -g zona "$DATA" "$DATA/tmp"
install -m 644 "$APP/deploy/systemd/telegram-bot-api.service" /etc/systemd/system/telegram-bot-api.service
systemctl daemon-reload
systemctl enable --now telegram-bot-api
systemctl restart telegram-bot-api
sleep 2
if systemctl is-active --quiet telegram-bot-api; then
  echo "✅ telegram-bot-api ishlayapti: http://127.0.0.1:8081"
  echo "Endi panelda: Bot -> logOut -> Bot API server = http://127.0.0.1:8081 -> Lokal rejim -> Saqlash"
else
  echo "❌ Servis ishga tushmadi: journalctl -u telegram-bot-api -n 50"; exit 1
fi
