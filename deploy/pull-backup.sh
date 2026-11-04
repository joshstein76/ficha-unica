#!/bin/bash
# Ficha Única: baja a tu Mac la copia de seguridad más reciente de la base de datos, para tener una fuera del servidor.
# Corre en TU Mac (macOS, bash 3.2), no en el servidor.
#
# Uso:    deploy/pull-backup.sh <carpeta-destino>
# Ejemplo: deploy/pull-backup.sh "$HOME/FichaUnica-respaldos"
#
# Qué hace, en orden:
#   1. Entra por ssh al alias `fichaunica-vps` (usuario deploy) y busca la llave-AAAAMMDD-HHMMSS.db.gz MÁS NUEVA en el
#      servidor. Los archivos son del usuario de la app (fichaunica), así que se leen con `sudo -n` (sin contraseña, sin preguntar).
#   2. La copia a la carpeta destino con un nombre temporal y la revisa: tamaño mayor a cero y `gzip -t`. Solo si pasa, toma su
#      nombre final. Si falla, el temporal se borra y las copias que ya tenías quedan como estaban.
#   3. Deja en la carpeta destino las 14 copias más nuevas (por nombre) y borra las demás de AHÍ. Solo en TU Mac.
#   4. Escribe UNA línea por corrida en <carpeta-destino>/pull-backup.log (fecha, OK / YA ESTABA / ERROR, qué pasó).
#
# NO borra, mueve ni cambia nada en el servidor: solo corre `sudo -n ls -1 <carpeta>` y `sudo -n cat <archivo>`.
# Solo baja la .db.gz (la base de datos), no las fotos. Las copias tienen datos de clientes: los archivos quedan solo para tu usuario.
#
# Ajustes (variables de entorno, casi nunca hacen falta):
#   PULL_BACKUP_SSH         comando que reemplaza a `ssh fichaunica-vps`. Se separa por espacios, sin comillas dentro. Sirve para
#                           probar con un simulador local (tests/test_pull_backup.py); en la vida real no se pone.
#   PULL_BACKUP_REMOTE_DIR  carpeta de respaldos en el servidor (por defecto /srv/fichaunica-data/backups).
#   PULL_BACKUP_KEEP        cuántas copias dejar en tu Mac (por defecto 14).
#
# Salida: 0 bien (o ya la tenías) · 1 no se pudo (queda en el log) · 2 mal uso.
set -u
set -o pipefail
umask 077

REMOTE_DIR=${PULL_BACKUP_REMOTE_DIR:-/srv/fichaunica-data/backups}
KEEP=${PULL_BACKUP_KEEP:-14}
SSH_CMD=${PULL_BACKUP_SSH:-"ssh -o BatchMode=yes -o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=4 fichaunica-vps"}
NAME_RE='^llave-[0-9]{8}-[0-9]{6}\.db\.gz$'

usage() {
  echo "Uso: $0 <carpeta-destino>" >&2
  echo "Baja la copia .db.gz más nueva del servidor (alias ssh fichaunica-vps) a esa carpeta, la revisa y deja las 14 más nuevas." >&2
  exit 2
}

[ $# -eq 1 ] && [ -n "$1" ] || usage
DEST=$1
case $KEEP in ''|*[!0-9]*|0) echo "PULL_BACKUP_KEEP debe ser un número mayor a cero" >&2; exit 2 ;; esac
printf '%s' "$REMOTE_DIR" | grep -Eq '^/[A-Za-z0-9_./-]+$' || { echo "PULL_BACKUP_REMOTE_DIR no es una ruta simple" >&2; exit 2; }
if [ -e "$DEST" ] && [ ! -d "$DEST" ]; then echo "No es una carpeta: $DEST" >&2; exit 2; fi
mkdir -p "$DEST" || { echo "No pude crear la carpeta: $DEST" >&2; exit 2; }
[ -w "$DEST" ] || { echo "No puedo escribir en: $DEST" >&2; exit 2; }

LOG="$DEST/pull-backup.log"
TMP=""
ERRF="$DEST/.pull-backup.$$.err"
cleanup() {
  [ -n "$TMP" ] && rm -f -- "$TMP"
  rm -f -- "$ERRF"
}
trap cleanup EXIT
trap 'exit 1' INT TERM

# Una sola línea de log por corrida: todas las salidas pasan por aquí.
finish() {  # finish <código> <ESTADO> <mensaje>
  local code=$1 status=$2; shift 2
  local line
  line="$(date '+%Y-%m-%dT%H:%M:%S%z') $status $*"
  printf '%s\n' "$line" >> "$LOG"
  if [ "$code" -eq 0 ]; then printf '%s\n' "$line"; else printf '%s\n' "$line" >&2; fi
  exit "$code"
}

# Lo que dijo el servidor (ssh / sudo), en una línea y corto, para el log.
why() {
  head -c 300 "$ERRF" 2>/dev/null | tr '\r\n\t' '   ' | sed 's/  */ /g; s/^ //; s/ $//'
}

# ---- 1. cuál es la más nueva en el servidor
LIST=$($SSH_CMD "sudo -n ls -1 $REMOTE_DIR" 2>"$ERRF" </dev/null)
rc=$?
[ $rc -eq 0 ] || finish 1 ERROR "no pude leer la carpeta de respaldos del servidor (ssh o sudo, código $rc): $(why)"
NEWEST=$(printf '%s\n' "$LIST" | grep -E "$NAME_RE" | sort | tail -n 1)
[ -n "$NEWEST" ] || finish 1 ERROR "el servidor no tiene ninguna copia llave-AAAAMMDD-HHMMSS.db.gz en $REMOTE_DIR"

# ---- 2. copiarla y revisarla (o confirmar que ya la tienes bien)
ok_file() {  # ok_file <ruta>: existe, pesa más de cero y gzip la da por buena
  [ -s "$1" ] && gzip -t "$1" 2>/dev/null
}
FINAL="$DEST/$NEWEST"
if [ -f "$FINAL" ] && ok_file "$FINAL"; then
  STATUS="YA ESTABA"
else
  TMP="$DEST/.$NEWEST.$$.part"
  $SSH_CMD "sudo -n cat $REMOTE_DIR/$NEWEST" >"$TMP" 2>"$ERRF" </dev/null
  rc=$?
  [ $rc -eq 0 ] || finish 1 ERROR "$NEWEST: falló la copia (código $rc): $(why)"
  [ -s "$TMP" ] || finish 1 ERROR "$NEWEST: llegó vacía; no la guardé"
  gzip -t "$TMP" 2>"$ERRF" || finish 1 ERROR "$NEWEST: gzip -t dice que está dañada o incompleta; no la guardé: $(why)"
  mv -f -- "$TMP" "$FINAL" || finish 1 ERROR "$NEWEST: no pude guardarla en $DEST"
  TMP=""
  STATUS="OK"
fi
SIZE=$(wc -c < "$FINAL" | tr -d ' ')

# ---- 3. dejar las KEEP más nuevas (por nombre, que lleva la fecha); solo en esta carpeta, solo copias llave-*.db.gz
n=0
removed=0
for f in $(ls -1 "$DEST" | grep -E "$NAME_RE" | sort -r); do
  n=$((n + 1))
  if [ "$n" -gt "$KEEP" ] && [ "$f" != "$NEWEST" ]; then
    rm -f -- "$DEST/$f" && removed=$((removed + 1))
  fi
done
kept=$((n - removed))

# ---- 4. una línea de log
finish 0 "$STATUS" "$NEWEST ${SIZE} bytes; copias en la carpeta: $kept; borradas aquí: $removed"
