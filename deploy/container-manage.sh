#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

if [ "$#" -eq 0 ]; then
    echo "Usage: container-manage.sh DJANGO_COMMAND [ARGUMENTS...]" >&2
    exit 2
fi

exec "$project_root/deploy/container-compose.sh" run --rm --no-deps api \
    python manage.py "$@"
