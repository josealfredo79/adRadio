#!/usr/bin/env bash
# backup_db.sh — Dump the production Postgres (Neon) database with pg_dump.
#
# Usage:
#   DATABASE_URL=postgresql+asyncpg://user:pass@host.neon.tech/dbname?ssl=require \
#     ./backup_db.sh
#
# Optional env vars:
#   BACKUP_OUT_DIR   Directory to write the dump file into (default: current dir)
#
# The app's DATABASE_URL is a SQLAlchemy-style asyncpg URL
# (postgresql+asyncpg://...?ssl=require). pg_dump needs a plain libpq URL
# (postgresql://...?sslmode=require), so this script rewrites it before use.
#
# Produces a timestamped custom-format (compressed) dump:
#   iaradio_backup_YYYYMMDD_HHMMSS.dump
#
# Exits non-zero (with a clear message) if DATABASE_URL is unset, empty,
# or pg_dump fails / produces an empty file.

set -euo pipefail

if [ -z "${DATABASE_URL:-}" ]; then
  echo "ERROR: DATABASE_URL is not set. Cannot run backup." >&2
  exit 1
fi

if ! command -v pg_dump >/dev/null 2>&1; then
  echo "ERROR: pg_dump is not installed / not on PATH." >&2
  exit 1
fi

# Rewrite SQLAlchemy async driver scheme -> plain postgresql:// for pg_dump.
PG_URL="${DATABASE_URL/postgresql+asyncpg:\/\//postgresql://}"
PG_URL="${PG_URL/postgres+asyncpg:\/\//postgresql://}"

# asyncpg's query param is `ssl=`, libpq/pg_dump expects `sslmode=`.
PG_URL="${PG_URL/ssl=/sslmode=}"

OUT_DIR="${BACKUP_OUT_DIR:-.}"
mkdir -p "$OUT_DIR"

TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"
OUT_FILE="${OUT_DIR%/}/iaradio_backup_${TIMESTAMP}.dump"

echo "Starting pg_dump backup -> ${OUT_FILE}"

if ! pg_dump --no-owner --no-privileges -Fc --dbname="$PG_URL" -f "$OUT_FILE"; then
  echo "ERROR: pg_dump failed. See output above for details." >&2
  rm -f "$OUT_FILE"
  exit 1
fi

if [ ! -s "$OUT_FILE" ]; then
  echo "ERROR: backup file '${OUT_FILE}' is empty. Treating as a failed backup." >&2
  rm -f "$OUT_FILE"
  exit 1
fi

echo "Backup completed successfully: ${OUT_FILE} ($(du -h "$OUT_FILE" | cut -f1))"
