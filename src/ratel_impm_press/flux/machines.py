from enum import Enum
from dataclasses import dataclass, field
import platform
import getpass
from pathlib import Path
from rich import print

from ..import config


@dataclass
class MachineConfig:
    gpus_per_node: int
    bank: str
    partition: str
    max_time: str
    ceed_backend: str
    parallel_filesystem: Path
    packages: list[str] = field(default_factory=list)
    defines: dict[str, str] = field(default_factory=dict)


class Machine(Enum):
    """Enumeration of the machines that can be used for the experiments."""
    TUOLUMNE = 'tuolumne'
    TIOGA = 'tioga'
    LASSEN = 'lassen'
    DEFAULT = 'default'


def get_machine_config(machine: Machine) -> MachineConfig:
    """Get the configuration for the specified machine."""
    machine = Machine(machine)
    if machine == Machine.TUOLUMNE:
        tuo_packages = [
            'rocmcc/6.4.0-cce-19.0.0d-magic',
            'rocm/6.4.0',
            'craype-accel-amd-gfx942',
            'cray-python',
            'cray-libsci_acc',
            'cray-hdf5-parallel/1.14.3.5',
            'flux_wrappers',
            'cray-mpich/8.1.32',  # needed while 8.1.33 is in beta
        ]
        tuo_defines = {
            'HSA_XNACK': '1',
            'MPICH_GPU_SUPPORT_ENABLED': '1',
            'MPICH_SMP_SINGLE_COPY_MODE': 'XPMEM',
        }
        return MachineConfig(
            gpus_per_node=4,
            bank='uco',
            partition='pbatch',
            max_time='12h',
            ceed_backend='/gpu/hip/gen',
            parallel_filesystem=Path('/p/lustre5'),
            packages=tuo_packages,
            defines=tuo_defines
        )
    elif machine == Machine.TIOGA:
        tioga_packages = [
            'rocmcc/6.4.0-cce-19.0.0d-magic',
            'rocm/6.4.0',
            'craype-accel-amd-gfx90a',
            'cray-python',
            'cray-libsci_acc',
            'cray-hdf5-parallel/1.14.3.5',
            'flux_wrappers',
            'cray-mpich/8.1.32',  # needed while 8.1.33 is in beta
        ]
        tioga_defines = {
            'HSA_XNACK': '1',
            'MPICH_GPU_SUPPORT_ENABLED': '1',
        }
        return MachineConfig(
            gpus_per_node=8,
            bank='uco',
            partition='pdebug',
            max_time='12h',
            ceed_backend='/gpu/hip/gen',
            parallel_filesystem=Path('/p/lustre2'),
            packages=tioga_packages,
            defines=tioga_defines)
    elif machine == Machine.LASSEN:
        lassen_packages = [
            'clang/ibm-18.1.8-cuda-11.8.0-gcc-11.2.1',
            'cuda/11.8.0',
            'base-gcc/11.2.1',
            'essl',
            'lapack',
            'python/3.11.5',
        ]
        return MachineConfig(
            gpus_per_node=8,
            bank='uco',
            partition='pdebug',
            max_time='12h',
            ceed_backend='/gpu/cuda/gen',
            parallel_filesystem=Path('/p/gpfs1'),
            packages=lassen_packages)
    else:
        raise ValueError(f'Invalid machine: {machine}')


def detect_machine() -> Machine | None:
    """Detect the machine that the script is running on."""
    hostname = platform.node()
    if hostname.startswith('tuolumne'):
        return Machine.TUOLUMNE
    elif hostname.startswith('tioga'):
        return Machine.TIOGA
    elif hostname.startswith('lassen'):
        return Machine.LASSEN
    print(f'[warning]Could not detect machine from hostname: {hostname}, are you connected to the right machine?[/]')
    return None


def get_scratch(machine: Machine | None) -> Path | None:
    configured_dir = config.get('SCRATCH_DIR', machine=machine)
    if configured_dir or not machine or machine == Machine.DEFAULT:
        return Path(configured_dir) if configured_dir else None
    if machine and machine != Machine.DEFAULT:
        machine_config = get_machine_config(machine)
        default = machine_config.parallel_filesystem / getpass.getuser() / 'ratel-scratch'
        config.set('SCRATCH_DIR', f'{default}', machine=machine, quiet=False)
        return default
