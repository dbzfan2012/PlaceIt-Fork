# Jetson setup

Target now: JetPack 7.x / Ubuntu 24.04-class / Jetson Thor.

Do not copy `qdp/` from the workstation. It is x86_64. Rebuild locally on Jetson.

```bash
cd placeit
bash scripts/setup_jetson_conda.sh placeit
conda activate placeit
bash scripts/run_placeit_smoke.sh
```

If a pinned ARM64 package is unavailable, unpin only that package first:

```yaml
      - pybullet
      - open3d
```

For headless runtime, use `-ll` and do not pass `-d`.

For optional GUI replay:

```bash
python visualization/replay_poses.py -r runs/<run_folder>/ -f -i 0
```
