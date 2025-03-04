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
import gmsh
import yaml
import logging
from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme
from rich.pretty import pprint


custom_theme = Theme({
    "info": "dim white",
    "warning": "bold yellow",
    "error": "bold red",
    "success": "bold green",
    "h1": "bold underline green",
    "h2": "bold underline white",
})

app = typer.Typer()

FORMAT = "%(message)s"
logging.basicConfig(
    level=logging.WARNING, format=FORMAT, datefmt="[%X]", handlers=[RichHandler()]
)

log = logging.getLogger("mpm_confined_compression")
log.setLevel(logging.INFO)
console = Console(theme=custom_theme)

RATEL_DIR = Path(env['HOME']) / "project" / "micromorph" / "ratel"
RATEL_EXE = RATEL_DIR / "bin" / "ratel-quasistatic"
OPTIONS_FILE = Path(__file__).parent / "Material_Options.yml"
OPTIONS_FILE_MATERIAL_MESH = Path(__file__).parent / "Material_Options_MaterialMesh.yml"
OPTIONS_FILE_VOXEL = Path(__file__).parent / "Material_Options_Voxel.yml"
OPTIONS_FILE_VOXEL_AIR = Path(__file__).parent / "Material_Options_Voxel_Air.yml"
SOLVER_OPTIONS_FILE = Path(__file__).parent / "Ratel_Solver_Options.yml"

DIE_PIXEL_SIZE = 8.434786e-3  # mm/pixel # 8.434786 um/pixel
DIE_RADIUS = 2.550608716  # mm # 2550.608716 um, 5_000 / (8.434786 * 2) + 6 pixels
DIE_HEIGHT = 8.51913386  # mm # 8519.13386 um, 1010 pixels
DIE_CENTER = [2.65695759, 2.65695759, 0]  # [2656.95759, 2656.95759, 0] um, 315, 315, 0 pixels


def get_bounding_box(mesh_file: Path):
    gmsh.initialize()
    gmsh.open(str(mesh_file))
    bbox = gmsh.model.getBoundingBox(-1, -1)
    gmsh.finalize()
    return np.asarray([bbox[0], bbox[1], bbox[2]]), np.asarray([bbox[3], bbox[4], bbox[5]])


class Topology(enum.Enum):
    CYLINDER = "cylinder"
    DIE = "die"
    CUBE = "cube"

    def __repr__(self):
        return self.value

    def __str__(self):
        return self.value


def get_mesh(characteristic_length, topology=Topology.CYLINDER, load_fraction=0.05,
             material_mesh: Path = None, voxel_data: Path = None):
    console.print("[h1]Mesh Generation[/]\n")
    if topology == Topology.CYLINDER:
        return get_cylinder_mesh(characteristic_length, material_mesh=material_mesh)
    elif topology == Topology.DIE:
        args = get_cylinder_mesh(
            characteristic_length,
            radius=DIE_RADIUS,
            height=DIE_HEIGHT,
            center=DIE_CENTER,
            voxel_data=voxel_data)
        args.extend([
            '-mpm_use_voxel',
            '-mpm_voxel_filename', f'{voxel_data.absolute()}',
            '-mpm_voxel_pixel_size', f'{DIE_PIXEL_SIZE}',
            '-mpm_void_characteristic_length', f'{characteristic_length*4}',
        ])
        if load_fraction != 0.5:
            args.extend([
                '-remap_scale', f'{1-load_fraction}',
                '-bc_slip_2_translate', f'0,0,{-load_fraction*DIE_HEIGHT}'
            ])
        return args
    elif topology == Topology.CUBE:
        return get_cube_mesh(characteristic_length)
    else:
        raise ValueError(f"Unknown topology {topology}")


def get_cylinder_mesh(characteristic_length, radius=2534.72400368, height=4420.35076904,
                      center=[0, 0, 0], load_fraction=0.05, material_mesh: Path = None, voxel_data: Path = None):
    if material_mesh is not None:
        if not material_mesh.exists():
            raise FileNotFoundError(f"Material mesh {material_mesh} does not exist")
        mesh_file = Path(__file__).parent / "meshes" / \
            f"cylinder_{material_mesh.stem}_CL{characteristic_length}.msh"
    elif voxel_data is not None:
        if not voxel_data.exists():
            raise FileNotFoundError(f"Voxel data {voxel_data} does not exist")
        mesh_file = Path(__file__).parent / "meshes" / \
            f"cylinder_{voxel_data.stem}_CL{characteristic_length}.msh"
    else:
        mesh_file = Path(__file__).parent / "meshes" / f"cylinder_CL{characteristic_length}.msh"
    if mesh_file.exists() and mesh_file.with_suffix(".yml").exists():
        console.print(f"[info]Using existing mesh [/]{mesh_file}")
        return ["-options_file", f"{mesh_file.with_suffix('.yml')}"]
    (Path(__file__).parent / "meshes").mkdir(exist_ok=True)

    element_order = 1
    if material_mesh is not None:
        bbox_min, bbox_max = get_bounding_box(material_mesh)
        center = (bbox_min + bbox_max) / 2
        center[2] = bbox_min[2]
        radius = (bbox_max[0] - bbox_min[0]) / 2
        height = bbox_max[2] - bbox_min[2]

        console.print(f"[info]Using material mesh [/]{material_mesh}")
        console.print(f"  [info]Bounding box: [/]{bbox_min}[info] to [/]{bbox_max}")

    layers = int(np.ceil(height / characteristic_length))
    console.print(f"[info]Center: [/]{center}")
    console.print(f"[info]Radius: [/]{radius}")
    console.print(f"[info]Height: [/]{height}")
    console.print(f"[info]Number of layers: [/]{layers}")
    console.print(f"[info]Element order: [/]{element_order}")
    console.print(f"[info]Characteristic length: [/]{characteristic_length}")
    SURFACE = 2
    VOLUME = 3
    gmsh.initialize()

    # create cylinder mesh
    disk = gmsh.model.occ.addDisk(center[0], center[1], center[2], radius, radius)

    # Extrude the disk along (0, 0, height) with the specified number of layers.
    # The 'recombine=True' option tells gmsh to recombine triangular faces into quads.
    # The extrude function returns a list of new entities:
    #  - extruded[0]: the top surface,
    #  - extruded[1]: the volume,
    #  - extruded[2]: the lateral (side) surface.
    extruded = gmsh.model.occ.extrude([(SURFACE, disk)], 0, 0, height,
                                      numElements=[layers],
                                      recombine=True)

    # Extract tags from the extrusion result.
    top_surface = extruded[0][1]  # Top surface created by extrusion.
    volume = extruded[1][1]  # The volume.
    lateral_surface = extruded[2][1]  # The lateral surface.

    # Synchronize to update the model with the new entities.
    gmsh.model.occ.synchronize()

    # Force recombination of bottom surface
    gmsh.model.mesh.setRecombine(SURFACE, disk)

    # set mesh options
    gmsh.option.setNumber("Mesh.MeshSizeMin", 0.5)
    gmsh.option.setNumber("Mesh.MeshSizeMax", 1.0)
    gmsh.option.setNumber("Mesh.MeshSizeFactor", characteristic_length)
    gmsh.option.setNumber("Mesh.ElementOrder", element_order)
    gmsh.option.setNumber("Mesh.HighOrderOptimize", 1 if element_order > 1 else 0)

    # set physical groups
    gmsh.model.addPhysicalGroup(SURFACE, [disk], 1)
    gmsh.model.setPhysicalName(SURFACE, 1, "bottom")
    gmsh.model.addPhysicalGroup(SURFACE, [top_surface], 2)
    gmsh.model.setPhysicalName(SURFACE, 2, "top")
    gmsh.model.addPhysicalGroup(SURFACE, [lateral_surface], 3)
    gmsh.model.setPhysicalName(SURFACE, 3, "outside")
    gmsh.model.addPhysicalGroup(VOLUME, [volume], 1)
    gmsh.model.setPhysicalName(VOLUME, 1, "cylinder")

    # generate mesh
    gmsh.model.mesh.generate(3)

    # save mesh
    gmsh.write(str(mesh_file))
    gmsh.finalize()

    console.print(f"[info]Mesh saved to [/]{mesh_file}")

    options = {
        "dm_plex": {
            "filename": f"{mesh_file.absolute()}",
            "dim": 3,
            "simplex": 0,
        },
        "bc": {
            "slip": "1,2,3",
            "slip_1_components": "0,1,2",
            "slip_2": {
                "components": "0,1,2",
                "translate": f"0,0,{-0.05 * height}",
            },
            "slip_3_components": "0,1",
        },
        "remap": {
            "direction": "z",
            "scale": 0.95,
        },
    }
    if material_mesh is not None:
        options["mpm_material_mesh_dm_plex_filename"] = f"{material_mesh.absolute()}"
    console.print(f"[info]Generated mesh options:[/]")
    pprint(options, expand_all=True)

    with open(mesh_file.with_suffix(".yml"), "w") as f:
        yaml.dump(options, f, default_flow_style=False)

    return ["-options_file", f"{mesh_file.with_suffix('.yml').absolute()}"]


def get_cube_mesh(characteristic_length):
    max_side_length = characteristic_length
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
def run(characteristic_length: Annotated[float, typer.Argument(min=0)], topology: Topology, ratel_path: Annotated[Path, typer.Argument(envvar='RATEL_DIR')], out: Annotated[Path, typer.Option()] = None, n: Annotated[int, typer.Option(
        min=1)] = 1, dry_run: bool = False, ceed: str = '/cpu/self', additional_args: str = "", material_mesh: Path = None, voxel_data: Path = None, load_fraction: Annotated[float, typer.Option(min=0, max=1)] = 0.05, use_air: bool = False) -> None:
    if topology == Topology.DIE and voxel_data is None:
        raise typer.Abort("Voxel data is required for die topology")
    console.print(f"\n[h1]RATEL MPM CONFINED COMPRESSION[/]")
    console.print(f"\n[h2]Mesh Options[/]")
    console.print(f"  • Characteristic length: {characteristic_length}")
    console.print(f"  • Topology: {str(topology)}")
    if material_mesh is not None:
        console.print(f"  • Material mesh: {material_mesh}")
    if voxel_data is not None:
        console.print(f"  • Voxel data: {voxel_data}")
    console.print(f"\n[h2]Simulation Options[/]")
    console.print(f"  • Ratel path: {ratel_path}")
    console.print(f"  • Output directory: {out}")
    console.print(f"  • Number of processes: {n}")
    console.print(f"  • Ceed backend: {ceed}")
    if additional_args:
        console.print(f"  • Additional arguments: {additional_args}")
    console.print("")

    if out is None:
        out = Path.cwd() / \
            f"MPM-{topology.value}-CL{int(characteristic_length):03}-{datetime.datetime.now().strftime(r'%Y-%m-%d_%H-%M-%S')}"
    if out.exists():
        for file in out.glob("*"):
            file.unlink()
        out.rmdir()
    out.mkdir()

    mesh_options = get_mesh(
        characteristic_length,
        topology,
        material_mesh=material_mesh,
        voxel_data=voxel_data,
        load_fraction=load_fraction)
    local_solver_options = out / SOLVER_OPTIONS_FILE.name
    local_options = out / OPTIONS_FILE.name
    shutil.copy(SOLVER_OPTIONS_FILE, local_solver_options)
    if topology == Topology.DIE:
        if use_air:
            shutil.copy(OPTIONS_FILE_VOXEL_AIR, local_options)
            additional_args += f" -mpm_void_characteristic_length {4*characteristic_length}"
        else:
            shutil.copy(OPTIONS_FILE_VOXEL, local_options)
    elif material_mesh is not None:
        shutil.copy(OPTIONS_FILE_MATERIAL_MESH, local_options)
    else:
        shutil.copy(OPTIONS_FILE, local_options)

    pre = "mpm_" if (material_mesh or voxel_data) else ""
    options = [
        "-options_file", f"{local_solver_options}",
        "-options_file", f"{local_options}",
        "-ceed", f"{ceed}",
        f"-{pre}binder_characteristic_length", f"{4*characteristic_length}",
        f"-{pre}grains_characteristic_length", f"{4*characteristic_length}",
        *mesh_options,
        "-ts_monitor_diagnostic_quantities", f"cgns:{out}/diagnostic_%06d.cgns",
        "-ts_monitor_solution", f"cgns:{out}/solution_%06d.cgns",
        "-ts_monitor_surface_force_per_face", f"ascii:{out}/forces.csv",
        "-ts_monitor_strain_energy", f"ascii:{out}/strain_energy.csv",
        "-ts_monitor_swarm", f"ascii:{out.absolute()}/swarm.xmf",
        *additional_args.split()
    ]
    out_file = out / "stdout.txt"
    err_file = out / "stderr.txt"
    ratel_exe = ratel_path / 'bin' / 'ratel-quasistatic'
    cmd_arr = ["mpirun", "-np", f"{n}", f"{ratel_exe}", *options] if n > 1 else [f"{ratel_exe}", *options]

    console.print(f"\n[h1]Running experiment[/]\n")
    console.print(f"[info]Running:\n  > [/]{' '.join(cmd_arr)}")

    if dry_run:
        console.print("[success]Dry run, exiting[/]")
        return
    try:
        with out_file.open("wb") as out_f, err_file.open("wb") as err_f:
            proc = subprocess.run(cmd_arr, stdout=out_f, stderr=err_f)
    except subprocess.CalledProcessError as e:
        console.print(f"[error]Error: process returned {e.returncode}[/]")
        console.print(e.stderr.decode())
        raise typer.Exit(code=e.returncode)

    if proc.returncode != 0:
        console.print(f"[error]Error: process returned {proc.returncode}[/]")
        console.print(err_file.read_text())
        raise typer.Exit(code=proc.returncode)

    console.print(f"[success]Experiment completed successfully.[/]")


SCRIPT_PATH = Path(__file__).parent / 'flux_scripts'

CORES_PER_SLOT = 24
GPUS_PER_NODE = 4


@app.command()
def flux_run(characteristic_length: Annotated[float, typer.Argument(min=1)], topology: Topology, ratel_path: Annotated[Path, typer.Argument(envvar='RATEL_DIR')], n: int = 1,
             dry_run: bool = False, ceed: str = '/gpu/hip/gen', additional_args: str = "", material_mesh: Path = None, voxel_data: Path = None, load_fraction: Annotated[float, typer.Option(min=0, max=1)] = 0.05, use_air: bool = False) -> None:
    scratch_dir = f"/p/lustre5/{os.environ['USER']}/ratel"
    Path(scratch_dir).mkdir(parents=True, exist_ok=True)
    if topology == Topology.DIE and voxel_data is None:
        raise typer.Abort("Voxel data is required for die topology")
    console.print(f"\n[h1]RATEL MPM CONFINED COMPRESSION -- FLUX[/]")
    console.print(f"\n[h2]Mesh Options[/]")
    console.print(f"  • Characteristic length: {characteristic_length}")
    console.print(f"  • Topology: {str(topology)}")
    if material_mesh is not None:
        console.print(f"  • Material mesh: {material_mesh}")
    if voxel_data is not None:
        console.print(f"  • Voxel data: {voxel_data}")
    console.print(f"\n[h2]Simulation Options[/]")
    console.print(f"  • Ratel path: {ratel_path}")
    console.print(f"  • Scratch directory: {scratch_dir}")
    console.print(f"  • Number of processes: {n}")
    console.print(f"  • Ceed backend: {ceed}")
    if additional_args:
        console.print(f"  • Additional arguments: {additional_args}")
    console.print("")

    mesh_options = get_mesh(
        characteristic_length,
        topology,
        material_mesh=material_mesh,
        voxel_data=voxel_data,
        load_fraction=load_fraction)
    pre = "mpm_" if (material_mesh or voxel_data) else ""

    command = f"{ratel_path / 'bin' / 'ratel-quasistatic'} {' '.join(options)}"
    num_nodes = int(np.ceil(n / GPUS_PER_NODE))

    SCRIPT_PATH.mkdir(exist_ok=True)

    if topology == Topology.DIE:
        if use_air:
            options_file = OPTIONS_FILE_VOXEL_AIR
            additional_args += f" -mpm_void_characteristic_length {4*characteristic_length}"
        else:
            options_file = OPTIONS_FILE_VOXEL
    elif material_mesh is not None:
        options_file = OPTIONS_FILE_MATERIAL_MESH
    else:
        options_file = OPTIONS_FILE

    options = [
        "-options_file", f"$SCRATCH/Ratel_Solver_Options.yml",
        "-options_file", f"$SCRATCH/Material_Options.yml",
        "-ceed", f"{ceed}",
        f"-{pre}binder_characteristic_length", f"{4*characteristic_length}",
        f"-{pre}grains_characteristic_length", f"{4*characteristic_length}",
        *mesh_options,
        "-ts_monitor_diagnostic_quantities", f"cgns:$SCRATCH/diagnostic_%06d.cgns",
        "-ts_monitor_surface_force_per_face", f"ascii:$SCRATCH/forces.csv",
        "-ts_monitor_strain_energy", f"ascii:$SCRATCH/strain_energy.csv",
        "-ts_monitor_swarm", f"ascii:$SCRATCH/swarm.xmf",
        *additional_args.split()
    ]

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
            'ml +rocmcc/6.3.0-cce-18.0.1d-magic',
            'ml +rocm/6.3.0',
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
            f'cp $INPUT_DIRECTORY/{options_file.name} $SCRATCH/Material_Options.yml',
            'cp $INPUT_DIRECTORY/Ratel_Solver_Options.yml $SCRATCH',
            'mkdir $SCRATCH/meshes',
            f'cp $INPUT_DIRECTORY/{mesh_options[1]} $SCRATCH/{mesh_options[1]}' if topology != Topology.CUBE else '',
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

    command = ["flux", "batch", "-N", f"{num_nodes}", "-n", f"{n}", '-x', "-g", "1", f"{script_file}"]
    console.print(f"Submitting job with command: {' '.join(command)}")
    if dry_run:
        console.print("[success]Dry run, exiting[/]")
        return
    proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        console.print(f"[error]Return code {proc.returncode}: {proc.stderr.decode()}[/]")
    else:
        console.print(f"[success]Job submitted with ID {proc.stdout.decode()}[/]")
    script_file.unlink()


if __name__ == "__main__":
    app()
