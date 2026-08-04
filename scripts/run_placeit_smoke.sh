#!/usr/bin/env bash
set -euo pipefail

export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/placeit-mpl-cache}"

python run_qd_place.py \
  -a placeit_rand_sample \
  -nbr 20 \
  -p 20 \
  -o ycb_mug \
  -t table \
  -ii \
  -ll \
  -f jetson_smoke

python - <<'PY'
from pathlib import Path
import numpy as np

run = max(Path("runs").glob("jetson_smoke*"), key=lambda p: p.stat().st_mtime)
d = np.load(run / "run_data.npz")
print("run:", run)
print("internal_runtime_s:", float(d["run_time_hist"][-1]))
print("actual_evals:", int(d["n_evals_hist"][-1]))
print("successful_cells:", int(d["n_successful_cells_list"][-1]))
PY
