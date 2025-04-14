# This module is responsible for generating flux scripts to run experiments.
from pathlib import Path
from math import ceil
import tempfile
import rich
import subprocess

from .. import config
from .machines import Machine, get_machine_config, detect_machine
from ..experiment import ExperimentConfig

console = rich.get_console()
print = console.print


def generate(experiment: ExperimentConfig, machine: Machine | None, num_processes: int, max_time: str = None,
             output_dir: Path = None, ratel_dir: Path = None, scratch_dir: Path = None, additional_args: str = ""):
    """Generate a flux script to run the experiments."""
    if ratel_dir is None:
        ratel_dir = Path(config.get_fallback('RATEL_DIR'))
    if scratch_dir is None:
        scratch_dir = Path(config.get_fallback('SCRATCH_DIR'))
    if output_dir is None:
        output_dir = Path(config.get_fallback('OUTPUT_DIR', Path.cwd() / 'output'))
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

    command = f'{ratel_dir}/bin/ratel-quasistatic -ceed {machine_config.ceed_backend} -options_file "$SCRATCH/options.yml" {additional_args}'

    script = '\n'.join([
        '#!/bin/bash',
        '',
        f'#flux: -N {num_nodes}',
        f'#flux: -n {num_processes_total} # 1 proc per gpu, may be larger than necessary, but needed for binding',
        '#flux: -x',
        f'#flux: -t {max_time if max_time is not None else machine_config.max_time}',
        f'#flux: -q {machine_config.partition}',
        f'#flux: --output={output_dir / "flux_output"}' '/output_{{id}}.txt',
        f'#flux: --job-name={experiment.name}',
        f'#flux: -B {machine_config.bank}',
        '#flux: --setattr=thp=always # Transparent Huge Pages',
        '#flux: -l # Add task rank prefixes to each line of output.',
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
        '',
        f'export SCRATCH="{scratch_dir}/{experiment.name}-$CENTER_JOB_ID"',
        'echo ""',
        'echo "Scratch = $SCRATCH"',
        'echo ""',
        '',
        'mkdir -p "$SCRATCH"',
        f'ln -s "$SCRATCH" {output_dir.resolve()}',
        '',
        'echo ""',
        'echo "-->Moving into scratch directory"',
        'echo ""',
        'cd "$SCRATCH"',
        f'cp {options_file.resolve()} "$SCRATCH/options.yml"',
        f'',
        'echo ""',
        'echo "-->Starting simulation at $(date)"',
        'echo ""',
        '',
        f'flux run -N{num_nodes} -n{num_processes} -g1 -x --verbose --setopt=mpibind=verbose:1 \\',
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

    with tempfile.NamedTemporaryFile(mode='w', delete=False, dir=temp_dir, suffix='.sh') as f:
        f.write(script)
        script_path = Path(f.name)

    return script_path


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
