import typer
import logging
import rich
from rich.logging import RichHandler
from rich.theme import Theme

from .experiments import press_no_air, press_sticky_air
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
rich.reconfigure(theme=custom_theme)

app = typer.Typer()
press_app = typer.Typer()
app.add_typer(press_app, name="press")
press_app.add_typer(press_sticky_air.app, name="sticky-air")
# app.add_typer(efficiency.app, name="efficiency")
app.add_typer(config.app, name="config")
app.add_typer(build.app, name="build")

if __name__ == "__main__":
    app()
