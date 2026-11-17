#!/usr/bin/env bash
# Ishchi bazaning izchil zaxira nusxasi (server ishlab turganda ham xavfsiz). Oxirgi 14 kun saqlanadi.
#   qo'lda:  sudo -u zona /opt/zona/deploy/backup.sh
#   avtomatik: zona-backup.timer (har kuni 02:30)
set -euo pipefail

DB="${ZONA_DB_PATH:-/var/lib/zona/db.sqlite3}"
DIR="${ZONA_BACKUP_DIR:-/var/lib/zona/backups}"
KEEP_DAYS="${ZONA_BACKUP_DAYS:-14}"
mkdir -p "$DIR"
OUT="$DIR/db-$(date +%Y%m%d-%H%M%S).sqlite3"

/opt/zona/.venv/bin/python - "$DB" "$OUT" <<'PY'
import sqlite3, sys
src, dst = sqlite3.connect(sys.argv[1]), sqlite3.connect(sys.argv[2])
with dst:
    src.backup(dst)
ok = dst.execute("PRAGMA integrity_check").fetchone()[0]
src.close(); dst.close()
if ok != "ok":
    sys.exit(f"integrity_check: {ok}")
PY

gzip -f "$OUT"

# QR Drive bazasi (alohida servis — alohida baza)
QR_DB="${QRDRIVE_DB_PATH:-/var/lib/zona/qrdrive/qrdrive.sqlite3}"
if [[ -f "$QR_DB" ]]; then
  QR_OUT="$DIR/qrdrive-$(date +%Y%m%d-%H%M%S).sqlite3"
  /opt/zona/.venv/bin/python - "$QR_DB" "$QR_OUT" <<'PY'
import sqlite3, sys
src, dst = sqlite3.connect(sys.argv[1]), sqlite3.connect(sys.argv[2])
with dst:
    src.backup(dst)
src.close(); dst.close()
PY
  gzip -f "$QR_OUT"
fi
find "$DIR" \( -name 'db-*.sqlite3.gz' -o -name 'qrdrive-*.sqlite3.gz' \) -mtime +"$KEEP_DAYS" -delete
echo "Zaxira: $OUT.gz"
