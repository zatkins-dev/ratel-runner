from dataclasses import dataclass
import yaml
import rich
import re
from pathlib import Path
from typing import Annotated
import typer

__doc__ = "Load and write sweep specifications for Ratel iMPM experiments"
__all__ = ['load_sweep_specification', 'write_sweep_specification']

console = rich.get_console()
print = console.print

app = typer.Typer(help=__doc__)

# https://stackoverflow.com/a/4703508
numeric_pattern = r'[-+]?(?:(?:\d*\.\d+)|(?:\d+\.?))(?:[Ee][+-]?\d+)?'
range_pattern = re.compile(rf'^({numeric_pattern}):({numeric_pattern}):(\d+)$')


@dataclass
class ParameterRange:
    """
    Class to hold a range of values for a parameter in the sweep specification.

    The range is defined by a start value, an end value, and a count of values.
    The step size is calculated as (end - start) / (count - 1).
    """
    start: float
    end: float
    count: int

    @property
    def values(self) -> list[float]:
        step = (self.end - self.start) / (self.count - 1)
        return [self.start + i * step for i in range(self.count)]


def range_representer(dumper: yaml.Dumper, data: ParameterRange) -> str:
    """
    String representation of a range in the format start:end:count.
    """
    return dumper.represent_scalar("!parameter_range", f"{data.start}:{data.end}:{data.count}")


def range_parser(loader: yaml.Loader, node: yaml.Node) -> ParameterRange:
    """
    Parse a string in the format start:end:count into a tuple of (start, end, count).
    """
    value = loader.construct_scalar(node)
    match = range_pattern.match(value)
    if not match:
        raise ValueError(f"Invalid range format: {value}")
    start, end, count = match.groups()
    return ParameterRange(float(start), float(end), int(count))


yaml.add_constructor('!parameter_range', range_parser)
yaml.add_implicit_resolver('!parameter_range', range_pattern)
yaml.add_representer(ParameterRange, range_representer)


@app.command('load')
def load_sweep_specification(ctx: typer.Context, path: Path, quiet: bool = False) -> dict[str, list]:
    """
    Load the sweep specification from a YAML file.

    The YAML file should contain a dictionary where keys are parameter names
    and values are either a list of values or a range in the format start:end:count.
    """
    with open(path, 'r') as file:
        data = yaml.full_load(file)
        if not isinstance(data, dict):
            raise ValueError(f"Sweep specification file {path} is not a valid YAML file")
    sweep_parameters = {}
    for parameter, values in data.items():
        if isinstance(values, list):
            sweep_parameters[parameter] = values
        elif isinstance(values, ParameterRange):
            sweep_parameters[parameter] = values.values
        elif isinstance(values, str):
            sweep_parameters[parameter] = [values]
        else:
            raise ValueError(f"Invalid value for parameter {parameter}: {values}")
    if not quiet:
        print(f"Loaded sweep specification from {path}:")
        for parameter, values in sweep_parameters.items():
            print(f"  {parameter}: {values}")
    return sweep_parameters


@app.command('write')
def write_sweep_specification(path: Path, parameters: list[str]):
    """
    Write the sweep specification to a YAML file.

    The parameters should be a dictionary where keys are parameter names
    and values are lists of values.
    """
    mapped_parameters = {}
    for parameter, values in zip(parameters[::2], parameters[1::2]):
        match = range_pattern.match(values)
        if match:
            start, end, count = match.groups()
            mapped_parameters[parameter] = ParameterRange(float(start), float(end), int(count))
        else:
            val_list = values.split(',')
            mapped_parameters[parameter] = val_list

    with open(path, 'w') as file:
        yaml.dump(mapped_parameters, file)
