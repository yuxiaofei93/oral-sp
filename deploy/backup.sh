#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
database_path=${SQLITE_DB_PATH:-"$project_root/var/production.sqlite3"}
backup_dir=${BACKUP_DIR:-"$project_root/backups"}

if [ ! -f "$database_path" ]; then
    echo "SQLite database does not exist: $database_path" >&2
    exit 1
fi

case "$backup_dir" in
    ""|"/")
        echo "Refusing unsafe backup directory: $backup_dir" >&2
        exit 1
        ;;
esac

umask 077
mkdir -p "$backup_dir"
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_path="$backup_dir/oral-sp-sqlite-$timestamp.sqlite3"
partial_path="$backup_path.partial"
trap 'rm -f "$partial_path"' EXIT HUP INT TERM

"$project_root/.venv/bin/python" "$project_root/deploy/backup_sqlite.py" \
    "$database_path" "$partial_path"

mv "$partial_path" "$backup_path"
trap - EXIT HUP INT TERM

echo "Database backup created: $backup_path"
