#!/usr/bin/env bash
# Hot backup of the SQLite database (safe while the worker runs).
# Cron example:  0 3 * * *  cd /opt/pokewatch && deploy/backup_sqlite.sh
set -euo pipefail
DB="${1:-data/pokewatch.db}"
OUT="data/backups"
STAMP="$(date +%F)"
mkdir -p "$OUT"
sqlite3 "$DB" ".backup '$OUT/pokewatch-$STAMP.db'"
gzip -f "$OUT/pokewatch-$STAMP.db"
# keep the 14 newest backups
ls -1t "$OUT"/pokewatch-*.db.gz | tail -n +15 | xargs -r rm --
