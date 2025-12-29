from pathlib import Path
import rich
from rich.syntax import Syntax
from multiprocessing import cpu_count
from enum import Enum
import gmsh
import numpy as np
import typer
from typing import Annotated, Optional, ClassVar
from abc import ABC, abstractmethod
from types import SimpleNamespace
import pandas as pd
import math

from ...helper.experiment import ExperimentConfig, LogViewType
from ...helper import config
from ...helper.flux import flux, machines
from ...helper.utilities import run_once, callback_is_set

from .. import local
from ..sweep import load_sweep_specification

from .press_boundary import BoundaryType, PressBoundary


console = rich.get_console()
print = console.print


class MaterialType(Enum):
    DAMAGE = "damage"
    NEO_HOOKEAN = "neo_hookean"
    MONOCLINIC = "monoclinic"
    TRICLINIC = "triclinic"


@run_once
def register_keys():
    keys = {
        'VOXEL_SIZE': config.ConfigKey('VOXEL_SIZE', 'Side length for each voxel', float),
        'LOAD_FRACTION': config.ConfigKey('LOAD_FRACTION', 'Desired Final height/Initial height ratio', float, config.CheckBounded(0, 1)),
        'VOXEL_DATA': config.ConfigKey('VOXEL_DATA', 'Path to voxel data file', Path),
        'CHARACTERISTIC_LENGTH': config.ConfigKey('CHARACTERISTIC_LENGTH', 'Desired characteristic length of background mesh', float),
        'GRAIN_IDS': config.ConfigKey('GRAIN_IDS', 'Range-based list of IDs corresponding to different grains', str),
    }
    for name, key in keys.items():
        config.add_key(name, key)


register_keys()

DIE_PIXEL_SIZE_IP01 = 8.434786e-3  # mm/pixel # 8.434786 um/pixel
# DIE_RADIUS = 2.550608716  # mm # 2550.608716 um, 5_000 / (8.434786 * 2) + 6 pixels
# DIE_HEIGHT = 8.51913386  # mm # 8519.13386 um, 1010 pixels
# DIE_CENTER = [2.65695759, 2.65695759, 0]  # [2656.95759, 2656.95759, 0] um, 315, 315, 0 pixels


def compute_die_stats(voxel_data, voxel_size: float, buf: int):
    with open(voxel_data) as f:
        line = f.readline()
    _, nx, ny, nz = map(int, line.split())
    radius = (5.000 / (voxel_size * 2) + buf) * voxel_size
    height = nz * voxel_size
    center = [nx / 2 * voxel_size, ny / 2 * voxel_size, 0]
    return radius, height, center


def set_diagnostic_options(experiment: ExperimentConfig, save_forces: int, save_strain_energy: int, save_swarm: int, save_solution: int,
                           save_diagnostics: int, save: bool) -> None:
    """
    Set diagnostic options for the experiment.

    :param experiment: The experiment configuration object.
    :param save_forces: Whether to save forces.
    :param save_swarm: Whether to save swarm data.
    :param save_solution: Whether to save solution data.
    :param save_diagnostics: Whether to save diagnostics.
    :param save_all: Whether to save all data.
    """
    if not save:
        return
    if save_forces > 0:
        experiment.diagnostic_options["ts_monitor_surface_force_per_face"] = "ascii:forces.csv"
        experiment.diagnostic_options["ts_monitor_surface_force_per_face_interval"] = f"{save_forces}"
    if save_strain_energy > 0:
        experiment.diagnostic_options["ts_monitor_strain_energy"] = "ascii:strain_energy.csv"
        experiment.diagnostic_options["ts_monitor_strain_energy_interval"] = f"{save_strain_energy}"
    if save_swarm > 0:
        experiment.diagnostic_options["ts_monitor_swarm_solution"] = "ascii:swarm.xmf"
        experiment.diagnostic_options["ts_monitor_swarm_fields"] = "J,volume,rho,material,model state,elastic parameters"
        experiment.diagnostic_options["ts_monitor_swarm_solution_interval"] = f"{save_swarm}"
    if save_solution > 0:
        experiment.diagnostic_options["ts_monitor_solution"] = r"cgns:solution_%06d.cgns"
        experiment.diagnostic_options["ts_monitor_solution_interval"] = f"{save_solution}"
    if save_diagnostics > 0:
        experiment.diagnostic_options["ts_monitor_output_fields"] = r"cgns:output_fields_%06d.cgns"
        experiment.diagnostic_options["ts_monitor_output_fields_interval"] = f"{save_diagnostics}"


def generate_mesh(characteristic_length: float, voxel_data: Path,
                  voxel_size: float, voxel_buf: int, scratch_dir: Path) -> Path:
    mesh_dir = scratch_dir / "meshes"
    if not mesh_dir.exists():
        mesh_dir.mkdir(parents=True, exist_ok=True)
    if not voxel_data.exists():
        raise FileNotFoundError(f"Voxel data {voxel_data} does not exist")
    mesh_file = mesh_dir / f"cylinder_{voxel_data.stem}_CL{characteristic_length}.cgns"
    if mesh_file.exists():
        console.print(f"[info]Using existing mesh [/]{mesh_file}")
        return mesh_file.resolve()

    element_order = 1
    radius, height, center = compute_die_stats(voxel_data, voxel_size, voxel_buf)
    square_radius = radius * np.sqrt(0.125)

    layers = int(np.ceil(height / characteristic_length) + 1)
    print(f"[info]Voxel Size: [/]{voxel_size}")
    print(f"[info]Center: [/]{center}")
    print(f"[info]Radius: [/]{radius}")
    print(f"[info]Height: [/]{height}")
    print(f"[info]Number of layers: [/]{layers}")
    print(f"[info]Element order: [/]{element_order}")
    print(f"[info]Characteristic length: [/]{characteristic_length}")

    EDGE = 1
    SURFACE = 2
    VOLUME = 3

    inner_rad = radius - 0.5 * square_radius * (1 + np.sqrt(2))
    outer_rad = radius - square_radius
    avg_rad = 0.5 * (inner_rad + outer_rad)
    NPTS_SQUARE = int(np.ceil(0.5 / characteristic_length * (square_radius + np.pi / 4 * radius))) + 1
    NPTS_RADIAL = int(np.ceil(avg_rad / characteristic_length)) + 1

    gmsh.initialize()

    # set mesh options
    gmsh.option.setNumber("General.NumThreads", cpu_count())
    gmsh.option.setNumber("Mesh.Algorithm3D", 10)
    gmsh.option.setNumber("Mesh.ElementOrder", element_order)
    gmsh.option.setNumber("Mesh.HighOrderOptimize", 1 if element_order > 1 else 0)
    gmsh.option.setNumber("Mesh.Binary", 1)

    p1 = gmsh.model.geo.addPoint(*center)
    p2 = gmsh.model.geo.addPoint(*(center + np.array([square_radius, 0, 0])))
    offset = (0.5 + 0.5 / np.sqrt(2))
    p3 = gmsh.model.geo.addPoint(*(center + np.array([square_radius * offset, square_radius * offset, 0])))
    p4 = gmsh.model.geo.addPoint(*(center + np.array([0, square_radius, 0])))

    p5 = gmsh.model.geo.addPoint(*(center + np.array([radius, 0, 0])))
    p6 = gmsh.model.geo.addPoint(*(center + np.array([radius / np.sqrt(2), radius / np.sqrt(2), 0])))
    p7 = gmsh.model.geo.addPoint(*(center + np.array([0, radius, 0])))

    l1 = gmsh.model.geo.addLine(p1, p2)
    l2 = gmsh.model.geo.addLine(p2, p3)
    l3 = gmsh.model.geo.addLine(p3, p4)
    l4 = gmsh.model.geo.addLine(p4, p1)

    l5 = gmsh.model.geo.addLine(p2, p5)
    l6 = gmsh.model.geo.addCircleArc(p5, p1, p6)
    l7 = gmsh.model.geo.addLine(p6, p3)
    l8 = gmsh.model.geo.addCircleArc(p6, p1, p7)
    l9 = gmsh.model.geo.addLine(p7, p4)

    cl1 = gmsh.model.geo.addCurveLoop((l1, l2, l3, l4))
    cl2 = gmsh.model.geo.addCurveLoop((l5, l6, l7, -l2))
    cl3 = gmsh.model.geo.addCurveLoop((l9, -l3, -l7, l8))

    s1 = gmsh.model.geo.addPlaneSurface([cl1])
    s2 = gmsh.model.geo.addPlaneSurface([cl2])
    s3 = gmsh.model.geo.addPlaneSurface([cl3])

    for c in [l5, l7, l9]:
        gmsh.model.geo.mesh.setTransfiniteCurve(c, NPTS_RADIAL)
    for c in [l1, l2, l3, l4, l6, l8]:
        gmsh.model.geo.mesh.setTransfiniteCurve(c, NPTS_SQUARE)
    for s in [s1, s2, s3]:
        gmsh.model.geo.mesh.setTransfiniteSurface(s)
        gmsh.model.geo.mesh.setRecombine(SURFACE, s)

    gmsh.model.geo.synchronize()

    def add_quadrant(orig, angle):
        quadrant = gmsh.model.geo.copy(orig)
        lines = [id for dim, id in quadrant if dim == EDGE]
        for l in lines:
            if l - lines[0] + 1 in [l5, l7, l9]:
                gmsh.model.geo.mesh.setTransfiniteCurve(l, NPTS_RADIAL)
            else:
                gmsh.model.geo.mesh.setTransfiniteCurve(l, NPTS_SQUARE)
        for s in filter(lambda x: x[0] == SURFACE, quadrant):
            gmsh.model.geo.mesh.setTransfiniteSurface(s[1])
            gmsh.model.geo.mesh.setRecombine(s[0], s[1])
        gmsh.model.geo.rotate(quadrant, center[0], center[1], center[2], 0, 0, 1, angle)
        return list(set(gmsh.model.getEntities()).intersection(quadrant))

    quadrant1 = gmsh.model.getEntities()
    add_quadrant(quadrant1, np.pi / 2)
    add_quadrant(quadrant1, np.pi)
    add_quadrant(quadrant1, 3 * np.pi / 2)

    gmsh.model.geo.removeAllDuplicates()
    gmsh.model.geo.synchronize()

    disk = gmsh.model.getEntities(SURFACE)

    # Extrude the disk along (0, 0, height) with the specified number of layers.
    # The 'recombine=True' option tells gmsh to recombine triangular faces into quads.
    gmsh.model.geo.extrude(disk, 0, 0, height, [layers], recombine=True)

    # Synchronize to update the model with the new entities.
    gmsh.model.geo.synchronize()

    print('About to generate mesh')

    # generate mesh
    gmsh.model.mesh.generate(3)

    node_tags, coords, parametric_coords = gmsh.model.mesh.getNodes()
    types, tags, nodes = gmsh.model.mesh.getElements(VOLUME)
    gmsh.finalize()

    gmsh.initialize()
    v1 = gmsh.model.addDiscreteEntity(VOLUME)
    gmsh.model.mesh.addNodes(VOLUME, v1, node_tags, coords, parametric_coords)
    gmsh.model.mesh.addElements(VOLUME, v1, types, tags, nodes)
    # save mesh
    gmsh.write(str(mesh_file))
    gmsh.finalize()

    if not mesh_file.exists():
        raise RuntimeError(f"Failed to generate mesh file: {mesh_file}")

    print(f"[info]Mesh saved to [/]{mesh_file}")
    return mesh_file


class PressExperiment(ExperimentConfig, ABC):
    """Die press experiment using voxelized CT data and a synthetic mesh, using sticky air for voids"""
    @property
    @abstractmethod
    def solver_config(self) -> str:
        pass

    @property
    @abstractmethod
    def material_config(self) -> str:
        pass

    base_name: ClassVar[str]

    def __init__(
            self,
            voxel_data: Path,
            characteristic_length: float,
            voxel_size: float,
            voxel_buf: int,
            load_fraction: float,
            boundary: PressBoundary,
            material: MaterialType,
            seed: Optional[int],
            base_name: str | None = None,
            pretty_name: str | None = None,
            description: str | None = None,
    ):
        if not voxel_data.exists():
            raise FileNotFoundError(f"Voxel data {voxel_data} does not exist")
        if characteristic_length <= 0:
            raise ValueError(f"characteristic_length must be greater than 0, got {characteristic_length:f}")
        if load_fraction <= 0.0 or load_fraction > 1.0:
            raise ValueError(f"load_fraction must be in (0.0, 1.0], got {load_fraction}")
        self.voxel_data: Path = voxel_data
        self.characteristic_length: float = characteristic_length
        self.load_fraction: float = load_fraction
        self.boundary: PressBoundary = boundary
        self.scratch_dir: Path = Path(config.get_fallback('SCRATCH_DIR')).resolve()
        self.voxel_size: float = voxel_size
        self.voxel_buf: int = voxel_buf
        self.material: MaterialType = material
        self.seed: int = seed or np.random.SeedSequence().generate_state(1)[0]
        self.radius, self.height, self.center = compute_die_stats(self.voxel_data, self.voxel_size, self.voxel_buf)
        base_config = self.solver_config + '\n' + self.boundary.snes_options + '\n' + self.material_config + '\n'
        base_config += f'mpm_grains_label_value: {config.get_fallback("GRAIN_IDS", "2")}\n'
        name = f"{base_name}-{voxel_data.stem}-{material.value}-CL{characteristic_length}-LF{load_fraction}-{self.boundary.name}"
        pretty_name = pretty_name or "Ratel iMPM Press Experiment"
        description = description or self.__doc__
        super().__init__(name=name, pretty_name=pretty_name, description=description, base_config=base_config)

    def get_mesh(self) -> str:
        """
        Get a mesh file for the given voxel data and characteristic length, generating if necessary.

        :param characteristic_length: The desired characteristic length for the mesh.
        :param voxel_data: Path to the voxel data file (e.g., CT scan).
        :param scratch_dir: Directory to store the generated mesh file.
        :param load_fraction: Fraction of the load to apply to the die (default is 0.4).
        :param voxel_size: Size of each voxel in the voxel data
        :param voxel_buf: Number of buffer voxels to add to the mesh
        :param bc_type: Type of boundary condition to apply.

        :return: A dictionary of mesh options for the experiment configuration.
        """
        mesh_file: Path = generate_mesh(
            self.characteristic_length,
            self.voxel_data,
            self.voxel_size,
            self.voxel_buf,
            self.scratch_dir
        )

        options: str = '\n'.join([
            "",
            "# Mesh options generated by press_common.generate_mesh",
            "mpm_voxel:",
            f"  filename: {self.voxel_data.resolve()}",
            f"  pixel_size: {self.voxel_size}",
            "",
            "dm_plex:",
            f"  filename: {mesh_file.resolve()}",
            "  cgns_parallel:",
            "  box_label:",
            "  dim: 3",
            "  simplex: 0",
            "",
            "remap:",
            f"  direction: z",
            f"  scale: {(1 - self.load_fraction)} # (1 - load_fraction) to match displacement",
            "",
        ])
        options += self.boundary.options(self.center, self.radius, self.height, self.load_fraction)

        print(f"[info]Generated mesh options:[/]")
        syntax = Syntax(options, "yaml")
        print(syntax)
        return options

    @property
    def mesh_options(self) -> str:
        if hasattr(self, '_mesh_options'):
            return getattr(self, '_mesh_options')
        options = self.get_mesh()
        setattr(self, '_mesh_options', options)
        return options

    def __str__(self) -> str:
        output = '\n'.join([
            f'[h1]{self.pretty_name}[/]',
            f'{self.description}',
            f"\n[h2]Mesh Options[/]",
            f"  • Characteristic length: {self.characteristic_length}",
            f"  • Voxel data: {self.voxel_data}",
            f"  • Voxel size: {self.voxel_size}",
            f"  • Die Geometry:",
            f"    • Radius: {self.radius}",
            f"    • Height: {self.height}",
            f"    • Center: {self.center}",
            f"  • Load fraction: {self.load_fraction}",
            f"  • Final Height: {self.height * self.load_fraction}",
            f"  • Boundary Condition: {self.boundary}",
        ])
        if self.user_options:
            output += "\n[h2]User Options[/]\n"
            output += "\n".join([f"  • {key}: {value}" for key, value in self.user_options.items()])
        return output

    @classmethod
    def create_options_callback(cls):
        def options_callback(
            ctx: typer.Context,
            voxel_data: Annotated[Path, typer.Option('--voxel-data', '--data', default_factory=lambda: config.get("VOXEL_DATA"), callback=callback_is_set, help="Path to voxel dump file")],
            characteristic_length: Annotated[float, typer.Option(
                '--characteristic-length', '--cl', min=0, max=6, default_factory=lambda: config.get("CHARACTERISTIC_LENGTH"), callback=callback_is_set, help="Characteristic length of background mesh"
            )],
            voxel_size: Annotated[float, typer.Option('--voxel-size', '--size', default_factory=lambda: config.get("VOXEL_SIZE"), callback=callback_is_set, help="Voxel side length, should be constant for a given voxel dump file")],
            material: Annotated[MaterialType, typer.Option('--material', help="Material model to use")],
            load_fraction: Annotated[float, typer.Option(
                '--load-fraction', '--lf', min=0.0, max=1.0, help="Percent of total cylinder height to compress"
            )] = float(config.get_fallback("LOAD_FRACTION", 0.4)),
            voxel_buffer: Annotated[int, typer.Option(help="Number of buffer voxel widths to add to the mesh")] = 0,
            bc_type: Annotated[BoundaryType, typer.Option('--bc', '--boundary', '--bc-type',
                                                          help="Type of boundary condition to apply")] = BoundaryType.CLAMPED,
            friction_coefficient: Annotated[float, typer.Option('--mu', '--friction-coefficient', min=0.0,
                                                                help="Kinetic friction coefficient, only for contact BCs")] = 0.5,
            seed: Annotated[Optional[int], typer.Option(
                help="Random seed for any stochastic components, mainly for anisotropic materials")] = None,
            machine: Annotated[Optional[machines.Machine], typer.Option(
                help="HPC machine to generate flux scripts for")] = None,
            num_processes: Annotated[int, typer.Option("-n", min=1, help="Number of MPI processes")] = 1,
            log_view: Annotated[Optional[LogViewType], typer.Option(help="Type of log view profiling to use")] = None,
            save_forces: Annotated[int, typer.Option(
                min=0, help="Interval to save surface forces, or 0 to disable")] = 1,
            save_strain_energy: Annotated[int, typer.Option(
                min=0, help="Interval to save strain energy, or 0 to disable")] = 1,
            save_swarm: Annotated[int, typer.Option(min=0, help="Interval to save swarm data, or 0 to disable")] = 0,
            save_solution: Annotated[int, typer.Option(
                min=0, help="Interval to save mesh solution, or 0 to disable")] = 0,
            save_diagnostics: Annotated[int, typer.Option(
                min=0, help="Interval to save projected diagnostic quantities, or zero to disable")] = 0,
            save: Annotated[bool, typer.Option(
                help="Global flag to enable or disable writing diagnostics. If False, nothing will be written")] = True,
            checkpoint: Annotated[int, typer.Option(
                min=0, help="Interval to save checkpoint files for restarting runs, or zero to disable")] = 0,
            max_time: Annotated[Optional[str], typer.Option(
                "-t", "--max-time", help="Flux time specification for max job length.")] = None,
            max_restarts: Annotated[int, typer.Option(help="Number of restart jobs to enqueue", min=0)] = 0,
            dry_run: Annotated[bool, typer.Option(help="If true, only generate scripts and exit")] = False,
            yes: Annotated[bool, typer.Option('-y', help="Automatically accept any confirmation prompts")] = False,
        ):
            """Common options for press experiments

            Args:
                ctx (typer.Context): Typer application context
                voxel_data (Path, optional): Path to voxel dump file.
                characteristic_length (float, optional): Characteristic length of background mesh.
                voxel_size (float, optional): Voxel side length, should be constant for a given voxel dump file.
                material (MaterialType, optional): Material model to use.
                load_fraction (float, optional): Percent of total cylinder height to compress.
                voxel_buffer (int, optional): Number of buffer voxel widths to add to the mesh.
                bc_type (BoundaryType, optional): Type of boundary condition to apply.
                friction_coefficient (float, optional): Kinetic friction coefficient, only for contact BCs.
                machine (machines.Machine, optional): HPC machine to generate flux scripts for.
                num_processes (int, optional): Number of MPI processes.
                log_view (LogViewType, optional): Type of log view profiling to use.
                save_forces (int, optional): Interval to save surface forces, or 0 to disable.
                save_strain_energy (int, optional): Interval to save strain energy, or 0 to disable.
                save_swarm (int, optional): Interval to save swarm data, or 0 to disable.
                save_solution (int, optional): Interval to save mesh solution, or 0 to disable.
                save_diagnostics (int, optional): Interval to save projected diagnostic quantities, or zero to disable.
                save (bool, optional): Global flag to enable or disable writing diagnostics. If False, nothing will be written.
                checkpoint (int, optional): Interval to save checkpoint files for restarting runs, or zero to disable.
                max_time (str, optional): Flux time specification for max job length.
                max_restarts(int, optional): Number of restart jobs to enqueue.
                dry_run (bool, optional): If true, only generate scripts and exit.
                yes (bool, optional): Automatically accept any confirmation prompts.
            """
            if not ctx.obj:
                ctx.obj = SimpleNamespace()
            context = ctx.obj
            boundary = PressBoundary.create(bc_type, friction_coefficient=friction_coefficient)
            context.experiment = cls(
                voxel_data,
                characteristic_length,
                voxel_size,
                voxel_buf=voxel_buffer,
                load_fraction=load_fraction,
                boundary=boundary,
                material=material,
                seed=seed,
            )
            context.experiment.logview = log_view
            set_diagnostic_options(
                context.experiment,
                save_forces=save_forces,
                save_strain_energy=save_strain_energy,
                save_swarm=save_swarm,
                save_solution=save_solution,
                save_diagnostics=save_diagnostics,
                save=save,
            )
            context.machine = machine if machine is not None else machines.detect_machine()
            context.num_processes = num_processes
            context.checkpoint = checkpoint
            context.max_time = max_time
            context.max_restarts = max_restarts
            context.dry_run = dry_run
            context.yes = yes
        return options_callback

    @classmethod
    def create_app(cls):
        app = typer.Typer(name=cls.base_name, callback=cls.create_options_callback(), help=cls.__doc__)

        @app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
        def run(
            ctx: typer.Context,
            out: Optional[Path] = None,
        ):
            """Run the experiment in the current shell (blocking)

            Hint: See `ratel-runner mpm press [EXPERIMENT] --help` for all options
            """
            ctx.obj.experiment.user_options = ctx.args
            local.run(
                ctx.obj.experiment,
                num_processes=ctx.obj.num_processes,
                out=out,
                dry_run=ctx.obj.dry_run
            )

        @app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
        def flux_run(
            ctx: typer.Context,
        ):
            """Run the experiment using the Flux job scheduler

            Hint: See `ratel-runner mpm press [EXPERIMENT] --help` for all options
            """
            ctx.obj.experiment.user_options = ctx.args
            if ctx.obj.dry_run:
                script_file, _ = flux.generate(
                    ctx.obj.experiment,
                    machine=ctx.obj.machine,
                    num_processes=ctx.obj.num_processes,
                    max_time=ctx.obj.max_time,
                    checkpoint_interval=ctx.obj.checkpoint,
                )
                print(f"Generated script saved to", script_file)
                print("Dry run, exiting.")
            else:
                flux.submit_series(
                    ctx.obj.experiment,
                    machine=ctx.obj.machine,
                    num_processes=ctx.obj.num_processes,
                    max_time=ctx.obj.max_time,
                    checkpoint_interval=ctx.obj.checkpoint,
                    max_restarts=ctx.obj.max_restarts
                )

        @app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
        def flux_sweep(
            ctx: typer.Context,
            sweep_spec: Path,
        ):
            """Run a parameter sweep using the Flux job scheduler.

            Hint: See `ratel-runner mpm press [EXPERIMENT] --help` for all options
            """
            ctx.obj.experiment.user_options = ctx.args
            sweep_params = load_sweep_specification(ctx, sweep_spec, quiet=True)
            flux.sweep(
                ctx.obj.experiment,
                machine=ctx.obj.machine,
                num_processes=ctx.obj.num_processes,
                max_time=ctx.obj.max_time,
                parameters=sweep_params,
                sweep_name=sweep_spec.stem,
                yes=ctx.obj.yes,
                dry_run=ctx.obj.dry_run
            )

        @app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
        def flux_uq(
            ctx: typer.Context,
            uq_spec: Path,
        ):
            """Run a parameter sweep using the Flux job scheduler."""
            ctx.obj.experiment.user_options = ctx.args
            uq_params = pd.read_csv(uq_spec).to_dict(orient='list')
            flux.uq(
                ctx.obj.experiment,
                machine=ctx.obj.machine,
                num_processes=ctx.obj.num_processes,
                max_time=ctx.obj.max_time,
                parameters=uq_params,
                sweep_name=uq_spec.stem,
                yes=ctx.obj.yes,
                dry_run=ctx.obj.dry_run
            )

        @app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
        def flux_strong_scaling(
            ctx: typer.Context,
            num_processes: Annotated[list[int], typer.Argument(min=1)],
            num_steps: Annotated[int, typer.Option(min=1, help="Number of time steps to run")] = 20,
            num_samples: Annotated[int, typer.Option(min=1, help="Number of runs at each process count")] = 1,
            output_name: Annotated[Optional[Path], typer.Option(help="Directory to save results")] = None,
            args: Annotated[Optional[list[str]], typer.Option('-a',
                                                              help="Additional arguments to pass to the experiment")] = None,
        ):
            """Run a parameter sweep using the Flux job scheduler.

            Hint: See `ratel-runner mpm press [EXPERIMENT] --help` for all options
            """
            output_dir = Path(config.get_fallback('OUTPUT_DIR', Path.cwd() / 'output'))
            if output_name is not None:
                output_dir = output_dir / output_name
            ctx.obj.experiment._name = ctx.obj.experiment._name + "-scaling"
            base_name = ctx.obj.experiment._name
            ctx.obj.experiment.user_options = ctx.args + [
                "--preload",
                "--ts_max_steps", f"{num_steps}"
            ] + (args if args else [])

            max_length = int(math.ceil(math.log10(max(num_processes) + 1)))
            for np in num_processes:
                for sample in range(num_samples):
                    np_str = f"{np}".zfill(max_length)
                    ctx.obj.experiment._name = base_name + f"-np{np_str}" + (f"-s{sample+1}" if num_samples > 1 else "")
                    script_file, _ = flux.generate(
                        ctx.obj.experiment,
                        machine=ctx.obj.machine,
                        num_processes=np,
                        max_time=ctx.obj.max_time,
                        output_dir=output_dir,
                    )
                    if ctx.obj.dry_run:
                        print(f"Generated script saved to", script_file)
                        print("Dry run, exiting.")
                    else:
                        flux.run(script_file)
        return app
