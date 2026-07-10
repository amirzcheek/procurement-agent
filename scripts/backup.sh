#!/bin/sh
# Бэкап базы знаний закупок (pg_dump контейнера procurement-db) в gzip с датой.
# Использование:  ./scripts/backup.sh            (папка ./backups)
#                 BACKUP_DIR=/data ./scripts/backup.sh
# Восстановление: gunzip -c backups/procurement_YYYYmmdd_HHMMSS.sql.gz \
#                   | docker exec -i procurement-db psql -U procurement -d procurement
set -e

DIR="${BACKUP_DIR:-./backups}"
USER="${POSTGRES_USER:-procurement}"
DB="${POSTGRES_DB:-procurement}"
mkdir -p "$DIR"
STAMP=$(date +%Y%m%d_%H%M%S)
OUT="$DIR/procurement_${STAMP}.sql.gz"

docker exec procurement-db pg_dump -U "$USER" "$DB" | gzip > "$OUT"
echo "backup: $OUT"

# Ротация: оставить последние 30 бэкапов.
ls -1t "$DIR"/procurement_*.sql.gz 2>/dev/null | tail -n +31 | xargs -r rm -f
