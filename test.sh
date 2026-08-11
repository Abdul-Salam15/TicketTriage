#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/backend"

if [ ! -d "venv" ]; then
  echo "Creating virtual environment..." >&2
  python -m venv venv
fi

# shellcheck disable=SC1091
source venv/Scripts/activate 2>/dev/null || source venv/bin/activate

pip install -q -r requirements.txt -r requirements-dev.txt
pytest -q "$@"
