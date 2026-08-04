# Jetson setup

Target now: JetPack 7.x / Ubuntu 24.04-class / Jetson Thor.

Do not copy `qdp/` from the workstation. It is x86_64. Rebuild locally on Jetson.

```bash
cd placeit
bash scripts/setup_jetson_conda.sh placeit
conda activate placeit
bash scripts/run_placeit_smoke.sh
```

If `open3d` or `pybullet` fails to install from pip on Jetson, keep the same env and install the failing package from conda-forge or build it locally. Those are the two expected ARM64 pain points.

The env intentionally asks conda for Python 3.10 even on JetPack 7. That is fine: conda isolates Python from the system Python. If conda cannot solve Python 3.10 on that image, change this line in `environment.jetson.yml`:

```yaml
  - python=3.10
```

to:

```yaml
  - python=3.12
```

Then rerun:

```bash
bash scripts/setup_jetson_conda.sh placeit
```

If `open3d==0.19.0` or `pybullet==3.2.6` is the blocker, unpin only that package first:

```yaml
      - pybullet
      - open3d
```

For headless runtime, use `-ll` and do not pass `-d`.

For optional GUI replay:

```bash
python visualization/replay_poses.py -r runs/<run_folder>/ -f -i 0
```
