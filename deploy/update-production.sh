#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
remote=${DEPLOY_REMOTE:-origin}
branch=${DEPLOY_BRANCH:-main}
service_name=${DEPLOY_SERVICE_NAME:-oral-sp-api}
health_url=${DEPLOY_HEALTH_URL:-http://127.0.0.1:8010/api/health/ready/}
health_host=${DEPLOY_HEALTH_HOST:-wenzhen.wishine.top}
force=false

log() {
    printf '\n==> %s\n' "$1"
}

fail() {
    printf 'Error: %s\n' "$1" >&2
    exit 1
}

usage() {
    cat <<'EOF'
Usage: ./deploy/update-production.sh [--force]

Update application code from Git, back up SQLite, install dependencies,
apply migrations, build both frontends, restart the API, and verify health.
Nginx configuration and TLS certificates are intentionally not changed.

Options:
  --force     Redeploy even when Git is already up to date.
  -h, --help  Show this help text.
EOF
}

case ${1:-} in
    "")
        ;;
    --force)
        force=true
        ;;
    -h|--help)
        usage
        exit 0
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac

[ "$(id -u)" -ne 0 ] || fail "Run this script as the deployment user, not as root."
[ -d "$project_root/.git" ] || fail "Git repository not found: $project_root"
[ -x "$project_root/.venv/bin/python" ] || fail "Python virtual environment is missing."
[ -f "$project_root/.env.production" ] || fail "Production environment file is missing."

for command_name in git npm sudo curl; do
    command -v "$command_name" >/dev/null 2>&1 || fail "Required command not found: $command_name"
done

cd "$project_root"

current_branch=$(git branch --show-current)
[ "$current_branch" = "$branch" ] || fail "Expected branch '$branch', found '$current_branch'."

worktree_status=$(git status --porcelain --untracked-files=normal)
if [ -n "$worktree_status" ]; then
    printf '%s\n' "$worktree_status" >&2
    fail "The Git worktree is not clean. Commit, move, or remove these files first."
fi

log "Fetching $remote/$branch"
git fetch "$remote" "$branch"

local_revision=$(git rev-parse HEAD)
remote_revision=$(git rev-parse FETCH_HEAD)

git merge-base --is-ancestor "$local_revision" "$remote_revision" || \
    fail "The update is not a fast-forward. Resolve the branch history manually."

if [ "$local_revision" = "$remote_revision" ] && [ "$force" = false ]; then
    printf 'Already up to date at %s. Nothing was deployed.\n' "$(git rev-parse --short HEAD)"
    exit 0
fi

log "Checking sudo access"
sudo -v

log "Backing up the production SQLite database"
sudo "$project_root/deploy/backup.sh"

if [ "$local_revision" != "$remote_revision" ]; then
    log "Updating code with a fast-forward merge"
    git merge --ff-only "$remote_revision"
else
    log "Redeploying the current revision"
fi

log "Installing backend dependencies"
"$project_root/.venv/bin/python" -m pip install \
    -c "$project_root/apps/api/constraints.txt" \
    "$project_root/apps/api"

log "Building student and teacher frontends"
"$project_root/deploy/build-frontends.sh"

log "Checking Django and applying database migrations"
sudo -u www-data "$project_root/deploy/manage-production.sh" check
sudo -u www-data "$project_root/deploy/manage-production.sh" migrate --noinput

log "Restarting $service_name"
if ! sudo systemctl restart "$service_name"; then
    sudo systemctl status "$service_name" --no-pager -l || true
    fail "The API service could not be restarted."
fi

log "Waiting for the API readiness check"
attempt=1
while [ "$attempt" -le 15 ]; do
    if curl --fail --silent --show-error \
        --header "Host: $health_host" \
        --header "X-Forwarded-Proto: https" \
        --output /dev/null \
        "$health_url"; then
        printf 'Deployment completed successfully at %s.\n' "$(git rev-parse --short HEAD)"
        curl --fail --silent --show-error \
            --header "Host: $health_host" \
            --header "X-Forwarded-Proto: https" \
            "$health_url"
        printf '\n'
        exit 0
    fi
    attempt=$((attempt + 1))
    sleep 1
done

sudo systemctl status "$service_name" --no-pager -l || true
sudo journalctl -u "$service_name" -n 50 --no-pager || true
fail "The API did not become ready within 15 seconds."
