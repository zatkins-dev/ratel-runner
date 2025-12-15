from platform import machine
import typer
import json
from pathlib import Path
from rich import print
import os
from typing import Annotated, Any, Callable
from dataclasses import dataclass
from difflib import get_close_matches
from rich.table import Table
from enum import Enum
from copy import deepcopy
from contextlib import contextmanager

from .flux import machines

__all__ = ['get_app_dir', 'get', 'set', 'unset', 'get_fallback', 'app']


class FileOpenMode(Enum):
    READ = 'r'
    WRITE = 'w'

    def __str__(self):
        return self.value

    def __repr__(self):
        return self.value


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
    check: Callable[[Any], bool] = lambda _: True

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


class CheckBounded():
    def __init__(self, lower=None, upper=None, inclusive_lower=False, inclusive_upper=False):
        assert lower is not None or upper is not None, "One of upper or lower bounds must be set"
        self.lower = lower
        self.upper = upper
        self.inclusive_lower = inclusive_lower
        self.inclusive_upper = inclusive_upper

    def __str__(self) -> str:
        if self.lower is None:
            return f"must be <{('=' if self.inclusive_upper else '')} {self.upper}"
        if self.upper is None:
            return f"must be >{('=' if self.inclusive_lower else '')} {self.lower}"
        bracket_lower = "[" if self.inclusive_lower else "("
        bracket_upper = "]" if self.inclusive_upper else ")"
        return f"must be in the interval {bracket_lower}{self.lower}, {self.upper}{bracket_upper}"

    def __call__(self, value) -> bool:
        good = value is not None
        if good and self.lower is not None:
            good = good and (value > self.lower or (self.inclusive_lower and value == self.lower))
        if good and self.upper is not None:
            good = good and (value < self.upper or (self.inclusive_upper and value == self.upper))
        if not good:
            print(f'[error]value {value} {self}')
            return False
        return True


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


def add_key(key_name: str, key: ConfigKey):
    if key_name in _KNOWN_KEYS.keys():
        print(f'[warn]{key_name} already registered, overwriting')
    _KNOWN_KEYS[key_name] = key


def _get_config(machine: machines.Machine | None = None, name: str | None = None):
    """
    Get the configuration file, creating it if it does not exist.
    """
    if machine is None:
        machine = machines.detect_machine()
    app_dir = get_app_dir()
    if name is not None:
        config_file = Path(name)
        if not config_file.is_absolute():
            config_file = app_dir / config_file
        if not config_file.exists():
            config_file.parent.mkdir(parents=True, exist_ok=True)
            config = {}
            config_file.write_text(json.dumps(config, indent=2))
        return config_file
    if machine is None or machine == machines.Machine.DEFAULT:
        config_file = app_dir / "config.json"
    else:
        config_file = app_dir / f'{machine.value.lower()}' / "config.json"
    if not config_file.exists():
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config = {}
        config_file.write_text(json.dumps(config, indent=2))
    return config_file


@contextmanager
def runtime_config(mode: FileOpenMode, machine: machines.Machine | None = None):
    """
    Read/write values in the application configuration file.
    """
    if machine is None:
        machine = machines.detect_machine()
    config_path = _get_config(machine)
    configuration = json.loads(config_path.read_text())
    yield configuration
    if mode == FileOpenMode.WRITE:
        config_path.write_text(json.dumps(configuration, indent=2))
    del configuration


app = typer.Typer(help="Manage Ratel Runner runtime configuration")


def get_app_dir():
    return Path(typer.get_app_dir("ratel-runner"))


def unset(key: str, machine: machines.Machine | None = None):
    """
    Remove a key from the runtime configuration.
    """
    with runtime_config(FileOpenMode.WRITE, machine=machine) as config:
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
    if not config_key.check(config_key.type(value)):
        raise typer.Abort(f'Error: Invalid value {value} for key {key}')
    with runtime_config(FileOpenMode.WRITE, machine=machine) as config:
        if not quiet:
            if config_key.name in config:
                print(f"Key {key} already exists. Overwriting value (old: {config[key]})")
            print(f"Setting {key} to {value}")
        config[config_key.name] = str(config_key.type(value))


@app.command('set')
def set_cmd(key: str, value: str, machine: machines.Machine | None = None):
    """
    Set a key-value pair in the configuration file.
    """
    set(key, value, machine=machine, quiet=False)


def get(key: str, machine: machines.Machine | None = None, quiet: bool = True):
    """
    Internal helper function to get the value of a key from the config file.
    """
    if key not in _KNOWN_KEYS.keys():
        if not quiet:
            print(f"[warn]Unknown key:[/warn] {key}")
        similar = get_close_matches(key, _KNOWN_KEYS.keys())
        if len(similar) and not quiet:
            print(f"[warn]  Similar keys:[/warn] {' '.join(similar)}")
        raise typer.Exit(1)
    config_key = _KNOWN_KEYS[key]
    with runtime_config(FileOpenMode.READ, machine=machine) as config:
        value = config.get(key, None)
    return config_key.type(value) if value else None


@app.command('get')
def get_cmd(key: str, machine: machines.Machine | None = None,
            script: Annotated[bool, typer.Option("-s", help="Output only the value")] = False):
    """
    Get the value of a key in the configuration file.
    """
    val = get(key, machine=machine, quiet=script)
    if script:
        if val is None:
            raise typer.Exit(1)
        print(val)
    else:
        print(f"{key}: ", "Key not found." if val is None else val)


def print_config(config: dict):
    """
    Print the configuration in a human-readable format.
    """
    if len(config) == 0:
        print("[success]Configuration empty, use[/success] `config set` [success]to add configuration variables")
    else:
        table = Table("Name", "Description", "Options", "Value")
        for key, value in config.items():
            config_key = _KNOWN_KEYS.get(key, ConfigKey(f'[warn]{key}', "[warn]UNKNOWN KEY[/warn]", str))
            options = ", ".join(str(e) for e in config_key.type) if issubclass(config_key.type, Enum) else ""
            table.add_row(f'[bold underline]{config_key.name}', f"{config_key.description}", options, value)
        print(table)


def list_config(machine: machines.Machine | None = None):
    """
    List all keys in the configuration file.
    """
    with runtime_config(FileOpenMode.READ, machine=machine) as config:
        print_config(config)


@app.command('list')
def list_cmd(machine: machines.Machine | None = None):
    """
    List all keys and values in the configuration file.
    """
    list_config(machine=machine)


@app.command('copy')
def copy_cmd(src: machines.Machine, dst: Annotated[machines.Machine | None, typer.Argument()] = None):
    """
    Copy all configuration variables from one machine to another
    """
    with runtime_config(FileOpenMode.READ, machine=src) as src_config:
        with runtime_config(FileOpenMode.WRITE, machine=dst) as dst_config:
            dst_config.clear()
            for key, value in src_config.items():
                dst_config[key] = value


@app.command('dump')
def dump_cmd(dst: Path, machine: machines.Machine | None = None):
    """
    Dump the configuration file as JSON
    """
    full_dst = dst.resolve()
    full_dst.parent.mkdir(parents=True, exist_ok=True)
    with runtime_config(FileOpenMode.READ, machine=machine) as config:
        full_dst.write_text(json.dumps(config, indent=2))
    print(f'[success]Wrote configuration to {full_dst}[/success]')


@app.command('load')
def load_cmd(src: Path, machine: machines.Machine | None = None):
    """
    Load the configuration file from JSON
    """
    full_src = src.resolve()
    if not full_src.exists():
        print(f'[error]Source file {full_src} does not exist[/error]')
        raise typer.Exit(1)
    config_data = json.loads(full_src.read_text())
    with runtime_config(FileOpenMode.WRITE, machine=machine) as config:
        config.clear()
        for key, value in config_data.items():
            config[key] = value
    print(f'[success]Loaded configuration from {full_src}[/success]')


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


stash_app = typer.Typer()
app.add_typer(stash_app, name='stash', help='Stash and apply runtime configurations')


@contextmanager
def stash(mode: FileOpenMode = FileOpenMode.WRITE, machine: machines.Machine | None = None):
    """
    Context manager for stashed configurations
    """
    app_dir = get_app_dir()
    if machine is None or machine == machines.Machine.DEFAULT:
        stash_path = app_dir / "stashes.json"
    else:
        stash_path = app_dir / f'{machine.value.lower()}' / "stashes.json"
    stash_path = stash_path
    stash_data = json.loads(stash_path.read_text())
    yield stash_data
    if mode == FileOpenMode.WRITE:
        stash_path.write_text(json.dumps(stash_data, indent=2))
    del stash_data


@stash_app.command('push')
def stash_push(name: Annotated[str | None, typer.Argument()] = None,
               machine: machines.Machine | None = None, quiet: bool = False):
    """
    Stash the current configuration under a given name
    """
    with stash(mode=FileOpenMode.WRITE, machine=machine) as stash_data:
        with runtime_config(FileOpenMode.READ, machine=machine) as config:
            if name is None:
                name = f'stash-{len(stash_data["stashes"])+1}'
            stash_data['stashes'][name] = deepcopy(config)
            stash_data['stack'].append(name)
            if not quiet:
                print(f'Stashed current configuration as [bold]{name}[/bold]')


@stash_app.command('apply')
def stash_apply(name: Annotated[str | None, typer.Argument()] = None,
                machine: machines.Machine | None = None, quiet: bool = False) -> str:
    """
    Apply the stashed configuration with the given name
    """
    with stash(mode=FileOpenMode.READ, machine=machine) as stash_data:
        with runtime_config(FileOpenMode.WRITE, machine=machine) as config:
            if name is None:
                if len(stash_data['stack']) == 0:
                    if not quiet:
                        print('[error]No stashed configurations to apply[/error]')
                    raise typer.Exit(1)
                resolved_name: str = stash_data['stack'][-1]
            else:
                resolved_name = name
            if resolved_name not in stash_data['stashes']:
                print(f'[error]No stashed configuration with name {resolved_name}[/error]')
                raise typer.Exit(1)
            stashed_config = stash_data['stashes'][resolved_name]
            config.clear()
            for key, value in stashed_config.items():
                config[key] = value
            if not quiet:
                print(f'Applied stashed configuration [bold]{resolved_name}[/bold]:')
                print_config(config)
    return resolved_name


@stash_app.command('remove')
def stash_remove(name: str, machine: machines.Machine | None = None):
    """
    Remove the stashed configuration with the given name without applying it
    """
    with stash(mode=FileOpenMode.WRITE, machine=machine) as stash_data:
        if name not in stash_data['stashes']:
            print(f'[error]No stashed configuration with name {name}[/error]')
            raise typer.Exit(1)
        stash_data['stack'].remove(name)
        del stash_data['stashes'][name]


@stash_app.command('pop')
def stash_pop(name: Annotated[str | None, typer.Argument()] = None,
              machine: machines.Machine | None = None, quiet: bool = False):
    """
    Apply the stashed configuration with the given name and remove it from the stash
    """
    name = stash_apply(name=name, machine=machine, quiet=quiet)
    stash_remove(name=name, machine=machine)


@stash_app.command('show')
def stash_show(name: str, machine: machines.Machine | None = None, quiet: bool = False):
    """
    Show the stashed configuration with the given name without applying it
    """
    with stash(mode=FileOpenMode.READ, machine=machine) as stash_data:
        if name not in stash_data['stashes']:
            print(f'[error]No stashed configuration with name {name}[/error]')
            raise typer.Exit(1)
        stashed_config = stash_data['stashes'][name]
        if not quiet:
            print(f'Stashed configuration [bold]{name}[/bold]:')
            print_config(stashed_config)


@stash_app.command('peek')
def stash_peek(machine: machines.Machine | None = None):
    """
    Show the most recently stashed configuration without applying it
    """
    with stash(mode=FileOpenMode.READ, machine=machine) as stash_data:
        if len(stash_data['stack']) == 0:
            print('[error]No stashed configurations to show[/error]')
            raise typer.Exit(1)
        name = stash_data['stack'][-1]
        stashed_config = stash_data['stashes'][name]
        print(f'Stashed configuration [bold]{name}[/bold]:')
        print_config(stashed_config)


@stash_app.command('list')
def stash_list(machine: machines.Machine | None = None):
    """
    List all stashed configurations
    """
    with stash(mode=FileOpenMode.READ, machine=machine) as stash_data:
        if len(stash_data['stashes']) == 0:
            print('[success]No stashed configurations[/success]')
            return
        table = Table("Index", "Name")
        for order, name in enumerate(stash_data['stack'][::-1], start=1):
            table.add_row(str(order), f'[bold]{name}[/bold]')
        print(table)


@stash_app.command('clear')
def stash_clear(machine: machines.Machine | None = None, quiet: bool = False):
    """
    Clear all stashed configurations
    """
    with stash(mode=FileOpenMode.WRITE, machine=machine) as stash_data:
        stash_data['stack'] = []
        stash_data['stashes'] = {}
    if not quiet:
        print('[success]Cleared all stashed configurations[/success]')
