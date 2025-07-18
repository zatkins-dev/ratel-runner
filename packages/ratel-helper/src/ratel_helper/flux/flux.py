# This module is responsible for generating flux scripts to run experiments.
from pathlib import Path
from math import ceil, prod
import tempfile
from rich import print, get_console
import subprocess
import shutil
from itertools import product
from typing import Optional

from .. import config
from .machines import Machine, get_machine_config, detect_machine
from ..experiment import ExperimentConfig


console = get_console()


def generate(
    experiment: ExperimentConfig,
    machine: Optional[Machine],
    num_processes: int,
    max_time: Optional[str] = None,
    link_name: Optional[str] = None,
    output_dir: Optional[Path] = None,
    additional_args: str = ""
) -> tuple[Path, Path]:
    """Generate a flux script to run the experiments."""
    ratel_dir = Path(config.get_fallback('RATEL_DIR'))
    scratch_dir = Path(config.get_fallback('SCRATCH_DIR'))
    output_dir = output_dir or Path(config.get_fallback('OUTPUT_DIR', Path.cwd() / 'output'))
    if machine is None:
        machine = detect_machine()
        if machine is None:
            raise ValueError("Could not detect machine. Please specify a machine.")

    if not output_dir.exists():
        output_dir.mkdir(parents=True)
    if not (output_dir / 'flux_output').exists():
        (output_dir / 'flux_output').mkdir(parents=True)
    machine_config = get_machine_config(machine)
    num_nodes = int(ceil(num_processes / machine_config.gpus_per_node))
    num_processes_total = num_processes + \
        ((machine_config.gpus_per_node - num_processes) % machine_config.gpus_per_node)

    print(f'{experiment}')
    print("")
    print(f"\n[h2]Simulation Options[/]")
    print(f"  • Ratel path: {ratel_dir}")
    print(f"  • Output directory: {output_dir}")
    print(f"  • Scratch directory: {scratch_dir}")
    print(f"  • Number of processes: {num_processes}")
    print(f"  • Number of nodes: {num_nodes}")
    print("")

    cache = scratch_dir / 'flux_scripts'
    if not cache.exists():
        cache.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(dir=cache, prefix=experiment.name))
    options_file: Path = experiment.write_config(temp_dir)
    name = experiment.name if link_name is None else link_name
    options_file = options_file.rename(temp_dir / (name + '.yaml'))
    output_link = output_dir.resolve() if link_name is None else output_dir.resolve() / link_name
    if output_link.exists() and link_name is not None:
        output_link.unlink()

    ratel = f'{ratel_dir}/bin/ratel-quasistatic'
    command = f'{ratel} -ceed {machine_config.ceed_backend} -options_file "$SCRATCH/options.yml" {additional_args}'

    script = '\n'.join([
        '#!/bin/bash',
        '',
        f'#flux: -N {num_nodes}',
        f'#flux: -n {num_processes_total} # 1 proc per gpu, may be larger than necessary, but needed for binding',
        '#flux: -x',
        f'#flux: -t {max_time if max_time is not None else machine_config.max_time}',
        f'#flux: -q {machine_config.partition}',
        f'#flux: --output={output_dir / "flux_output"}/{"output" if link_name is None else link_name}_' '{{id}}.txt',
        f'#flux: --job-name={experiment.name}',
        f'#flux: -B {machine_config.bank}',
        '#flux: --setattr=thp=always # Transparent Huge Pages',
        '#flux: -l # Add task rank prefixes to each line of output.',
        ('#flux: --setattr=hugepages=512GB' if machine == Machine.TUOLUMNE else ''),
        '',
        'echo "~~~~~~~~~~~~~~~~~~~"',
        'echo "Welcome!"',
        'echo "~~~~~~~~~~~~~~~~~~~"',
        'echo ""',
        'echo "-->Loading modules"',
        'echo ""',
        '',
        'module reset',
        *[f'module load {package}' for package in machine_config.packages],
        'module list',
        '',
        'echo ""',
        'echo "-->Job information"',
        'echo "Job ID = $CENTER_JOB_ID"',
        'echo "Flux Resources = $(flux resource info)"',
        '',
        *[f'export {key}={value}' for key, value in machine_config.defines.items()],
        'ulimit -c unlimited',
        '',
        f'export SCRATCH="{scratch_dir}/{experiment.name}-$CENTER_JOB_ID"',
        'echo ""',
        'echo "Scratch = $SCRATCH"',
        'echo ""',
        '',
        'mkdir -p "$SCRATCH"',
        f'ln -s "$SCRATCH" "{output_link}"',
        '',
        'echo ""',
        'echo "-->Moving into scratch directory"',
        'echo ""',
        'cd "$SCRATCH"',
        f'cp "{options_file}" "$SCRATCH/options.yml"',
        f'',
        'echo ""',
        'echo "-->Starting simulation at $(date)"',
        'echo ""',
        '',
        f'flux run -N{num_nodes} -n{num_processes} -g1 -x --verbose -l --setopt=mpibind=verbose:1 \\',
        f'  {command} > "$SCRATCH/run.log" 2>&1',
        '',
        'echo ""',
        'echo "-->Simulation finished at $(date)"',
        'echo ""',
        '',
        'echo "~~~~~~~~~~~~~~~~~~~"',
        'echo "All done! Bye!"',
        'echo "~~~~~~~~~~~~~~~~~~~"',
    ])
    name = experiment.name if link_name is None else link_name
    with tempfile.NamedTemporaryFile(mode='w', delete=False, dir=temp_dir, prefix=name, suffix='.sh') as f:
        f.write(script)
        script_path = Path(f.name)

    return script_path, options_file


def run(script_path: Path):
    command = [
        "flux",
        "batch",
        f"{script_path.resolve()}",
    ]
    print(f"Submitting job with command: {' '.join(command)}")
    proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        print(f"[error]Return code {proc.returncode}: {proc.stderr.decode()}[/]")
    else:
        print(f"[success]Job submitted with ID {proc.stdout.decode()}[/]")
    # script_path.unlink()


def sweep(
    experiment: ExperimentConfig,
    machine: Optional[Machine],
    num_processes: int,
    max_time: Optional[str] = None,
    parameters: dict = {},
    sweep_name: str = 'sweep',
    yes: bool = False,
    dry_run: bool = False,
):
    """Generate flux scripts for a parameter sweep."""
    options = experiment.user_options.copy()
    num_runs = prod(map(len, parameters.values()))
    ratel_dir = Path(config.get_fallback('RATEL_DIR'))
    scratch_dir = Path(config.get_fallback('SCRATCH_DIR'))
    output_dir = Path(config.get_fallback('OUTPUT_DIR', Path.cwd() / 'output'))

    if machine is None:
        machine = detect_machine()
        if machine is None:
            raise ValueError("Could not detect machine. Please specify a machine.")

    if not output_dir.exists():
        output_dir.mkdir(parents=True)

    sweep_name = experiment.name + f'-{sweep_name}-' + '-'.join(parameters.keys())
    sweep_output_dir = (output_dir / sweep_name).resolve()
    sweep_script_dir = (sweep_output_dir / 'flux_scripts').resolve()
    sweep_options_dir = (sweep_output_dir / 'options').resolve()

    print(f'{experiment}')
    print("")
    print(f'[h2]Parameter Sweep[/]')
    print(f"  • Sweeping {len(parameters)} parameters:")
    for name, values in parameters.items():
        print(f"    • {name}: {', '.join(map(str, values))}")
    print(f"  • Total number of runs: {num_runs}")
    print(f"  • Number of processes per run: {num_processes}")
    print(f"  • Number of nodes per run: {int(ceil(num_processes / get_machine_config(machine).gpus_per_node))}")
    print(f"  • Output directory: {sweep_output_dir}")
    print(f"  • Script directory: {sweep_script_dir}")

    if sweep_output_dir.exists() and not yes:
        yn = console.input(f"[warning]Directory {sweep_output_dir} already exists. Remove?[/] (y/n) ")
        if yn.lower() != 'y':
            raise FileExistsError(f"Directory {sweep_output_dir} already exists.")
    if sweep_output_dir.exists():
        shutil.rmtree(sweep_output_dir)
    sweep_output_dir.mkdir(parents=True, exist_ok=True)
    sweep_script_dir.mkdir()
    sweep_options_dir.mkdir()

    scripts = []
    for params in product(*parameters.values()):
        param_dict = dict(zip(parameters.keys(), params))
        param_dict_str = dict(zip(parameters.keys(), map(str, params)))
        new_options = options.copy()
        new_options.update(param_dict_str)
        experiment.user_options = new_options

        print(f"[info]Generating script for parameters:")
        for name, val in param_dict.items():
            print(f"[info]    • {name}: {val}")

        link_name = '---'.join([f"{key}-{value}" for key, value in param_dict_str.items()])

        # Capture output to avoid cluttering console
        console.begin_capture()
        script_path, options_path = generate(
            experiment,
            machine=machine,
            num_processes=num_processes,
            max_time=max_time,
            output_dir=sweep_output_dir,
            link_name=link_name,
        )
        console.end_capture()
        shutil.copy(script_path, sweep_script_dir / script_path.name)
        script_path.unlink()
        script_path = sweep_script_dir / script_path.name

        # Link options file for ease of access
        (sweep_options_dir / options_path.name).symlink_to(options_path)

        scripts.append(script_path)
        print(f"[info]  Script written to: {script_path}[/]")
        print(f"[info]  Output directory:  {sweep_output_dir / link_name}[/]")

    print(f"[info]All scripts written to: {sweep_script_dir}[/]")
    print("")
    if dry_run:
        print(f"[info]Dry run mode: not submitting jobs.[/]")
        return
    print(f"[h2]Submitting jobs...[/]")
    for script_path in scripts:
        run(script_path)

    print(f"[success]All jobs submitted![/]")


def uq(
    experiment: ExperimentConfig,
    machine: Optional[Machine],
    num_processes: int,
    max_time: Optional[str] = None,
    parameters: dict = {},
    sweep_name: str = 'uq',
    yes: bool = False,
    dry_run: bool = False,
):
    """Generate flux scripts for a UQ study."""
    options = experiment.user_options.copy()
    num_runs = len(list(parameters.values())[0])
    scratch_dir = Path(config.get_fallback('SCRATCH_DIR'))
    output_dir = Path(config.get_fallback('OUTPUT_DIR', Path.cwd() / 'output'))
    if machine is None:
        machine = detect_machine()
        if machine is None:
            raise ValueError("Could not detect machine. Please specify a machine.")

    if not output_dir.exists():
        output_dir.mkdir(parents=True)

    sweep_name = experiment.name + f'-{sweep_name}-' + '-'.join(parameters.keys())
    sweep_output_dir = (output_dir / sweep_name).resolve()
    sweep_script_dir = (sweep_output_dir / 'flux_scripts').resolve()
    sweep_options_dir = (sweep_output_dir / 'options').resolve()

    print(f'{experiment}')
    print("")
    print(f'[h2]Parameter Sweep[/]')
    print(f"  • Sweeping {len(parameters)} parameters:")
    for name, values in parameters.items():
        print(f"    • {name}: {', '.join(map(str, values))}")
    print(f"  • Total number of runs: {num_runs}")
    print(f"  • Number of processes per run: {num_processes}")
    print(f"  • Number of nodes per run: {int(ceil(num_processes / get_machine_config(machine).gpus_per_node))}")
    print(f"  • Output directory: {sweep_output_dir}")
    print(f"  • Script directory: {sweep_script_dir}")

    if sweep_output_dir.exists() and not yes:
        yn = console.input(f"[warning]Directory {sweep_output_dir} already exists. Remove?[/] (y/n) ")
        if yn.lower() != 'y':
            raise FileExistsError(f"Directory {sweep_output_dir} already exists.")
    if sweep_output_dir.exists():
        shutil.rmtree(sweep_output_dir)
    sweep_output_dir.mkdir(parents=True, exist_ok=True)
    sweep_script_dir.mkdir()
    sweep_options_dir.mkdir()

    scripts = []
    for params in zip(*parameters.values()):
        param_dict = dict(zip(parameters.keys(), params))
        param_dict_str = dict(zip(parameters.keys(), map(str, params)))
        new_options = options.copy()
        new_options.update(param_dict_str)
        experiment.user_options = new_options

        print(f"[info]Generating script for parameters:")
        for name, val in param_dict.items():
            print(f"[info]    • {name}: {val}")

        link_name = '---'.join([f"{key}-{value}" for key, value in param_dict_str.items()])

        # Capture output to avoid cluttering console
        console.begin_capture()
        script_path, options_path = generate(
            experiment,
            machine=machine,
            num_processes=num_processes,
            max_time=max_time,
            output_dir=sweep_output_dir,
            link_name=link_name,
        )
        console.end_capture()
        shutil.copy(script_path, sweep_script_dir / script_path.name)
        script_path.unlink()
        script_path = sweep_script_dir / script_path.name

        # Link options file for ease of access
        (sweep_options_dir / options_path.name).symlink_to(options_path)

        scripts.append(script_path)
        print(f"[info]  Script written to: {script_path}[/]")
        print(f"[info]  Output directory:  {sweep_output_dir / link_name}[/]")

    print(f"[info]All scripts written to: {sweep_script_dir}[/]")
    print("")
    if dry_run:
        print(f"[info]Dry run mode: not submitting jobs.[/]")
        return
    print(f"[h2]Submitting jobs...[/]")
    for script_path in scripts:
        run(script_path)

    print(f"[success]All jobs submitted![/]")
