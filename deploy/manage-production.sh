#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
env_file="$project_root/.env.production"

if [ ! -f "$env_file" ]; then
    echo "Missing production environment file: $env_file" >&2
    exit 1
fi

set -a
. "$env_file"
set +a

exec "$project_root/.venv/bin/python" "$project_root/apps/api/manage.py" "$@"
