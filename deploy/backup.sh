#!/usr/bin/env bash
# =============================================================
# Backup diário do PAC Download.
# Roda via crontab: 0 3 * * * cd /opt/pac-xml-downloader && bash deploy/backup.sh
# =============================================================

set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/pac-xml-downloader}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/pac}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

# (Opcional) Upload para storage externo
# Se quiser usar Backblaze B2, descomente e configure:
#   B2_ACCOUNT_ID=...
#   B2_APP_KEY=...
#   B2_BUCKET=pac-backups
B2_BUCKET="${B2_BUCKET:-}"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

cd "$REPO_DIR"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# 1. Dump Postgres
log "Iniciando dump do Postgres..."
PG_DUMP_FILE="$BACKUP_DIR/pg_${TIMESTAMP}.sql.gz"
docker compose -f docker-compose.production.yml exec -T postgres \
  pg_dump -U "${POSTGRES_USER:-pac}" "${POSTGRES_DB:-pac_xml}" | gzip > "$PG_DUMP_FILE"

DUMP_SIZE=$(du -h "$PG_DUMP_FILE" | cut -f1)
log "✓ Postgres dump: $PG_DUMP_FILE ($DUMP_SIZE)"

# 2. Tar do storage (XMLs, CNDs, SITFIS, apuracoes)
log "Empacotando storage..."
STORAGE_FILE="$BACKUP_DIR/storage_${TIMESTAMP}.tar.gz"
docker compose -f docker-compose.production.yml exec -T backend \
  tar czf - /app/storage > "$STORAGE_FILE"

STORAGE_SIZE=$(du -h "$STORAGE_FILE" | cut -f1)
log "✓ Storage: $STORAGE_FILE ($STORAGE_SIZE)"

# 3. (Opcional) Upload para Backblaze B2
if [[ -n "$B2_BUCKET" && -n "${B2_ACCOUNT_ID:-}" && -n "${B2_APP_KEY:-}" ]]; then
  if command -v b2 &>/dev/null; then
    log "Enviando para Backblaze B2..."
    b2 authorize-account "$B2_ACCOUNT_ID" "$B2_APP_KEY"
    b2 upload-file "$B2_BUCKET" "$PG_DUMP_FILE"  "pg/$(basename "$PG_DUMP_FILE")"
    b2 upload-file "$B2_BUCKET" "$STORAGE_FILE"  "storage/$(basename "$STORAGE_FILE")"
    log "✓ Upload B2 OK"
  else
    log "⚠ b2 CLI não instalado — pulando upload (instale com: pip install b2)"
  fi
fi

# 4. Limpa backups antigos (>$RETENTION_DAYS)
log "Limpando backups com mais de $RETENTION_DAYS dias..."
find "$BACKUP_DIR" -name "pg_*.sql.gz"       -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "storage_*.tar.gz"  -mtime +$RETENTION_DAYS -delete

log "✅ Backup concluído com sucesso."
log "Backups locais em: $BACKUP_DIR"
ls -lh "$BACKUP_DIR" | tail -10
