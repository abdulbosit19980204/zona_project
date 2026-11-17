#!/usr/bin/env bash
# Foydali frontend (pm2: foydali-frontend) boshqaruvi. Boshqaruv markazi «sudo -n» bilan chaqiradi.
# Faqat shu bitta jarayon ustida amal bajaradi — boshqa pm2 jarayonlari (masalan biolab-frontend)ga tegmaydi.
# foydali-setup.sh /usr/local/sbin/foydali-pm2 ga o'rnatadi va __NODE_BIN__ ni almashtiradi.
set -euo pipefail
export HOME=/root PM2_HOME=/root/.pm2 PATH="__NODE_BIN__:/usr/local/bin:/usr/bin:/bin"
NAME=foydali-frontend
ECO=/etc/foydali/foydali.ecosystem.config.cjs

case "${1:-}" in
  status)
    pm2 jlist 2>/dev/null | python3 -c '
import json, sys, time
apps = [a for a in json.load(sys.stdin) if a.get("name") == "foydali-frontend"]
if not apps:
    print(json.dumps({"state": "stopped"})); sys.exit()
e = apps[0]["pm2_env"]
st = {"online": "running", "launching": "starting", "stopping": "stopping", "errored": "crashed"}.get(e.get("status"), "stopped")
up = (time.time() * 1000 - e.get("pm_uptime", 0)) / 1000 if st == "running" else None
print(json.dumps({"state": st, "pid": apps[0].get("pid") or None, "restarts": e.get("restart_time", 0), "uptime": up}))'
    ;;
  start)
    if pm2 describe "$NAME" >/dev/null 2>&1; then pm2 start "$NAME" >/dev/null; else pm2 start "$ECO" --only "$NAME" >/dev/null; fi
    pm2 save >/dev/null; echo ok ;;
  stop)    pm2 stop "$NAME" >/dev/null; pm2 save >/dev/null; echo ok ;;
  restart) pm2 restart "$NAME" --update-env >/dev/null; echo ok ;;
  logs)
    n="${2:-200}"; [[ "$n" =~ ^[0-9]+$ ]] || n=200
    pm2 logs "$NAME" --lines "$n" --nostream --raw 2>&1 | tail -n "$n" ;;
  *) echo "ishlatish: $0 status|start|stop|restart|logs [N]" >&2; exit 2 ;;
esac
