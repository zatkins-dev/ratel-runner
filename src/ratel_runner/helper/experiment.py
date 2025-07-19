from abc import ABC, abstractmethod
from pathlib import Path
from enum import Enum
from typing import Optional


class LogViewType(Enum):
    FLAMEGRAPH = "flamegraph"
    XML = "xml"
    DETAIL = "detail"
    TEXT = "text"

    def to_petsc(self) -> str:
        match self:
            case self.FLAMEGRAPH:
                return ".txt:ascii_flamegraph"
            case self.XML:
                return ".xml:ascii_xml"
            case self.DETAIL:
                return ".py:ascii_info_detail"
            case self.TEXT:
                return ".txt"


class ExperimentConfig(ABC):
    _name: str
    _description: str
    _base_config: str
    _logview: Optional[LogViewType]

    def __init__(self, name: str, description: Optional[str], base_config: str):
        self._name = name
        self._description = description or ''
        self._base_config = base_config
        self._logview = None
        self._user_options = dict()
        self.diagnostic_options = dict()

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
    @abstractmethod
    def mesh_options(self) -> str:
        raise NotImplementedError

    @property
    def logview(self) -> LogViewType | None:
        return self._logview

    @logview.setter
    def logview(self, value: Optional[LogViewType]):
        self._logview = LogViewType(value) if value is not None else None

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
    def diagnostic_config(self):
        return '\n# Diagnostic output options\n' + '\n'.join([
            f"{key}: {value}"
            for key, value in self.diagnostic_options.items()
        ])

    @property
    def user_config(self) -> str:
        return '\n# User-provided options\n' + '\n'.join([
            f"{key}: {value}"
            for key, value in self._user_options.items()
        ])

    @property
    def user_options(self) -> dict:
        return self._user_options

    @user_options.setter
    def user_options(self, options: dict | list):
        if isinstance(options, list):
            self._user_options = self.parse_user_args(options)
        elif isinstance(options, dict):
            self._user_options = options
        else:
            raise TypeError("user_options must be a list or a dict")

    @property
    def config(self) -> str:
        config = self.base_config + self.mesh_options + self.diagnostic_config + self.user_config
        match self.logview:
            case LogViewType.FLAMEGRAPH | LogViewType.XML | LogViewType.DETAIL:
                config += '\n' + '\n'.join([
                    f'log_view: :log_view{self.logview.to_petsc()}',
                    # 'log_view_gpu_time:',
                ])
            case LogViewType.TEXT:
                config += '\n' + '\n'.join([
                    f'log_view: :log_view{self.logview.to_petsc()}',
                    # 'log_view_gpu_time:',
                    # 'log_view_memory:'
                ])
        return config

    def write_config(self, output_dir: Path) -> Path:
        """Write the configuration file for the experiment to output_dir."""
        config_path = output_dir / f'{self.name}.yaml'
        with config_path.open('w') as f:
            f.write(self.config)

        return config_path
