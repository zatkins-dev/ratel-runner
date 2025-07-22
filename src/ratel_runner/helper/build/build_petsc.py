from pathlib import Path
import subprocess
import importlib.resources
from rich import print
import re
import typer
from typing import Annotated, Optional

from ..flux.machines import Machine, detect_machine
from .. import config
from .git import Repository
from .build import app

URI = "https://gitlab.com/petsc/petsc.git"


def get_config(machine: Machine | None) -> str:
    """Get the machine PETSc configuration."""
    if machine is not None and machine != Machine.DEFAULT:
        return importlib.resources.read_text('ratel_runner.helper.build.machines',
                                             f'reconfigure_{machine.value.lower()}.py')
    else:
        raise ValueError(
            "Unsupported machine configuration. Set the PETSC_CONFIG environment variable to a suitable python script.")


def get_repository() -> Repository:
    """Get the repository."""
    repo = Repository(URI)
    if not repo.is_cloned():
        repo.clone()
        repo.checkout('release')
    return repo


@app.command("petsc")
def build_petsc(branch: Optional[str] = None, force: Annotated[bool, typer.Option('-f', '--force')] = False):
    """Build PETSc."""
    print("[h1]Building PETSc[/h1]")
    machine = detect_machine()

    repo = get_repository()
    if branch is None:
        branch = repo.branch
    else:
        print(f"[info]Checking out {branch} and pulling latest changes...")
        repo.checkout(branch)

    if not repo.is_up_to_date():
        pull = force
        if not force:
            pull = typer.confirm(f"\nRepository is not up to date. Pull latest changes from {branch}?")
        if pull:
            print("[info]Pulling latest changes...")
            repo.pull()
    else:
        print("[info]Repository is up to date.")

    # Check if the build directory exists
    petsc_config = config.get_fallback("PETSC_CONFIG", '')
    config_str = ''
    if petsc_config != '':
        if not Path(petsc_config).is_file():
            raise FileNotFoundError(f"Configuration file {petsc_config} does not exist")
        config_str = Path(petsc_config).read_text()
    else:
        config_str = get_config(machine)

    # Copy the configuration file to the repository directory
    (repo.dir / 'reconfigure.py').write_text(config_str)

    # Run the configure script
    print("[info]Running configure script:")
    print("  > python3", f"{repo.dir / 'reconfigure.py'}")
    subprocess.run(['python3', 'reconfigure.py'], cwd=repo.dir, check=True)
    output = subprocess.run(['tail', '-n', '10', f'configure.log'], cwd=repo.dir, text=True, capture_output=True)
    output = output.stdout.splitlines()

    make_cmd = list()
    for i in range(len(output)):
        if "Configure stage complete" in output[i]:
            make_cmd = output[i + 1].strip().split(" ")
            break
    up_to_date = any("Your configure options and state has not changed" in line for line in output)
    if not up_to_date and len(make_cmd) == 0:
        raise RuntimeError("Configuration failed. Check the output for details.")

    # Determine PETSC_ARCH
    petsc_arch = ""
    petscvars = repo.dir / 'lib' / 'petsc' / 'conf' / 'petscvariables'
    matches = re.findall(r"PETSC_ARCH=([^\n]+)", petscvars.read_text())
    if len(matches) > 0:
        petsc_arch = matches[-1]
        print(f"[info]Using PETSC_ARCH={petsc_arch} from {petscvars}")

    # Run the make command
    make_cmd = ["make", f"PETSC_DIR={repo.dir}", f"PETSC_ARCH={petsc_arch}", "lib"]
    print("[info]Running make command:")
    if force:
        make_cmd.append("-B")
    print("  > ", " ".join(make_cmd))
    subprocess.run(make_cmd, cwd=repo.dir, check=True)

    config.set("PETSC_DIR", str(repo.dir))
    config.set("PETSC_ARCH", petsc_arch)

    print("[success]PETSc build complete with", f"PETSC_DIR={repo.dir}", f"PETSC_ARCH={petsc_arch}.")
    return repo.dir, petsc_arch
