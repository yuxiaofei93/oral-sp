#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
web_root="$project_root/apps/web"

export VITE_STUDENT_ORIGIN=${VITE_STUDENT_ORIGIN:-https://wenzhen.wishine.top}
export VITE_TEACHER_ORIGIN=${VITE_TEACHER_ORIGIN:-https://manage.wishine.top}

npm --prefix "$web_root" ci --no-audit --no-fund
npm --prefix "$web_root" run build:student
npm --prefix "$web_root" run build:teacher
