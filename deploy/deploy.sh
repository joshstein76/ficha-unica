#!/usr/bin/env bash
# Ficha Única deploy. DRY-RUN BY DEFAULT: prints what it would do. Real deploy needs deploy/target.env AND --go.
# Usage: deploy/deploy.sh            (dry run: tests + rsync --dry-run preview)
#        deploy/deploy.sh --go       (real: tests, backup on server, rsync, restart, health check, rollback on failure)
set -euo pipefail
cd "$(dirname "$0")/.."
GO=0; [[ "${1:-}" == "--go" ]] && GO=1
[[ -f deploy/target.env ]] || { echo "No deploy/target.env yet (copy deploy/target.env.example once the Hostinger plan is chosen). Dry run only."; GO=0; TARGET_KIND=vps; SSH_HOST=example; SSH_USER=example; SSH_PORT=22; APP_DIR=/srv/fichaunica; DATA_DIR=/srv/fichaunica-data; PYTHON=python3; }
[[ -f deploy/target.env ]] && source deploy/target.env
for v in SSH_HOST SSH_USER APP_DIR DATA_DIR; do [[ "${!v}" == REPLACE_ME* ]] && { echo "Fill $v in deploy/target.env"; exit 1; }; done

echo "== 1. Tests"; python3 -m unittest discover -s tests >/dev/null 2>&1 && echo "tests OK" || { echo "TESTS FAIL: not deploying"; exit 1; }
REL=$(git rev-parse --short HEAD); [[ -z "$(git status --porcelain)" ]] || { echo "Uncommitted changes: commit first"; [[ $GO == 1 ]] && exit 1; }
SSH="ssh -p ${SSH_PORT:-22} ${SSH_USER}@${SSH_HOST}"
RSYNC_OPTS=(-az --delete --exclude .git --exclude data/ --exclude 'deploy/target.env' --exclude '__pycache__' --exclude 'seed/*.local.md' --exclude 'config/*.env' --exclude 'config/*.env.bak*' -e "ssh -p ${SSH_PORT:-22}")
DEST="${SSH_USER}@${SSH_HOST}:${APP_DIR}/releases/${REL}/"

if [[ $GO == 0 ]]; then
  echo "== DRY RUN (nothing sent). Would:"
  echo "  - backup on server:   $SSH '$PYTHON $APP_DIR/current/tools/backup.py --dest $DATA_DIR/backups --prune'"
  echo "  - upload release:     rsync ${RSYNC_OPTS[*]} ./ $DEST"
  echo "  - switch symlink:     $APP_DIR/current -> releases/$REL (keep previous for rollback)"
  if [[ "$TARGET_KIND" == vps ]]; then echo "  - restart:            sudo systemctl restart fichaunica"; else echo "  - restart:            $APP_DIR/current/deploy/run-cloud.sh restart"; fi
  echo "  - health check:       curl -fsS http://127.0.0.1:8640/healthz on the server; rollback symlink if it fails"
  exit 0
fi

echo "== 2. Backup on server"
if [[ "$TARGET_KIND" == vps ]]; then  # app.env is 600 for the app user: back up as that user, fail the deploy if it fails
  $SSH "test ! -e $APP_DIR/current || sudo -u fichaunica bash -c 'set -a && . $DATA_DIR/app.env && set +a && cd $APP_DIR/current && $PYTHON tools/backup.py --dest $DATA_DIR/backups --prune'" || { echo "BACKUP FAILED: not deploying"; exit 1; }
else
  $SSH "test -e $APP_DIR/current && set -a && . $DATA_DIR/app.env && set +a && $PYTHON $APP_DIR/current/tools/backup.py --dest $DATA_DIR/backups --prune || echo 'first deploy: no backup'"
fi
echo "== 3. Upload $REL"; $SSH "mkdir -p $APP_DIR/releases/$REL"; rsync "${RSYNC_OPTS[@]}" ./ "$DEST"
echo "== 4. Switch"; PREV=$($SSH "readlink $APP_DIR/current || true"); $SSH "ln -sfn $APP_DIR/releases/$REL $APP_DIR/current"
echo "== 5. Restart"
if [[ "$TARGET_KIND" == vps ]]; then $SSH "sudo systemctl restart fichaunica"; else $SSH "$APP_DIR/current/deploy/run-cloud.sh restart"; fi
echo "== 6. Health"; sleep 3
if $SSH "curl -fsS http://127.0.0.1:8640/healthz | grep -q '\"ok\": true'"; then echo "DEPLOYED $REL"; else
  echo "HEALTH FAILED: rolling back to $PREV"; [[ -n "$PREV" ]] && $SSH "ln -sfn $PREV $APP_DIR/current"
  if [[ "$TARGET_KIND" == vps ]]; then $SSH "sudo systemctl restart fichaunica"; else $SSH "$APP_DIR/current/deploy/run-cloud.sh restart"; fi; exit 1; fi
