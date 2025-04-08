import subprocess
from rich import print

from .git import Repository
from .build import app
from . import build_petsc, build_libceed
from .. import config

URI = "https://gitlab.com/micromorph/ratel.git"
CONFIG_DEFAULT = """# Ratel configuration file
OPT=-O3 -g -fno-signed-zeros -freciprocal-math -ffp-contract=fast -march=native -fPIC -Wno-pass-failed -fassociative-math -fno-math-errno
"""


def get_repository():
    """Get the repository."""
    repo = Repository(URI)
    if not repo.is_cloned():
        repo.clone()
    return repo


@app.command("ratel")
def build_ratel():
    """Build Ratel and its dependencies."""
    petsc_dir, petsc_arch = build_petsc.build_petsc()
    libceed_dir = build_libceed.build_libceed()

    print("[h1]Building Ratel[/h1]")

    repo = get_repository()
    if not repo.is_up_to_date():
        print("[info]Repository is not up to date. Pulling latest changes...")
        repo.pull()
    else:
        print("[info]Repository is up to date.")

    # Copy the configuration file to the repository directory
    config_file = repo.dir / 'config.mk'
    if not config_file.exists():
        print("[info]Creating default configuration file.")
        config_str = CONFIG_DEFAULT + "\n".join([
            f"PETSC_DIR={petsc_dir}",
            f"PETSC_ARCH={petsc_arch}",
            f"CEED_DIR={libceed_dir}",
            ""
        ])
        config_file.write_text(config_str)

    # Run the make command
    make_command = ["make", "-j"]
    print("[info]Running make command:")
    print("  > ", " ".join(make_command))
    subprocess.run(make_command, cwd=repo.dir, check=True)

    config.set("RATEL_DIR", str(repo.dir))

    print("[success]Ratel build complete with ", f"RATEL_DIR={repo.dir}.")
