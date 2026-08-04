#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${1:-placeit}"

echo "Platform:"
uname -a
python3 --version || true
if command -v apt-cache >/dev/null 2>&1; then
  apt-cache show nvidia-jetpack 2>/dev/null | sed -n '1,6p' || true
fi

if ! command -v conda >/dev/null 2>&1; then
  echo "conda not found. Install Miniforge for aarch64 first, then rerun." >&2
  exit 1
fi

conda env create -n "$ENV_NAME" -f environment.jetson.yml || conda env update -n "$ENV_NAME" -f environment.jetson.yml

CONDA_BASE="$(conda info --base)"
# shellcheck disable=SC1091
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate "$ENV_NAME"

python -m pip install -e .
python scripts/check_placeit_install.py

echo
echo "Ready:"
echo "  conda activate $ENV_NAME"
echo "  bash scripts/run_placeit_smoke.sh"
