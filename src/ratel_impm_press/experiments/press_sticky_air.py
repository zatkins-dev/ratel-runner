from pathlib import Path
import importlib.resources
import typer
from typing import Optional, Annotated
import datetime
import subprocess
from rich import print

from .press_common import get_mesh, DIE_HEIGHT
from ..experiment import ExperimentConfig
from ..flux import flux, machines
from .. import local
from .. import config


__doc__ = "Die press experiment using voxelized CT data and a synthetic mesh, using sticky air for voids"
_material_config_file = importlib.resources.files('ratel_impm_press') / 'yml' / 'Material_Options_Voxel_Air.yml'
_solver_config_file = importlib.resources.files('ratel_impm_press') / 'yml' / 'Ratel_Solver_Options.yml'


class PressStickyAirExperiment(ExperimentConfig):
    def __init__(self, voxel_data: Path, characteristic_length: float,
                 load_fraction: float = 0.4, scratch_dir: Path = None):
        if not voxel_data.exists():
            raise FileNotFoundError(f"Voxel data {voxel_data} does not exist")
        if characteristic_length <= 0:
            raise ValueError(f"characteristic_length must be greater than 0, got {characteristic_length:f}")
        elif characteristic_length > DIE_HEIGHT / 4:
            raise ValueError(f"characteristic_length is extremely large, maybe you meant {characteristic_length:f}e-3?")
        if load_fraction <= 0.0 or load_fraction > 1.0:
            raise ValueError(f"load_fraction must be in (0.0, 1.0], got {load_fraction}")
        self._options: str | None = None
        self.voxel_data: Path = voxel_data
        self.characteristic_length: float = characteristic_length
        self.load_fraction: float = load_fraction
        self.scratch_dir: Path = scratch_dir or Path(config.get_fallback('SCRATCH_DIR')).resolve()
        base_config = _solver_config_file.read_text() + '\n' + _material_config_file.read_text()
        base_name = Path(__file__).stem.replace('_', '-')
        name = f"{base_name}-CL{characteristic_length}-LF{load_fraction}"
        super().__init__(name, __doc__, base_config)

    @property
    def mesh_options(self) -> str:
        options = get_mesh(
            self.characteristic_length,
            self.voxel_data,
            self.scratch_dir,
            load_fraction=self.load_fraction
        )
        options += '\n' + '\n'.join([
            "# Specific options for sticky air die experiment",
            f"mpm_void_characteristic_length: {self.characteristic_length * 4}",
            f"mpm_grains_characteristic_length: {self.characteristic_length * 4}",
            f"mpm_binder_characteristic_length: {self.characteristic_length * 4}",
            "",
        ])
        return options

    def __str__(self) -> str:
        output = '\n'.join([
            f'[h1]Ratel iMPM Experiment[/]',
            f'{self.description}',
            f"\n[h2]Mesh Options[/]",
            f"  • Characteristic length: {self.characteristic_length}",
            f"  • Voxel data: {self.voxel_data}",
        ])
        if self.user_options:
            output += "\n[h2]User Options[/]\n"
            output += "\n".join([f"  • {key}: {value}" for key, value in self.user_options.items()])
        return output


app = typer.Typer()


@app.command()
def write_config(voxel_data: Path, characteristic_length: Annotated[float, typer.Argument(min=0, max=DIE_HEIGHT / 4)], load_fraction: Annotated[float, typer.Argument(min=0.0, max=1.0)] = 0.4,
                 output_dir: Annotated[Path, typer.Option(file_okay=False, resolve_path=True)] = Path.cwd(), log_view: bool = False):
    """Generate the efficiency experiment configuration."""
    experiment = PressStickyAirExperiment(voxel_data, characteristic_length, load_fraction)
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
    experiment.logview = log_view
    experiment.write_config(output_dir)


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)
def run(ctx: typer.Context, voxel_data: Path, characteristic_length: Annotated[float, typer.Argument(min=0, max=DIE_HEIGHT / 4)], load_fraction: Annotated[float, typer.Argument(min=0.0, max=1.0)] = 0.4,
        num_processes: Annotated[int, typer.Option("-n", min=1)] = 1, ratel_dir: Path = None, out: Path = None, scratch_dir: Path = None,
        dry_run: bool = False):
    if scratch_dir is None:
        scratch_dir = Path(config.get_fallback('SCRATCH_DIR')).resolve()
    experiment = PressStickyAirExperiment(voxel_data, characteristic_length, load_fraction, scratch_dir)
    experiment.user_options = ctx.args
    local.run(
        experiment,
        num_processes=num_processes,
        ratel_dir=ratel_dir,
        out=out,
        scratch_dir=scratch_dir,
        dry_run=dry_run
    )


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)
def flux_run(ctx: typer.Context, voxel_data: Path, characteristic_length: Annotated[float, typer.Argument(min=0, max=DIE_HEIGHT / 4)], load_fraction: Annotated[float, typer.Argument(min=0.0, max=1.0)] = 0.4,
             num_processes: Annotated[int, typer.Option("-n", min=1)] = 1, max_time: str = None, log_view: bool = False, machine: Optional[machines.Machine] = None, ratel_dir: Path = None,
             output_dir: Path = None, scratch_dir: Path = None, dry_run: bool = False):
    """Run the efficiency experiment using flux."""
    if scratch_dir is None:
        scratch_dir = Path(config.get_fallback('SCRATCH_DIR')).resolve()
    experiment = PressStickyAirExperiment(voxel_data, characteristic_length, load_fraction, scratch_dir)
    experiment.user_options = ctx.args
    experiment.logview = log_view
    script_file = flux.generate(
        experiment,
        machine=machine,
        num_processes=num_processes,
        max_time=max_time,
        output_dir=output_dir,
        ratel_dir=ratel_dir,
        scratch_dir=scratch_dir
    )
    if not dry_run:
        flux.run(script_file)
