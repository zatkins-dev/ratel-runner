import typer
import logging
import rich
from rich.logging import RichHandler
from rich.theme import Theme

from .plot.pole_diagram import app as plot_pole_diagram_app


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

plot_app = typer.Typer()
app.add_typer(plot_app, name="plot", help="Post-process plotting tools")
plot_app.add_typer(plot_pole_diagram_app)

if __name__ == "__main__":
    app()
