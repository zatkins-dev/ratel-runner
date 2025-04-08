import subprocess
from rich import print

from .git import Repository
from .build import app
from .. import config

URI = "https://github.com/CEED/libCEED.git"
CONFIG_DEFAULT = """# libCEED configuration file
OPT=-O3 -g -fno-signed-zeros -freciprocal-math -ffp-contract=fast -march=native -fPIC -Wno-pass-failed -fassociative-math -fno-math-errno

HIP_DIR=${{ROCM_PATH}}
CC=$(shell which mpicc)
CXX=$(shell which mpicxx)
FC=
"""


def get_repository():
    """Get the repository."""
    repo = Repository(URI)
    if not repo.is_cloned():
        repo.clone()
    return repo


@app.command("libceed")
def build_libceed():
    """Build PETSc."""
    print("[h1]Building libCEED[/h1]")

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
        config_file.write_text(CONFIG_DEFAULT)

    # Run the make command
    make_command = ["make", "-j", "lib"]
    print("[info]Running make command:")
    print("  > ", " ".join(make_command))
    subprocess.run(make_command, cwd=repo.dir, check=True)

    # Save the directory
    config.set("LIBCEED_DIR", str(repo.dir))

    print(f"[success]libCEED build complete with LIBCEED_DIR={repo.dir}.")
    return repo.dir
