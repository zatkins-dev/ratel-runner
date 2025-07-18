import typer

__doc__ = """Automatically build Ratel and its dependencies from source."""

app = typer.Typer(name='ratel-build', help=__doc__)

if __name__ == '__main__':
    app()
