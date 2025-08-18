import typer
import json
from pathlib import Path
from rich import print
import os
from typing import Annotated
from dataclasses import dataclass
from difflib import get_close_matches
from rich.table import Table
from enum import Enum

from .flux import machines

__all__ = ['get_app_dir', 'get', 'set', 'unset', 'get_fallback', 'app']


_configuration = None


class GPUMode(Enum):
    SPX = 'SPX'
    CPX = 'CPX'
    TPX = 'TPX'

    def __str__(self):
        return self.value

    def __repr__(self):
        return self.value


@dataclass
class ConfigKey:
    name: str
    description: str
    type: type

    def __eq__(self, key):
        if isinstance(key, ConfigKey):
            return self.name == key.name
        return self.name == key

    def __hash__(self):
        return hash(self.name)

    def __repr__(self):
        return self.name

    def __str__(self):
        return self.name


_KNOWN_KEYS = {
    "PETSC_DIR": ConfigKey("PETSC_DIR", "PETSc repository directory", Path),
    "PETSC_ARCH": ConfigKey("PETSC_ARCH", "PETSc arch name", Path),
    "PETSC_CONFIG": ConfigKey("PETSC_CONFIG", "User-specified configuration file for PETSc", Path),
    "LIBCEED_DIR": ConfigKey("LIBCEED_DIR", "libCEED repository directory", Path),
    "RATEL_DIR": ConfigKey("RATEL_DIR", "Ratel repository directory", Path),
    "SCRATCH_DIR": ConfigKey("SCRATCH_DIR", "Directory in which to write simulation outputs", Path),
    "OUTPUT_DIR": ConfigKey("OUTPUT_DIR", "Directory in which to place symlinks to output directories", Path),
    "GPU_MODE": ConfigKey("GPU_MODE", "GPU mode, only matters for Tuolumne", GPUMode),
}


def _get_config(machine: machines.Machine | None = None):
    """
    Get the configuration file, creating it if it does not exist.
    """
    if machine is None:
        machine = machines.detect_machine()
    app_dir = get_app_dir()
    if machine is None or machine == machines.Machine.DEFAULT:
        config_file = app_dir / "config.json"
    else:
        config_file = app_dir / f'{machine.value.lower()}' / "config.json"
    if not config_file.exists():
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config = {}
        config_file.write_text(json.dumps(config, indent=2))
    return config_file


def _get_runtime_config(machine: machines.Machine | None = None) -> dict:
    """
    Read/write values in the application configuration file.
    """
    if machine is None:
        machine = machines.detect_machine()
    global _configuration
    if _configuration is None:
        _configuration = dict()
    if _configuration.get(machine, None) is not None:
        return _configuration[machine]
    config_path = _get_config(machine)
    _configuration[machine] = json.loads(config_path.read_text())
    return _configuration[machine]


def _write_runtime_config(ctx: typer.Context, **kwargs):
    global _configuration
    if not _configuration:
        return
    for machine, config in _configuration.items():
        config_file = _get_config(machine)
        config_file.write_text(json.dumps(config, indent=2))


app = typer.Typer(callback=_get_runtime_config, result_callback=_write_runtime_config)


def get_app_dir():
    return Path(typer.get_app_dir("ratel-runner"))


def unset(key: str, machine: machines.Machine | None = None):
    """
    Remove a key from the runtime configuration.
    """
    config = _get_runtime_config(machine=machine)
    if key in config:
        del config[key]


@app.command('unset')
def unset_cmd(key: str, machine: machines.Machine | None = None):
    """
    Remove a key from the configuration file.
    """
    unset(key, machine=machine)


def set(key: str, value: str, machine: machines.Machine | None = None, quiet: bool = True):
    """
    Set a key-value pair in the runtime configuration.
    """
    if key not in _KNOWN_KEYS.keys():
        print(f"[warn]Unknown key:[/warn] {key}")
        similar = get_close_matches(key, _KNOWN_KEYS.keys())
        if len(similar):
            print(f"[warn]  Similar keys:[/warn] {' '.join(similar)}")
        raise typer.Exit(1)
    config_key = _KNOWN_KEYS[key]
    config = _get_runtime_config(machine)
    if not quiet:
        if config_key.name in config:
            print(f"Key {key} already exists. Overwriting value.")
        else:
            print(f"Setting {key} to {value}.")
    config[config_key.name] = str(config_key.type(value))


@app.command('set')
def set_cmd(key: str, value: str, machine: machines.Machine | None = None):
    """
    Set a key-value pair in the configuration file.
    """
    set(key, value, machine=machine, quiet=False)


def get(key: str, machine: machines.Machine | None = None):
    """
    Internal helper function to get the value of a key from the config file.
    """
    if key not in _KNOWN_KEYS.keys():
        print(f"[warn]Unknown key:[/warn] {key}")
        similar = get_close_matches(key, _KNOWN_KEYS.keys())
        if len(similar):
            print(f"[warn]  Similar keys:[/warn] {' '.join(similar)}")
        raise typer.Exit(1)
    config_key = _KNOWN_KEYS[key]
    config = _get_runtime_config(machine)
    value = config.get(key, None)
    return config_key.type(value) if value else None


@app.command('get')
def get_cmd(key: str, machine: machines.Machine | None = None):
    """
    Get the value of a key in the configuration file.
    """
    val = get(key, machine=machine)
    print(f"{key}: ", "Key not found." if val is None else val)


def list(machine: machines.Machine | None = None):
    """
    List all keys in the configuration file.
    """
    config = _get_runtime_config(machine)
    if len(config) == 0:
        print("[success]Configuration empty, use[/success] `config set` [success]to add configuration variables")
    else:
        table = Table("Name", "Description", "Options", "Value")
        for key, value in config.items():
            config_key = _KNOWN_KEYS.get(key, ConfigKey(f'[warn]{key}', "[warn]UNKNOWN KEY[/warn]", str))
            options = ", ".join(str(e) for e in config_key.type) if issubclass(config_key.type, Enum) else ""
            table.add_row(f'[bold underline]{config_key.name}', f"{config_key.description}", options, value)
        print(table)


@app.command('list')
def list_cmd(machine: machines.Machine | None = None):
    """
    List all keys and values in the configuration file.
    """
    list(machine=machine)


@app.command('copy')
def copy_cmd(src: machines.Machine, dst: Annotated[machines.Machine | None, typer.Argument()] = None):
    """
    Copy all configuration variables from one machine to another
    """
    config_from: dict = _get_runtime_config(src)
    config_to: dict = _get_runtime_config(dst)
    config_to.clear()
    for key, value in config_from.items():
        config_to[key] = value


def get_fallback(key: str, default=None, machine: machines.Machine | None = None):
    """
    Get the value of a key from the runtime config, environment variable, default provided, or raise an error.
    """
    value = get(key, machine=machine)
    if value is not None:
        return value
    value = os.environ.get(key, None)
    if value is not None:
        return value
    if default is not None:
        return default
    else:
        raise ValueError(
            f"{key} not set. Please set the {key} environment variable or use the config command to set it.")
