#!/usr/bin/env python3

import typer
import enum
from pathlib import Path
import subprocess
from os import environ as env
from typing_extensions import Annotated
import numpy as np
import datetime
import shutil
import tempfile
import os

app = typer.Typer()

RATEL_DIR = Path(env['HOME']) / "project" / "micromorph" / "ratel"
RATEL_EXE = RATEL_DIR / "bin" / "ratel-quasistatic"
OPTIONS_FILE = Path(__file__).parent / "Material_Options.yml"
SOLVER_OPTIONS_FILE = Path(__file__).parent / "Ratel_Solver_Options.yml"


class Topology(enum.Enum):
    CYLINDER = "cylinder"
    CUBE = "cube"


def get_mesh(characteristic_length, topology=Topology.CYLINDER, height_scale: float = 1):
    if topology == Topology.CYLINDER:
        return get_cylinder_mesh(characteristic_length, height_scale)
    elif topology == Topology.CUBE:
        return get_cube_mesh(characteristic_length, height_scale)
    else:
        raise ValueError(f"Unknown topology {topology}")


def get_cylinder_mesh(characteristic_length, height_scale: float = 1):
    if height_scale != 1:
        mesh_file = Path(__file__).parent / "meshes" / \
            f"cylinder_height{height_scale}_CL{int(characteristic_length):03}.msh"
    else:
        mesh_file = Path(__file__).parent / "meshes" / f"cylinder_CL{int(characteristic_length):03}.msh"
    if mesh_file.exists():
        return ["-dm_plex_filename", f"{mesh_file}"]
    (Path(__file__).parent / "meshes").mkdir(exist_ok=True)
    cmd = [
        "gmsh",
        "-3",
        "-setnumber",
        "cl",
        f"{characteristic_length}e-3",
        "-setnumber",
        "height_scale",
        f"{height_scale}",
        "cylinder.geo",
        "-o",
        f"{mesh_file}",
    ]
    typer.secho(f"Running:\n  > {' '.join(cmd)}", fg=typer.colors.BRIGHT_BLACK)
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return ["-dm_plex_filename", f"{mesh_file}"]


def get_cube_mesh(characteristic_length):
    max_side_length = 1e-3 * characteristic_length
    num_sides = int(np.ceil(4.4203 / max_side_length))
    options = [
        "-dm_plex_box_upper", "5.0684,5.0684,4.4203",
        "-dm_plex_box_faces", f"{num_sides},{num_sides},{num_sides}",
        "-bc_slip", "1,2,3,4,5,6",
        "-bc_slip_3_components", "1",
        "-bc_slip_4_components", "1",
        "-bc_slip_5_components", "0",
        "-bc_slip_6_components", "0",
    ]
    return options


@app.command()
def run(characteristic_length: Annotated[float, typer.Argument(min=1)], topology: Topology, ratel_path: Annotated[Path, typer.Argument(envvar='RATEL_DIR')], out: Annotated[Path, typer.Option()] = None, n: Annotated[int, typer.Option(
        min=1)] = 1, height_scale: float = 1, dry_run: bool = False, ceed: str = '/cpu/self', additional_args: str = "") -> None:
    typer.secho(f"Running experiment with mesh characteristic length {characteristic_length}", fg=typer.colors.GREEN)
    if out is None:
        out = Path.cwd() / \
            f"MPM-{topology.value}-CL{int(characteristic_length):03}-{datetime.datetime.now().strftime(r'%Y-%m-%d_%H-%M-%S')}"
    if out.exists():
        for file in out.glob("*"):
            file.unlink()
        out.rmdir()
    out.mkdir()

    mesh_options = get_mesh(characteristic_length, topology, height_scale)
    local_solver_options = out / SOLVER_OPTIONS_FILE.name
    local_options = out / OPTIONS_FILE.name
    shutil.copy(SOLVER_OPTIONS_FILE, local_solver_options)
    shutil.copy(OPTIONS_FILE, local_options)

    options = [
        "-options_file", f"{local_options}",
        "-options_file", f"{local_solver_options}",
        "-ceed", f"{ceed}",
        "-binder_characteristic_length", f"{4*characteristic_length*1e-3}",
        "-grains_characteristic_length", f"{4*characteristic_length*1e-3}",
        *mesh_options,
        "-ts_monitor_diagnostic_quantities", f"cgns:{out}/diagnostic_%06d.cgns",
        "-ts_monitor_surface_force_per_face", f"ascii:{out}/forces.csv",
        "-ts_monitor_strain_energy", f"ascii:{out}/strain_energy.csv",
        "-ts_monitor_swarm", f"ascii:{out.absolute()}/swarm.xmf",
        "-bc_slip_2_translate", f"0,0,{-0.221015*height_scale}",
        * additional_args.split()
    ]
    out_file = out / "stdout.txt"
    err_file = out / "stderr.txt"
    ratel_exe = ratel_path / 'bin' / 'ratel-quasistatic'
    cmd_arr = ["mpirun", "-np", f"{n}", f"{ratel_exe}", *options] if n > 1 else [f"{ratel_exe}", *options]
    typer.secho(f"Running:\n  > {' '.join(cmd_arr)}", fg=typer.colors.BRIGHT_BLACK)

    if dry_run:
        typer.secho("Dry run, exiting", fg=typer.colors.YELLOW)
        return
    try:
        with out_file.open("wb") as out_f, err_file.open("wb") as err_f:
            proc = subprocess.run(cmd_arr, stdout=out_f, stderr=err_f)
    except subprocess.CalledProcessError as e:
        typer.secho(f"Error: process returned {e.returncode}", fg=typer.colors.RED)
        typer.echo(e.stderr.decode())
        raise typer.Exit(code=e.returncode)

    if proc.returncode != 0:
        typer.secho(f"Error: process returned {proc.returncode}", fg=typer.colors.RED)
        typer.echo(err_file.read_text())
        raise typer.Exit(code=proc.returncode)

    typer.secho(f"Experiment with mesh characteristic length {characteristic_length}", fg=typer.colors.GREEN)


SCRIPT_PATH = Path(__file__).parent / 'flux_scripts'

CORES_PER_SLOT = 24
GPUS_PER_NODE = 4


@app.command()
def flux_run(characteristic_length: Annotated[float, typer.Argument(min=1)], topology: Topology, ratel_path: Annotated[Path, typer.Argument(envvar='RATEL_DIR')], height_scale: float = 1, n: int = 1,
             dry_run: bool = False, ceed: str = '/gpu/hip/gen', additional_args: str = ""):

    typer.secho(
        f"Using Flux to run experiment with mesh characteristic length {characteristic_length}",
        fg=typer.colors.GREEN)

    scratch_dir = f"/p/lustre5/{os.environ['USER']}/ratel"
    Path(scratch_dir).mkdir(parents=True, exist_ok=True)

    mesh_options = get_mesh(characteristic_length, topology, height_scale)
    options = [
        "-options_file", f"$SCRATCH/Material_Options.yml",
        "-options_file", f"$SCRATCH/Ratel_Solver_Options.yml",
        "-ceed", f"{ceed}",
        "-binder_characteristic_length", f"{4*characteristic_length*1e-3}",
        "-grains_characteristic_length", f"{4*characteristic_length*1e-3}",
        *mesh_options,
        "-ts_monitor_diagnostic_quantities", f"cgns:$SCRATCH/diagnostic_%06d.cgns",
        "-ts_monitor_surface_force_per_face", f"ascii:$SCRATCH/forces.csv",
        "-ts_monitor_strain_energy", f"ascii:$SCRATCH/strain_energy.csv",
        "-ts_monitor_swarm", f"ascii:$SCRATCH/swarm.xmf",
        "-bc_slip_2_translate", f"0,0,{-0.221015*height_scale}",
        *additional_args.split()
    ]

    command = f"{ratel_path / 'bin' / 'ratel-quasistatic'} {' '.join(options)}"
    num_nodes = int(np.ceil(n / GPUS_PER_NODE))

    if not SCRIPT_PATH.exists():
        SCRIPT_PATH.mkdir()

    script_file = None
    with tempfile.NamedTemporaryFile(mode='w', dir=SCRIPT_PATH, delete=False) as f:
        script_file = Path(f.name)
        f.write('\n'.join([
            '#!/bin/bash',
            '',
            f'#flux: -N {num_nodes}',
            f'#flux: -n {n}',
            '#flux: -g 1',
            '#flux: -x',
            '#flux: -t 24h',
            '#flux: -q pbatch',
            '#flux: --output=output_{{id}}.txt',
            f'#flux: --job-name=ratel_mpm_{topology.value}_CL{int(characteristic_length):03}',
            '#flux: -B guests',
            '#flux: --setattr=thp=always # Transparent Huge Pages',
            '#flux: -l # Add task rank prefixes to each line of output.',
            '',
            f'export INPUT_DIRECTORY={Path(__file__).parent}',
            '',
            'echo "~~~~~~~~~~~~~~~~~~~"',
            'echo "Welcome!"',
            'echo "~~~~~~~~~~~~~~~~~~~"',
            'echo ""',
            'echo "-->Loading modules"',
            'echo ""',
            '',
            'module reset',
            'ml +rocmcc/6.1.2-cce-18.0.0-magic',
            'ml +rocm/6.1.2',
            'ml +craype-accel-amd-gfx942',
            'ml +cray-python',
            'ml +cray-libsci_acc',
            'ml +cray-hdf5-parallel/1.14.3.3',
            'ml +flux_wrappers',
            'module list',
            '',
            'echo ""',
            'echo "-->Job information"',
            'echo "Job ID = $CENTER_JOB_ID"',
            'echo "Flux Resources = $(flux resource info)"',
            '',
            'export HSA_XNACK=1',
            'export MPICH_GPU_SUPPORT_ENABLED=1',
            '',
            f'export SCRATCH={scratch_dir}/MPM-{topology.value}-CL{int(characteristic_length):03}-$CENTER_JOB_ID',
            'echo ""',
            'echo "Scratch = $SCRATCH"',
            'echo ""',
            '',
            'mkdir -p $SCRATCH',
            f'ln -s $SCRATCH $INPUT_DIRECTORY',
            '',
            'echo ""',
            'echo "-->Moving into scratch directory"',
            'echo ""',
            'cd $SCRATCH',
            'cp $INPUT_DIRECTORY/Material_Options.yml $SCRATCH',
            'cp $INPUT_DIRECTORY/Ratel_Solver_Options.yml $SCRATCH',
            'mkdir $SCRATCH/meshes',
            f'cp $INPUT_DIRECTORY/{mesh_options[1]} $SCRATCH/{mesh_options[1]}' if topology == Topology.CYLINDER else '',
            f'',
            'echo ""',
            'echo "-->Starting simulation at $(date)"',
            'echo ""',
            '',
            f'flux run -N{num_nodes} -n{n} --gpus-per-task=1 --verbose --exclusive --setopt=mpibind=verbose:1 \\',
            f'  {command} > $SCRATCH/run.log 2>&1',
            '',
            'echo ""',
            'echo "-->Simulation finished at $(date)"',
            'echo ""',
            '',
            'echo "~~~~~~~~~~~~~~~~~~~"',
            'echo "All done! Bye!"',
            'echo "~~~~~~~~~~~~~~~~~~~"',
        ]))

    typer.secho(f"Submitting job with command: {command}")
    command = ["flux", "batch", "-N", f"{num_nodes}", "-n", f"{n}", '-x', "-g", "1", f"{script_file}"]
    proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        typer.secho(f"Return code {proc.returncode}: {proc.stderr.decode()}", fg=typer.colors.RED)
    else:
        typer.secho(f"Job submitted with ID {proc.stdout.decode()}", fg=typer.colors.GREEN)
    script_file.unlink()


if __name__ == "__main__":
    app()
