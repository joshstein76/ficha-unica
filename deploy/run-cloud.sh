#!/usr/bin/env bash
# Hostinger Cloud/shared (no root, no systemd): run the app as a setsid daemon; cron calls "watch" every minute to restart it if it died.
# Usage: run-cloud.sh start|stop|restart|watch
set -u
APP="$(cd "$(dirname "$0")/.." && pwd)"; DATA="${DATA_DIR:-$HOME/fichaunica-data}"; PIDF="$DATA/fichaunica.pid"
start() { set -a; . "$DATA/app.env"; set +a; mkdir -p "$DATA/logs"; cd "$APP" && setsid nohup python3 -m llave.web.server >> "$DATA/logs/server.log" 2>&1 < /dev/null & echo $! > "$PIDF"; disown || true; }
alive() { [[ -f "$PIDF" ]] && kill -0 "$(cat "$PIDF")" 2>/dev/null; }
case "${1:-}" in
  start) alive || start ;;
  stop) alive && kill "$(cat "$PIDF")"; rm -f "$PIDF" ;;
  restart) alive && kill "$(cat "$PIDF")"; sleep 1; start ;;
  watch) alive || { echo "$(date -u) restarting" >> "$DATA/logs/watchdog.log"; start; } ;;
  *) echo "usage: $0 start|stop|restart|watch"; exit 1 ;;
esac
