import typer
import json
from pathlib import Path
from rich import print
import os

app = typer.Typer()


def get_app_dir():
    return Path(typer.get_app_dir("ratel-impm-press"))


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


@app.command()
def set(key: str, value: str):
    config_file = _get_config()
    config = json.loads(config_file.read_text())

    config[key] = value
    config_file.write_text(json.dumps(config, indent=2))


def _get(key: str):
    """
    Internal helper function to get the value of a key from the config file.
    """
    config_file = _get_config()
    config = json.loads(config_file.read_text())
    return config.get(key, None)


@app.command()
def get(key: str):
    val = _get(key)
    print(f"{key}: ", "Key not found." if val is None else val)
    return val


@app.command()
def list():
    config_file = _get_config()
    config = json.loads(config_file.read_text())
    for key, value in config.items():
        print(f"{key}: {value}")
    return config


def get_fallback(key: str, default=None):
    value = _get(key)
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
