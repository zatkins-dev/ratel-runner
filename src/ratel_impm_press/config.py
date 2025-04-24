import typer
import json
from pathlib import Path
from rich import print
import os

__all__ = ['get_app_dir', 'get', 'set', 'unset', 'get_fallback', 'app', 'parse_common_args']


_configuration = None


def _get_config():
    """
    Get the configuration file, creating it if it does not exist.
    """
    app_dir = get_app_dir()
    config_file = app_dir / "config.json"
    if not config_file.exists():
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config = {}
        config_file.write_text(json.dumps(config, indent=2))
    return config_file


def _get_runtime_config():
    """
    Read/write values in the application configuration file.
    """
    global _configuration
    if _configuration is not None:
        return _configuration
    config_file = _get_config()
    _configuration = json.loads(config_file.read_text())
    return _configuration


def _write_runtime_config(ctx: typer.Context):
    config = _get_runtime_config()
    app_dir = get_app_dir()
    config_file = app_dir / "config.json"
    config_file.write_text(json.dumps(config, indent=2))


app = typer.Typer(callback=_get_runtime_config, result_callback=_write_runtime_config)


def get_app_dir():
    return Path(typer.get_app_dir("ratel-impm-press"))


def unset(key: str):
    """
    Remove a key from the runtime configuration.
    """
    config = _get_runtime_config()
    if key in config:
        del config[key]


@app.command('unset')
def unset_cmd(key: str):
    """
    Remove a key from the configuration file.
    """
    unset(key)


def set(key: str, value: str, quiet: bool = True):
    """
    Set a key-value pair in the runtime configuration.
    """
    config = _get_runtime_config()
    if not quiet:
        if key in config:
            print(f"Key {key} already exists. Overwriting value.")
        else:
            print(f"Setting {key} to {value}.")
    config[key] = value


@app.command('set')
def set_cmd(key: str, value: str):
    """
    Set a key-value pair in the configuration file.
    """
    set(key, value, quiet=False)


def get(key: str):
    """
    Internal helper function to get the value of a key from the config file.
    """
    config = _get_runtime_config()
    return config.get(key, None)


@app.command('get')
def get_cmd(key: str):
    """
    Get the value of a key in the configuration file.
    """
    val = get(key)
    print(f"{key}: ", "Key not found." if val is None else val)


def list():
    """
    List all keys in the configuration file.
    """
    config = _get_runtime_config()
    for key, value in config.items():
        print(f"{key}: {value}")


@app.command('list')
def list_cmd():
    """
    List all keys and values in the configuration file.
    """
    list()


def get_fallback(key: str, default=None):
    """
    Get the value of a key from the runtime config, environment variable, default provided, or raise an error.
    """
    value = get(key)
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
