import typer
import json
from pathlib import Path
from rich import print
import os
from typing import Annotated

from .flux import machines

__all__ = ['get_app_dir', 'get', 'set', 'unset', 'get_fallback', 'app']


_configuration = None


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
    config = _get_runtime_config(machine)
    if not quiet:
        if key in config:
            print(f"Key {key} already exists. Overwriting value.")
        else:
            print(f"Setting {key} to {value}.")
    config[key] = value


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
    config = _get_runtime_config(machine)
    return config.get(key, None)


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
        print("[success]Configuration empty, use `config set` to add configuration variables")
    for key, value in config.items():
        print(f"{key}: {value}")


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
