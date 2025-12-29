import typer
import logging
import rich
from rich.logging import RichHandler
from rich.theme import Theme
from pathlib import Path
from typing import Optional

from .helper import build, config

try:
    from .mpm.main import app as mpm_app
    HAVE_MPM = True
except ImportError:
    HAVE_MPM = False


try:
    from .postprocess.main import app as postprocess_app
    HAVE_POSTPROCESS = True
except ImportError:
    HAVE_POSTPROCESS = False

custom_theme = Theme({
    "info": "dim white",
    "warning": "bold yellow",
    "warn": "bold yellow",
    "error": "bold red",
    "err": "bold red",
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


# @app.callback()
def main(
    ratel_dir: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    scratch_dir: Optional[Path] = None,
):
    """
    Ratel Runner
    """
    if ratel_dir is not None:
        config.set('RATEL_DIR', f"{ratel_dir.resolve()}")
    if output_dir is not None:
        config.set('OUTPUT_DIR', f"{output_dir.resolve()}")
    if scratch_dir is not None:
        config.set('SCRATCH_DIR', f"{scratch_dir.resolve()}")


# Basic helper utilities
app.add_typer(config.app, name="config")
app.add_typer(build.app, name="build")

if HAVE_MPM:
    app.add_typer(mpm_app, name="mpm", help="Run iMPM Experiments")

if HAVE_POSTPROCESS:
    app.add_typer(postprocess_app, name="postprocess", help="Post-process iMPM Experiments")
    # # Press experiments
    # press_app = typer.Typer()
    # mpm_app.add_typer(press_app, name="press", help="Press consolidation experiments")
    # press_app.add_typer(press_sticky_air.app)
    # press_app.add_typer(press_no_air.app)
    # mpm_app.add_typer(sweep.app, name="sweep")
    # perf_app = typer.Typer()
    # # Performance experiments
    # mpm_app.add_typer(perf_app, name="performance", help="Performance experiments")
    # perf_app.add_typer(efficiency.app)

if __name__ == "__main__":
    app()
