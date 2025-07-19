# This module is responsible for running experiments locally.
from pathlib import Path
from rich import print
import subprocess
import datetime
from typing import Optional

from ..helper import config
from ..helper.experiment import ExperimentConfig


def run(experiment: ExperimentConfig, num_processes: int = 1, ratel_dir: Optional[Path] = None,
        out: Optional[Path] = None, scratch_dir: Optional[Path] = None, dry_run: bool = False):
    """Run the experiment locally."""
    # Resolve paths
    if ratel_dir is None:
        ratel_dir = Path(config.get_fallback('RATEL_DIR')).resolve()
    if scratch_dir is None:
        scratch_dir = Path(config.get_fallback('SCRATCH_DIR')).resolve()
    output_dir = Path(config.get_fallback('OUTPUT_DIR', Path.cwd() / 'output')).resolve()
    scratch_dir = Path(config.get_fallback('SCRATCH_DIR', scratch_dir)).resolve()
    if out is not None:
        run_dir = scratch_dir / 'output' / out
    else:
        run_dir = scratch_dir / 'output' / f"{experiment.name}-{datetime.datetime.now().strftime(r'%Y-%m-%d_%H-%M-%S')}"
    run_dir = run_dir.resolve()
    print(f'{experiment}')
    print("")
    print(f"[h2]Simulation Options[/]")
    print(f"  • Ratel path: {ratel_dir}")
    print(f"  • Output directory: {output_dir}")
    print(f"  • Run directory: {run_dir}")
    print(f"  • Number of processes: {num_processes}")
    print("")

    if run_dir.exists():
        for file in run_dir.glob("*"):
            file.unlink()
        run_dir.rmdir()
    run_dir.mkdir(parents=True, exist_ok=True)
    output_link = output_dir / run_dir.name
    if output_link.exists():
        output_link.unlink()
    output_link.symlink_to(run_dir, True)

    config_file = experiment.write_config(run_dir)
    out_file = run_dir / "stdout.txt"
    err_file = run_dir / "stderr.txt"
    ratel_exe = ratel_dir / 'bin' / 'ratel-quasistatic'

    options = [
        "-options_file", f"{config_file.resolve()}",
    ]

    if num_processes > 1:
        cmd_arr = ["mpirun", "-np", f"{num_processes}", f"{ratel_exe}", *options]
    else:
        cmd_arr = [f"{ratel_exe}", *options]
    print(f"\n[h1]Running experiment[/]\n")
    print(f"[info]Running:\n  > [/]{' '.join(cmd_arr)}")

    if dry_run:
        print("[success]Dry run, exiting[/]")
        return

    if not dry_run:
        with out_file.open('wb') as outfile, err_file.open('wb') as err:
            subprocess.run(cmd_arr, cwd=run_dir.resolve(), stdout=outfile, stderr=err)
    else:
        print(f"Command: {' '.join(cmd_arr)}")
