import argparse
import csv
import os
import pickle
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/placeit-mpl-cache")

import matplotlib.pyplot as plt
import numpy as np
import pybullet as p

from configs.obj_config import OBJ_ENV_CLASS


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--budgets", type=int, nargs="+", default=[20, 50, 100, 200, 500, 1000])
    p.add_argument("--population", "-p", type=int, default=20)
    p.add_argument("--algorithm", "-a", default="placeit_rand_sample")
    p.add_argument("--object", "-o", default="ycb_mug")
    p.add_argument("--target", "-t", default="table")
    p.add_argument("--log-path", default="runs/runtime_candidates")
    p.add_argument("--name", default="runtime_candidates")
    p.add_argument("--sample-interval", type=float, default=0.25)
    return p.parse_args()


def proc_children(pid):
    children = []
    for stat in Path("/proc").glob("[0-9]*/stat"):
        try:
            parts = stat.read_text().split()
            if int(parts[3]) == pid:
                child = int(parts[0])
                children.append(child)
                children.extend(proc_children(child))
        except (FileNotFoundError, IndexError, ValueError, ProcessLookupError):
            pass
    return children


def proc_rss_mib(pid):
    total = 0.0
    for p in [pid] + proc_children(pid):
        try:
            for line in Path(f"/proc/{p}/status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    total += int(line.split()[1]) / 1024
                    break
        except FileNotFoundError:
            pass
    return total


def system_ram_used_mib():
    vals = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        k, v = line.split(":", 1)
        vals[k] = int(v.split()[0])
    return (vals["MemTotal"] - vals.get("MemAvailable", vals["MemFree"])) / 1024


def gpu_mem_mib():
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=1,
        )
        return sum(float(x) for x in out.split())
    except (subprocess.SubprocessError, ValueError):
        return None


def monitor(proc, interval):
    samples = []
    t0 = time.perf_counter()

    def loop():
        while proc.poll() is None:
            samples.append({
                "t_s": time.perf_counter() - t0,
                "process_ram_mib": proc_rss_mib(proc.pid),
                "system_ram_used_mib": system_ram_used_mib(),
                "gpu_mem_mib": gpu_mem_mib(),
            })
            time.sleep(interval)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return samples, thread


def write_memory_csv(path, samples):
    if not samples:
        return ""
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=samples[0].keys())
        writer.writeheader()
        writer.writerows(samples)
    return str(path)


def render_best_pose(run_dir, image_path):
    archive = run_dir / "success_archives" / "individuals_0.npz"
    if not archive.exists():
        return ""

    data = np.load(archive, allow_pickle=True)
    if len(data["infos"]) == 0:
        return ""

    best_i = int(np.argmax(data["fitnesses"]))
    pose = data["infos"][best_i]["final_6dof_pose"]

    with open(run_dir / "config.pkl", "rb") as f:
        cfg = pickle.load(f)

    cfg["env"]["kwargs"]["display"] = False
    env = OBJ_ENV_CLASS(**cfg["env"]["kwargs"])
    try:
        env.reset()
        env.set_6dof_obj_pose(pose)
        view = p.computeViewMatrixFromYawPitchRoll(
            cameraTargetPosition=[0, 0, 0],
            distance=1.0,
            yaw=-35,
            pitch=-35,
            roll=0,
            upAxisIndex=2,
            physicsClientId=env.physics_client_id,
        )
        proj = p.computeProjectionMatrixFOV(
            fov=50,
            aspect=1.0,
            nearVal=0.01,
            farVal=10.0,
        )
        _, _, rgba, _, _ = p.getCameraImage(
            width=640,
            height=640,
            viewMatrix=view,
            projectionMatrix=proj,
            renderer=p.ER_TINY_RENDERER,
            physicsClientId=env.physics_client_id,
        )
        plt.imsave(image_path, np.asarray(rgba).reshape(640, 640, 4))
    finally:
        env.close()

    return str(image_path)


def run_one(args, budget):
    log_path = Path(args.log_path)
    before = set(log_path.glob(f"{args.name}_n{budget}_*"))
    cmd = [
        sys.executable, "run_qd_place.py",
        "-a", args.algorithm,
        "-nbr", str(budget),
        "-p", str(args.population),
        "-o", args.object,
        "-t", args.target,
        "-ii",
        "-ll",
        "-l", str(log_path),
        "-f", f"{args.name}_n{budget}_",
    ]
    env = os.environ.copy()
    env.setdefault("MPLCONFIGDIR", "/tmp/placeit-mpl-cache")
    t0 = time.perf_counter()
    proc = subprocess.Popen(cmd, env=env)
    mem_samples, mem_thread = monitor(proc, args.sample_interval)
    ret = proc.wait()
    wall_time = time.perf_counter() - t0
    mem_thread.join(timeout=args.sample_interval * 2)
    if ret:
        raise subprocess.CalledProcessError(ret, cmd)

    after = set(log_path.glob(f"{args.name}_n{budget}_*"))
    run_dir = max(after - before, key=lambda p: p.stat().st_mtime)
    data = np.load(run_dir / "run_data.npz")
    screenshot_dir = log_path / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    screenshot = render_best_pose(run_dir, screenshot_dir / f"{run_dir.name}.png")
    memory_csv = write_memory_csv(log_path / f"{run_dir.name}_memory.csv", mem_samples)
    gpu_values = [s["gpu_mem_mib"] for s in mem_samples if s["gpu_mem_mib"] is not None]
    return {
        "budget": budget,
        "actual_evals": int(data["n_evals_hist"][-1]),
        "internal_runtime_s": float(data["run_time_hist"][-1]),
        "wall_time_s": wall_time,
        "peak_process_ram_mib": max((s["process_ram_mib"] for s in mem_samples), default=0.0),
        "peak_system_ram_used_mib": max((s["system_ram_used_mib"] for s in mem_samples), default=0.0),
        "peak_gpu_mem_mib": max(gpu_values) if gpu_values else "",
        "successful_cells": int(data["n_successful_cells_list"][-1]),
        "memory_csv": memory_csv,
        "screenshot": screenshot,
        "run_dir": str(run_dir),
    }


def write_montage(rows, path):
    rows_with_images = [r for r in rows if r["screenshot"]]
    if not rows_with_images:
        return

    n = len(rows_with_images)
    fig, axes = plt.subplots(1, n, figsize=(4 * n, 4))
    if n == 1:
        axes = [axes]
    for ax, row in zip(axes, rows_with_images):
        ax.imshow(plt.imread(row["screenshot"]))
        ax.set_title(f'{row["actual_evals"]} evals\n{row["successful_cells"]} successes')
        ax.axis("off")
    plt.tight_layout()
    plt.savefig(path)
    plt.close(fig)


def write_memory_plot(rows, path):
    plotted = False
    fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
    for row in rows:
        if not row["memory_csv"]:
            continue
        data = list(csv.DictReader(open(row["memory_csv"])))
        if not data:
            continue
        t = [float(r["t_s"]) for r in data]
        axes[0].plot(t, [float(r["process_ram_mib"]) for r in data], label=f'{row["actual_evals"]} evals')
        axes[1].plot(t, [float(r["system_ram_used_mib"]) for r in data], label=f'{row["actual_evals"]} evals')
        gpu = [r["gpu_mem_mib"] for r in data]
        if any(g for g in gpu):
            axes[2].plot(t, [float(g) if g else np.nan for g in gpu], label=f'{row["actual_evals"]} evals')
        plotted = True
    if not plotted:
        plt.close(fig)
        return
    axes[0].set_ylabel("process RAM MiB")
    axes[1].set_ylabel("system RAM used MiB")
    axes[2].set_ylabel("GPU mem MiB")
    axes[2].set_xlabel("time (s)")
    for ax in axes:
        handles, _ = ax.get_legend_handles_labels()
        if handles:
            ax.legend()
    plt.tight_layout()
    plt.savefig(path)
    plt.close(fig)


def main():
    args = parse_args()
    rows = [run_one(args, budget) for budget in args.budgets]
    out = Path(args.log_path)
    out.mkdir(parents=True, exist_ok=True)

    csv_path = out / f"{args.name}.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    fig_path = out / f"{args.name}.png"
    plt.plot([r["actual_evals"] for r in rows], [r["internal_runtime_s"] for r in rows], marker="o", label="internal")
    plt.plot([r["actual_evals"] for r in rows], [r["wall_time_s"] for r in rows], marker="o", label="wall")
    plt.xlabel("candidate placements evaluated")
    plt.ylabel("runtime (s)")
    plt.title(f"{args.algorithm}: runtime vs candidate placements")
    plt.legend()
    plt.tight_layout()
    plt.savefig(fig_path)
    plt.close()

    montage_path = out / f"{args.name}_poses.png"
    write_montage(rows, montage_path)
    memory_plot_path = out / f"{args.name}_memory.png"
    write_memory_plot(rows, memory_plot_path)

    print(f"wrote {csv_path}")
    print(f"wrote {fig_path}")
    print(f"wrote {montage_path}")
    print(f"wrote {memory_plot_path}")
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
