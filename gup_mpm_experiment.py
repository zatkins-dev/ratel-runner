import typer
import enum
from pathlib import Path
import subprocess
from os import environ as env
from typing_extensions import Annotated
import matplotlib.pyplot as plt
import cycler
from cmcrameri import cm
import numpy as np
import pandas as pd
from dataclasses import dataclass
import datetime
import shutil

app = typer.Typer()

plt.rcParams["text.usetex"] = True
plt.rcParams["font.family"] = "serif"
plt.rcParams[
    "text.latex.preamble"
] = r"""
\usepackage[T1]{fontenc}
\usepackage{newpxtext,newpxmath}
\usepackage{amsmath}
\usepackage{bm}
"""

base_scale = 1.5

marker_cycler: cycler.Cycler = plt.cycler('marker', 25 * ['o', 's', '+', 'x'])
markersize_cycler: cycler.Cycler = plt.cycler(
    'markersize', 25 * [3.5 * base_scale, 3 * base_scale, 5 * base_scale, 4 * base_scale])
linestyle_cycler: cycler.Cycler = plt.cycler('linestyle',
                                             20 * [(0, (1, 1)), '-', (0, (5, 1, 1, 1)), '--', (0, (3, 1, 1, 1, 1, 1))]
                                             )

default_cycler: cycler.Cycler = plt.cycler('color', cm.batlowS.colors) + marker_cycler + markersize_cycler
plt.rcParams['axes.prop_cycle'] = default_cycler
plt.rcParams['lines.linewidth'] = 1 * base_scale
plt.rcParams["font.size"] = 16
# plt.rcParams["font.size"] = 10

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
        mesh_file = Path("meshes") / f"cylinder_height{height_scale}_CL{int(characteristic_length):03}.msh"
    else:
        mesh_file = Path("meshes") / f"cylinder_CL{int(characteristic_length):03}.msh"
    if mesh_file.exists():
        return ["-dm_plex_filename", f"{mesh_file}"]
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

# def make_filename(name: str, sample: SampleType, kappa: float, sym: bool, name_extra: str = ""):
#     sym_text = "-sym" if sym else ""
#     return f"{name}_{sample}-{kappa}{sym_text}{name_extra}"


# def load_experiment_data(sample: SampleType, kappa: float, sym: bool = False, name_extra: str = ""):
#     data_path = Path.cwd() / f"{make_filename('forces', sample, kappa, sym, name_extra)}_5.csv"
#     if not data_path.exists():
#         typer.secho(f"Data for {sample} and kappa {kappa} not found", fg=typer.colors.RED)
#         raise typer.Exit(code=1)
#     data = pd.read_csv(data_path)
#     if sym:
#         data['displacement'] = (data['centroid_x'] - data['centroid_x'][0])
#         data['force'] = -data['force_x']
#     else:
#         data['displacement'] = data['centroid_x'] - data['centroid_x'][0]
#         data['force'] = -data['force_x']
#     return data


# @app.command()
# def plot(sample: Annotated[list[SampleType], typer.Option("-s")], kappa: Annotated[list[float], typer.Option("-k")],
#          out: Annotated[Path, typer.Option()] = None, show: bool = False, sym: bool = False, name_extra: str = "") -> None:
#     fig, ax = plt.subplots(figsize=(9.352, 5))
#     for s, k in zip(sample, kappa):
#         data = load_abaqus_data(s, k, sym)
#         ax.plot(data['displacement'], data['force'], label=fr"Abaqus, {s.abrev()}, $\kappa={k}$", markevery=0.025)

#         data = load_experiment_data(s, k, sym, name_extra)
#         ax.plot(data['displacement'], data['force'], label=fr"Ratel, {s.abrev()}, $\kappa={k}$", markevery=0.025)

#         # data = load_reference_data(s, k)
#         # ax.plot(
#         #     data['displacement'],
#         #     data['force'],
#         #     label=fr"Gasser et al., {s.abrev()}, $\kappa={k}$",
#         #     markevery=0.025)

#     ax.set_xlabel(r"Displacement $u$ [mm]")
#     ax.set_ylabel(r"Force $f$ [N]")
#     ax.legend()
#     ax.grid()
#     fig.tight_layout()
#     if out is not None:
#         fig.savefig(out)
#     if show:
#         plt.show()


@app.command()
def run(characteristic_length: Annotated[float, typer.Argument(min=1)], topology: Topology, out: Annotated[Path, typer.Option()] = None, np: Annotated[int, typer.Option(
        min=1)] = 1, height_scale: float = 1, dry_run: bool = False, ceed: str = '/cpu/self', additional_args: str = "", sym: bool = False, name_extra: str = "") -> None:
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
        "-binder_characteristic_length", f"{2*characteristic_length*1e-3}",
        "-grains_characteristic_length", f"{2*characteristic_length*1e-3}",
        *mesh_options,
        "-ts_monitor_diagnostic_quantities", f"cgns:{out}/diagnostic_%06d.cgns",
        "-ts_monitor_surface_force_per_face", f"ascii:{out}/forces.csv",
        "-ts_monitor_strain_energy", f"ascii:{out}/strain_energy.csv",
        "-ts_monitor_swarm", f"ascii:{out}/swarm.xmf",
        "-bc_slip_2_translate", f"0,0,{-0.221015*height_scale}",
        * additional_args.split()
    ]
    out_file = out / "stdout.txt"
    err_file = out / "stderr.txt"

    cmd_arr = ["mpirun", "-np", f"{np}", f"{RATEL_EXE}", *options] if np > 1 else [f"{RATEL_EXE}", *options]
    typer.secho(f"Running:\n  > {' '.join(cmd_arr)}", fg=typer.colors.BRIGHT_BLACK)

    if dry_run:
        typer.secho("Dry run, exiting", fg=typer.colors.YELLOW)
        return
    try:
        with out_file.open("wb") as out_f, err_file.open("wb") as err_f:
            if (np > 1):
                proc = subprocess.run(["mpirun", "-np", f"{np}", f"{RATEL_EXE}",
                                      *options], stdout=out_f, stderr=err_f)
            else:
                proc = subprocess.run([f"{RATEL_EXE}", *options], stdout=out_f, stderr=err_f)
    except subprocess.CalledProcessError as e:
        typer.secho(f"Error: process returned {e.returncode}", fg=typer.colors.RED)
        typer.echo(e.stderr.decode())
        raise typer.Exit(code=e.returncode)

    if proc.returncode != 0:
        typer.secho(f"Error: process returned {proc.returncode}", fg=typer.colors.RED)
        typer.echo(err_file.read_text())
        raise typer.Exit(code=proc.returncode)

    typer.secho(f"Experiment with mesh characteristic length {characteristic_length}", fg=typer.colors.GREEN)


if __name__ == "__main__":
    app()
