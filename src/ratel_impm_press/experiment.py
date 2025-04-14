from abc import ABC, abstractmethod
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
        self._material_options = dict()

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
    def logview(self) -> bool:
        return self._logview

    @logview.setter
    def logview(self, value: bool):
        self._logview = value

    def parse_user_args(self, args) -> dict:
        options = {}
        i = 0
        while i < len(args):
            if args[i].startswith('-'):
                key = args[i].lstrip('-')
                if i + 1 < len(args) and not args[i + 1].startswith('-'):
                    value = args[i + 1]
                    i += 2
                else:
                    value = ''
                    i += 1
                options[key] = value
        return options

    @property
    def user_config(self) -> str:
        return '\n# User-provided options\n' + '\n'.join([
            f"{key}: {value}"
            for key, value in self._material_options.items()
        ])

    @property
    def user_options(self) -> dict:
        return self._material_options

    @user_options.setter
    def user_options(self, options: dict | list):
        if isinstance(options, list):
            self._material_options = self.parse_user_args(options)
        elif isinstance(options, dict):
            self._material_options = options
        else:
            raise TypeError("user_options must be a list or a dict")

    @property
    def config(self) -> str:
        config = self.base_config + self.mesh_options + self.user_config
        if self.logview:
            config += '\n'.join([
                'log_view: :log_view.txt',
                'log_view_memory:',
            ])
        return config

    def write_config(self, output_dir: Path) -> Path:
        """Write the configuration file for the experiment to output_dir."""
        config_path = output_dir / f'{self.name}.yaml'
        with config_path.open('w') as f:
            f.write(self.config)

        return config_path
