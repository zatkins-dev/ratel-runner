from pathlib import Path
import importlib.resources
from typing import ClassVar

from .press_common import PressExperiment, MaterialType


class PressNoAirExperiment(PressExperiment):
    """Die press experiment using voxelized CT data and a synthetic mesh"""
    @property
    def solver_config(self) -> str:
        if hasattr(self, '_solver_options'):
            return getattr(self, '_solver_options')
        options = (importlib.resources.files(__package__ or '') / 'yml' / 'common_solver.yml').read_text()
        setattr(self, '_solver_options', options)
        return getattr(self, '_solver_options')

    @property
    def material_config(self) -> str:
        if hasattr(self, '_material_options'):
            return getattr(self, '_material_options')
        options = (importlib.resources.files(__package__ or '') / 'yml' /
                   f'press_no_air_{self.material.value}.yml').read_text()
        if self.material == MaterialType.MONOCLINIC or self.material == MaterialType.TRICLINIC:
            options += f"\nmpm_grains_random_seed: {self.seed}\n"
        setattr(self, '_material_options', options)
        return getattr(self, '_material_options')

    base_name: ClassVar[str] = 'no-air'

    def __init__(self, *super_args, **super_kwargs):
        super().__init__(*super_args, **super_kwargs, base_name=Path(__file__).stem.replace('_', '-'),
                         pretty_name="Ratel iMPM Press Experiment, no air, background stabilization", description=self.__doc__)

    @property
    def mesh_options(self) -> str:
        if hasattr(self, '_mesh_options'):
            return getattr(self, '_mesh_options')
        options = super().mesh_options
        if self.material == MaterialType.DAMAGE:
            options += '\n' + '\n'.join([
                "# Specific options for no air die experiment",
                f"mpm_grains_characteristic_length: {self.characteristic_length * 4}",
                f"mpm_binder_characteristic_length: {self.characteristic_length * 4}",
                f"mpm_stabilization_background_stiffness_characteristic_length: {self.characteristic_length * 4}",
                "",
            ])
        setattr(self, '_mesh_options', options)
        return options


app = PressNoAirExperiment.create_app()
