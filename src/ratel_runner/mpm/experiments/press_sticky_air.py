from pathlib import Path
import importlib.resources
from typing import ClassVar

from .press_common import PressExperiment


class PressStickyAirExperiment(PressExperiment):
    """Die press experiment using voxelized CT data and a synthetic mesh, using sticky air for voids"""
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
        options = (importlib.resources.files(__package__ or '') / 'yml' / 'press_sticky_air.yml').read_text()
        setattr(self, '_material_options', options)
        return getattr(self, '_material_options')

    base_name: ClassVar[str] = 'sticky-air'

    def __init__(self, *super_args, **super_kwargs,):
        super().__init__(*super_args, **super_kwargs, base_name=Path(__file__).stem.replace('_', '-'),
                         pretty_name="Ratel iMPM Press Experiment, sticky air", description=self.__doc__)

    @property
    def mesh_options(self) -> str:
        if hasattr(self, '_mesh_options'):
            return getattr(self, '_mesh_options')
        options = super().mesh_options
        options += '\n' + '\n'.join([
            "# Specific options for sticky air die experiment",
            f"mpm_void_characteristic_length: {self.characteristic_length * 4}",
            f"mpm_grains_characteristic_length: {self.characteristic_length * 4}",
            f"mpm_binder_characteristic_length: {self.characteristic_length * 4}",
            "",
        ])
        setattr(self, '_mesh_options', options)
        return options


app = PressStickyAirExperiment.create_app()
