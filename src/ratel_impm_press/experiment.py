from abc import ABC
from pathlib import Path


class ExperimentConfig(ABC):
    _name: str
    _description: str
    _base_config: str
    _logview: bool

    def __init__(self, name: str, description: str, base_config: str):
        self._name = name
        self._description = description
        self._base_config = base_config
        self._logview = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def base_config(self) -> str:
        return self._base_config

    @property
    def mesh_options(self) -> str:
        raise NotImplementedError

    @property
    def config(self) -> str:
        config = self.base_config + self.mesh_options
        if self.logview:
            config += '\n'.join([
                'log_view: :log_view.txt',
                'log_view_memory:',
            ])
        return config

    @property
    def logview(self) -> bool:
        return self._logview

    @logview.setter
    def logview(self, value: bool):
        self._logview = value

    def write_config(self, output_dir: Path) -> Path:
        """Write the configuration file for the experiment to output_dir."""
        config_path = output_dir / f'{self.name}.yaml'
        with config_path.open('w') as f:
            f.write(self.config)

        return config_path
