#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
docker build -t sw-uav:basic -f "${PROJECT_DIR}/docker/Dockerfile" "${PROJECT_DIR}"
