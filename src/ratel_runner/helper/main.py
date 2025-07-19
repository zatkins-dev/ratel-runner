import typer
import logging
import rich
from rich.logging import RichHandler
from rich.theme import Theme
from pathlib import Path
from typing import Optional

from . import build
from . import config


custom_theme = Theme({
    "info": "dim white",
    "warning": "bold yellow",
    "error": "bold red",
    "success": "bold green",
    "h1": "bold underline green",
    "h2": "bold underline white",
})

FORMAT = "%(message)s"
logging.basicConfig(
    level=logging.WARNING, format=FORMAT, datefmt="[%X]", handlers=[RichHandler()]
)
rich.reconfigure(theme=custom_theme, soft_wrap=True)

app = typer.Typer()


@app.callback()
def main(
    ratel_dir: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    scratch_dir: Optional[Path] = None,
):
    """
    Ratel Build and Run Helper
    """
    if ratel_dir is not None:
        config.set('RATEL_DIR', f'{ratel_dir.resolve()}')
    if output_dir is not None:
        config.set('OUTPUT_DIR', f'{output_dir.resolve()}')
    if scratch_dir is not None:
        config.set('SCRATCH_DIR', f'{scratch_dir.resolve()}')


app.add_typer(config.app, name="config")
app.add_typer(build.app, name="build")


if __name__ == "__main__":
    app()
