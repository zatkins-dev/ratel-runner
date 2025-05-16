from enum import Enum
from dataclasses import dataclass, field
import platform
from rich import print


@dataclass
class MachineConfig:
    gpus_per_node: int
    bank: str
    partition: str
    max_time: str
    ceed_backend: str
    packages: list[str] = field(default_factory=list)
    defines: dict[str, str] = field(default_factory=dict)


class Machine(Enum):
    """Enumeration of the machines that can be used for the experiments."""
    TUOLUMNE = 'tuolumne'
    TIOGA = 'tioga'


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
        return MachineConfig(gpus_per_node=4, bank='uco', partition='pbatch', max_time='12h',
                             ceed_backend='/gpu/hip/gen', packages=tuo_packages, defines=tuo_defines)
    elif machine == Machine.TIOGA:
        tioga_packages = [
            'rocmcc/6.1.2-cce-18.0.0-magic',
            'rocm/6.1.2',
            'cray-python/3.11.7',
            'craype-accel-amd-gfx90a',
            'cray-libsci_acc/24.07.0',
            'cray-hdf5-parallel/1.12.2.11',
            'flux_wrappers',
        ]
        tioga_defines = {
            'HSA_XNACK': '1',
            'MPICH_GPU_SUPPORT_ENABLED': '1',
        }
        return MachineConfig(gpus_per_node=8, bank='uco', partition='pdebug', max_time='12h',
                             ceed_backend='/gpu/hip/gen', packages=tioga_packages, defines=tioga_defines)
    else:
        raise ValueError(f'Invalid machine: {machine}')


def detect_machine() -> Machine | None:
    """Detect the machine that the script is running on."""
    hostname = platform.node()
    if hostname.startswith('tuolumne'):
        return Machine.TUOLUMNE
    elif hostname.startswith('tioga'):
        return Machine.TIOGA
    print(f'[warning]Could not detect machine from hostname: {hostname}, are you connected to the right machine?[/]')
    return None
