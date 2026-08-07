#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
deploy_env="$project_root/.env.deploy"
production_env="$project_root/.env.production"

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this deployment script with sudo." >&2
    exit 1
fi

if [ "$#" -ne 1 ]; then
    echo "Usage: container-deploy.sh IMAGE_TAG" >&2
    exit 2
fi

new_tag=$1
case "$new_tag" in
    *[!A-Za-z0-9_.-]*|"")
        echo "Invalid image tag: $new_tag" >&2
        exit 2
        ;;
esac

if [ ! -f "$deploy_env" ]; then
    echo "Missing deployment environment file: $deploy_env" >&2
    exit 1
fi

if [ ! -f "$production_env" ]; then
    echo "Missing production environment file: $production_env" >&2
    exit 1
fi

set -a
. "$deploy_env"
set +a

previous_tag=${IMAGE_TAG:-}
IMAGE_TAG=$new_tag
export IMAGE_TAG

compose() {
    docker compose --env-file "$deploy_env" -f "$project_root/compose.acr.yaml" "$@"
}

echo "Pulling ACR images tagged $new_tag ..."
compose pull

if [ -f "$project_root/var/production.sqlite3" ]; then
    "$project_root/deploy/backup.sh"
fi

echo "Stopping the API for the database migration ..."
compose stop api
compose run --rm --no-deps api python manage.py migrate --noinput

echo "Starting the release and waiting for health checks ..."
compose up -d --remove-orphans --wait --wait-timeout 180

if grep -q '^IMAGE_TAG=' "$deploy_env"; then
    sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=$new_tag/" "$deploy_env"
else
    printf '\nIMAGE_TAG=%s\n' "$new_tag" >>"$deploy_env"
fi

echo "Deployment completed: $new_tag"
if [ -n "$previous_tag" ] && [ "$previous_tag" != "$new_tag" ]; then
    echo "Previous image tag: $previous_tag"
fi
