import subprocess
from rich import print
from typing import Annotated, Optional
import typer

from .git import Repository
from .build import app
from .. import config
from ..flux.machines import detect_gpu_backend, GPUBackend

URI = "https://github.com/CEED/libCEED.git"
CONFIG_DEFAULT = """# libCEED configuration file
OPT=-O3 -g -fno-signed-zeros -freciprocal-math -ffp-contract=fast -march=native -fPIC -Wno-pass-failed -fassociative-math -fno-math-errno

CC=$(shell which mpicc)
CXX=$(shell which mpicxx)
FC=
"""
CONFIG_ROCM = """
ROCM_DIR=${ROCM_PATH}
"""
CONFIG_CUDA = """
CUDA_DIR=${ROCM_PATH}
"""


def get_repository():
    """Get the repository."""
    repo = Repository(URI)
    if not repo.is_cloned():
        repo.clone()
    return repo


@app.command("libceed")
def build_libceed(branch: Optional[str] = None, force: Annotated[bool, typer.Option('-f', '--force')] = False):
    """Build PETSc."""
    print("[h1]Building libCEED[/h1]")

    repo = get_repository()

    if branch is None:
        branch = repo.branch
    else:
        repo.checkout(branch)

    if not repo.is_up_to_date():
        pull = force
        if not force:
            pull = typer.confirm(f"[info]Repository is not up to date. Pull latest changes from {branch}?")
        if pull:
            print("[info]Pulling latest changes...")
            repo.pull()
    else:
        print("[info]Repository is up to date.")

    # Copy the configuration file to the repository directory
    config_file = repo.dir / 'config.mk'
    if force or not config_file.exists():
        print("[info]Creating default configuration file.")
        backend = detect_gpu_backend()
        if backend == GPUBackend.CUDA:
            config_file.write_text('\n'.join([CONFIG_DEFAULT, CONFIG_CUDA]))
        elif backend == GPUBackend.ROCM:
            config_file.write_text('\n'.join([CONFIG_DEFAULT, CONFIG_ROCM]))
        else:
            config_file.write_text(CONFIG_DEFAULT)

    # Run the make command
    if force:
        make_command = ["make", "-B", "-j", "lib"]
    else:
        make_command = ["make", "-j", "lib"]
    print("[info]Running make command:")
    print("  > ", " ".join(make_command))
    subprocess.run(make_command, cwd=repo.dir, check=True)

    # Save the directory
    config.set("LIBCEED_DIR", str(repo.dir))

    print("[success]libCEED build complete with", f"LIBCEED_DIR={repo.dir}.")
    return repo.dir
