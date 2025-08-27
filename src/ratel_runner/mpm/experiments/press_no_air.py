from pathlib import Path
import importlib.resources
import typer
from typing import Optional, Annotated
import pandas as pd

from ...helper.experiment import ExperimentConfig, LogViewType
from ...helper.flux import flux, machines
from ...helper import config

from .press_common import get_mesh, DIE_HEIGHT, set_diagnostic_options
from ..sweep import load_sweep_specification
from .. import local


_material_config_file = importlib.resources.files(__package__ or '') / 'yml' / 'press_no_air.yml'
_solver_config_file = importlib.resources.files(__package__ or '') / 'yml' / 'common_solver.yml'


class PressNoAirExperiment(ExperimentConfig):
    """Die press experiment using voxelized CT data and a synthetic mesh"""

    def __init__(self, voxel_data: Path, characteristic_length: float,
                 load_fraction: float = 0.4, clamp_top: bool = True):
        if not voxel_data.exists():
            raise FileNotFoundError(f"Voxel data {voxel_data} does not exist")
        if characteristic_length <= 0:
            raise ValueError(f"characteristic_length must be greater than 0, got {characteristic_length:f}")
        elif characteristic_length > DIE_HEIGHT / 4:
            raise ValueError(f"characteristic_length is extremely large, maybe you meant {characteristic_length:f}e-3?")
        if load_fraction <= 0.0 or load_fraction > 1.0:
            raise ValueError(f"load_fraction must be in (0.0, 1.0], got {load_fraction}")
        self.voxel_data: Path = voxel_data
        self.characteristic_length: float = characteristic_length
        self.load_fraction: float = load_fraction
        self.clamp_top: bool = clamp_top
        self.scratch_dir: Path = Path(config.get_fallback('SCRATCH_DIR')).resolve()
        base_config = _solver_config_file.read_text() + '\n' + _material_config_file.read_text()
        base_name = Path(__file__).stem.replace('_', '-')
        name = f"{base_name}-CL{characteristic_length}-LF{load_fraction}{'-clamped' if clamp_top else ''}"
        super().__init__(name, self.__doc__, base_config)

    @property
    def mesh_options(self) -> str:
        options = get_mesh(
            self.characteristic_length,
            self.voxel_data,
            self.scratch_dir,
            load_fraction=self.load_fraction,
            clamp_top=self.clamp_top
        )
        options += '\n' + '\n'.join([
            "# Specific options for no air die experiment",
            f"mpm_grains_characteristic_length: {self.characteristic_length * 4}",
            f"mpm_binder_characteristic_length: {self.characteristic_length * 4}",
            "",
        ])
        return options

    def __str__(self) -> str:
        output = '\n'.join([
            f'[h1]Ratel iMPM Press Experiment, no air[/]',
            f'{self.description}',
            f"\n[h2]Mesh Options[/]",
            f"  • Characteristic length: {self.characteristic_length}",
            f"  • Voxel data: {self.voxel_data}",
        ])
        if self.user_options:
            output += "\n[h2]User Options[/]\n"
            output += "\n".join([f"  • {key}: {value}" for key, value in self.user_options.items()])
        return output


__doc__ = PressNoAirExperiment.__doc__

app = typer.Typer()


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)
def run(
    ctx: typer.Context,
    voxel_data: Path,
    characteristic_length: Annotated[float, typer.Argument(min=0, max=DIE_HEIGHT / 4)],
    load_fraction: Annotated[float, typer.Argument(min=0.0, max=1.0)] = 0.4,
    clamp_top: bool = True,
    num_processes: Annotated[int, typer.Option("-n", min=1)] = 1,
    log_view: Optional[LogViewType] = None,
    save_forces: Annotated[int, typer.Option(help="Interval to save surface forces, or zero to disable", min=0)] = 1,
    save_strain_energy: Annotated[int, typer.Option(
        help="Interval to save strain energy, or zero to disable", min=0)] = 1,
    save_swarm: Annotated[int, typer.Option(help="Interval to save swarm data, or zero to disable", min=0)] = 200,
    save_solution: Annotated[int, typer.Option(
        help="Interval to save projected solution, or zero to disable", min=0)] = 200,
    save_diagnostics: Annotated[int, typer.Option(
        help="Interval to save projected diagnostic quantities, or zero to disable", min=0)] = 200,
    save: Annotated[bool, typer.Option(
        help="Global flag to enable or disable writing diagnostics. If False, nothing will be written.")] = True,
    checkpoint: Annotated[int, typer.Option(
        help="Interval to save checkpoint files for restarting runs, or zero to disable", min=0)] = 20,
    out: Optional[Path] = None,
    dry_run: bool = False
):
    """Run the experiment in the current shell (blocking)"""
    experiment = PressNoAirExperiment(
        voxel_data,
        characteristic_length,
        load_fraction=load_fraction,
        clamp_top=clamp_top,
    )
    experiment.user_options = ctx.args
    experiment.logview = log_view
    set_diagnostic_options(
        experiment,
        save_forces=save_forces,
        save_strain_energy=save_strain_energy,
        save_swarm=save_swarm,
        save_solution=save_solution,
        save_diagnostics=save_diagnostics,
        save=save,
    )
    local.run(
        experiment,
        num_processes=num_processes,
        out=out,
        dry_run=dry_run
    )


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)
def flux_run(
    ctx: typer.Context,
    voxel_data: Path,
    characteristic_length: Annotated[float, typer.Argument(min=0, max=DIE_HEIGHT / 4)],
    load_fraction: Annotated[float, typer.Argument(min=0.0, max=1.0)] = 0.4,
    clamp_top: bool = True,
    num_processes: Annotated[int, typer.Option("-n", min=1)] = 1,
    max_time: Annotated[Optional[str], typer.Option("-t", "--max-time")] = None,
    log_view: Optional[LogViewType] = None,
    machine: Optional[machines.Machine] = None,
    save_forces: Annotated[int, typer.Option(help="Interval to save surface forces, or zero to disable", min=0)] = 1,
    save_strain_energy: Annotated[int, typer.Option(
        help="Interval to save strain energy, or zero to disable", min=0)] = 1,
    save_swarm: Annotated[int, typer.Option(help="Interval to save swarm data, or zero to disable", min=0)] = 200,
    save_solution: Annotated[int, typer.Option(
        help="Interval to save projected solution, or zero to disable", min=0)] = 200,
    save_diagnostics: Annotated[int, typer.Option(
        help="Interval to save projected diagnostic quantities, or zero to disable", min=0)] = 200,
    save: Annotated[bool, typer.Option(
        help="Global flag to enable or disable writing diagnostics. If False, nothing will be written.")] = True,
    checkpoint: Annotated[int, typer.Option(
        help="Interval to save checkpoint files for restarting runs, or zero to disable", min=0)] = 20,
    max_restarts: Annotated[int, typer.Option(help="Number of restart jobs to enqueue", min=0)] = 0,
    dry_run: bool = False
):
    """Run the experiment using the Flux job scheduler"""
    experiment = PressNoAirExperiment(
        voxel_data,
        characteristic_length,
        load_fraction=load_fraction,
        clamp_top=clamp_top,
    )
    experiment.user_options = ctx.args
    experiment.logview = log_view
    set_diagnostic_options(
        experiment,
        save_forces=save_forces,
        save_strain_energy=save_strain_energy,
        save_swarm=save_swarm,
        save_solution=save_solution,
        save_diagnostics=save_diagnostics,
        save=save,
    )
    if dry_run:
        script_file, _ = flux.generate(
            experiment,
            machine=machine,
            num_processes=num_processes,
            max_time=max_time,
            checkpoint_interval=checkpoint,
        )
        print(f"Generated script saved to", script_file)
        print("Dry run, exiting.")
    else:
        flux.submit_series(
            experiment,
            machine=machine,
            num_processes=num_processes,
            max_time=max_time,
            checkpoint_interval=checkpoint,
            max_restarts=max_restarts
        )


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)
def flux_sweep(
    ctx: typer.Context,
    sweep_spec: Path,
    voxel_data: Path,
    characteristic_length: Annotated[float, typer.Argument(min=0, max=DIE_HEIGHT / 4)],
    load_fraction: Annotated[float, typer.Argument(min=0.0, max=1.0)] = 0.4,
    clamp_top: bool = True,
    num_processes: Annotated[int, typer.Option("-n", min=1)] = 1,
    max_time: Annotated[Optional[str], typer.Option("-t", "--max-time")] = None,
    log_view: Optional[LogViewType] = None,
    machine: Optional[machines.Machine] = None,
    save_forces: Annotated[int, typer.Option(help="Interval to save surface forces, or zero to disable", min=0)] = 1,
    save_strain_energy: Annotated[int, typer.Option(
        help="Interval to save strain energy, or zero to disable", min=0)] = 1,
    save_swarm: Annotated[int, typer.Option(help="Interval to save swarm data, or zero to disable", min=0)] = 200,
    save_solution: Annotated[int, typer.Option(
        help="Interval to save projected solution, or zero to disable", min=0)] = 200,
    save_diagnostics: Annotated[int, typer.Option(
        help="Interval to save projected diagnostic quantities, or zero to disable", min=0)] = 200,
    save: Annotated[bool, typer.Option(
        help="Global flag to enable or disable writing diagnostics. If False, nothing will be written.")] = True,
    checkpoint: Annotated[int, typer.Option(
        help="Interval to save checkpoint files for restarting runs, or zero to disable", min=0)] = 20,
    max_restarts: Annotated[int, typer.Option(help="Number of restart jobs to enqueue", min=0)] = 0,
    yes: Annotated[bool, typer.Option('-y')] = False,
    dry_run: bool = False,
):
    """Run a parameter sweep using the Flux job scheduler."""
    experiment = PressNoAirExperiment(
        voxel_data,
        characteristic_length,
        load_fraction=load_fraction,
        clamp_top=clamp_top,
    )
    sweep_params = load_sweep_specification(ctx, sweep_spec, quiet=True)
    experiment.user_options = ctx.args
    experiment.logview = log_view
    set_diagnostic_options(
        experiment,
        save_forces=save_forces,
        save_strain_energy=save_strain_energy,
        save_swarm=save_swarm,
        save_solution=save_solution,
        save_diagnostics=save_diagnostics,
        save=save,
    )
    flux.sweep(
        experiment,
        machine=machine,
        num_processes=num_processes,
        max_time=max_time,
        parameters=sweep_params,
        sweep_name=sweep_spec.stem,
        yes=yes,
        dry_run=dry_run
    )


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)
def flux_uq(
    ctx: typer.Context,
    uq_spec: Path,
    voxel_data: Path,
    characteristic_length: Annotated[float, typer.Argument(min=0, max=DIE_HEIGHT / 4)],
    load_fraction: Annotated[float, typer.Argument(min=0.0, max=1.0)] = 0.4,
    clamp_top: bool = True,
    num_processes: Annotated[int, typer.Option("-n", min=1)] = 1,
    max_time: Annotated[Optional[str], typer.Option("-t", "--max-time")] = None,
    log_view: Optional[LogViewType] = None,
    machine: Optional[machines.Machine] = None,
    save_forces: Annotated[int, typer.Option(help="Interval to save surface forces, or zero to disable", min=0)] = 1,
    save_strain_energy: Annotated[int, typer.Option(
        help="Interval to save strain energy, or zero to disable", min=0)] = 1,
    save_swarm: Annotated[int, typer.Option(help="Interval to save swarm data, or zero to disable", min=0)] = 200,
    save_solution: Annotated[int, typer.Option(
        help="Interval to save projected solution, or zero to disable", min=0)] = 200,
    save_diagnostics: Annotated[int, typer.Option(
        help="Interval to save projected diagnostic quantities, or zero to disable", min=0)] = 200,
    save: Annotated[bool, typer.Option(
        help="Global flag to enable or disable writing diagnostics. If False, nothing will be written.")] = True,
    checkpoint: Annotated[int, typer.Option(
        help="Interval to save checkpoint files for restarting runs, or zero to disable", min=0)] = 20,
    max_restarts: Annotated[int, typer.Option(help="Number of restart jobs to enqueue", min=0)] = 0,
    yes: Annotated[bool, typer.Option('-y')] = False,
    dry_run: bool = False,
):
    """Run a parameter sweep using the Flux job scheduler."""
    experiment = PressNoAirExperiment(
        voxel_data,
        characteristic_length,
        load_fraction=load_fraction,
        clamp_top=clamp_top,
    )
    uq_params = pd.read_csv(uq_spec).to_dict(orient='list')
    experiment.user_options = ctx.args
    experiment.logview = log_view
    set_diagnostic_options(
        experiment,
        save_forces=save_forces,
        save_strain_energy=save_strain_energy,
        save_swarm=save_swarm,
        save_solution=save_solution,
        save_diagnostics=save_diagnostics,
        save=save,
    )
    flux.uq(
        experiment,
        machine=machine,
        num_processes=num_processes,
        max_time=max_time,
        parameters=uq_params,
        sweep_name=uq_spec.stem,
        yes=yes,
        dry_run=dry_run
    )


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)
def flux_strong_scaling(
    ctx: typer.Context,
    voxel_data: Path,
    characteristic_length: Annotated[float, typer.Argument(min=0, max=DIE_HEIGHT / 4)],
    load_fraction: Annotated[float, typer.Argument(min=0.0, max=1.0)] = 0.4,
    clamp_top: bool = True,
    num_processes: Annotated[list[int], typer.Option("-n", min=1)] = list([1]),
    max_time: Annotated[Optional[str], typer.Option("-t", "--max-time")] = None,
    num_steps: int = 5,
    log_view: Optional[LogViewType] = LogViewType.TEXT,
    machine: Optional[machines.Machine] = None,
    dry_run: bool = False,
):
    """Run a parameter sweep using the Flux job scheduler."""
    experiment = PressNoAirExperiment(
        voxel_data,
        characteristic_length,
        load_fraction=load_fraction,
        clamp_top=clamp_top,
    )
    experiment._name = experiment._name + "-scaling"
    experiment.user_options = ctx.args + [
        "--preload",
        "--ts_max_steps", f"{num_steps}"
    ]
    experiment.logview = log_view
    set_diagnostic_options(
        experiment,
        save_forces=0,
        save_strain_energy=0,
        save_swarm=0,
        save_solution=0,
        save_diagnostics=0,
        save=False,
    )
    for np in num_processes:
        if dry_run:
            script_file, _ = flux.generate(
                experiment,
                machine=machine,
                num_processes=np,
                max_time=max_time,
            )
            print(f"Generated script saved to", script_file)
            print("Dry run, exiting.")
        else:
            flux.submit_series(
                experiment,
                machine=machine,
                num_processes=np,
                max_time=max_time,
            )
