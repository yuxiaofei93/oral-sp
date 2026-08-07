#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
deploy_env="$project_root/.env.deploy"
compose_file="$project_root/compose.acr.yaml"

if [ ! -f "$deploy_env" ]; then
    echo "Missing deployment environment file: $deploy_env" >&2
    exit 1
fi

exec docker compose --env-file "$deploy_env" -f "$compose_file" "$@"
