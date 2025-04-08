from pathlib import Path
import subprocess
import importlib.resources
import shutil
from rich import print
import re
import os

from ..flux.machines import Machine, detect_machine
from .. import config
from .git import Repository
from .build import app

URI = "https://gitlab.com/petsc/petsc.git"


def get_config(machine: Machine):
    """Get the machine PETSc configuration."""
    if machine == Machine.TUOLUMNE:
        return Path(importlib.resources.files('ratel_impm_press') / 'build' / 'machines' / 'reconfigure_tuolumne.py')
    else:
        raise ValueError(
            "Unsupported machine configuration. Set the PETSC_CONFIG environment variable to a suitable python script.")


def get_repository():
    """Get the repository."""
    repo = Repository(URI)
    if not repo.is_cloned():
        repo.clone()
    return repo


@app.command("petsc")
def build_petsc():
    """Build PETSc."""
    print("[h1]Building PETSc[/h1]")

    repo = get_repository()
    if not repo.is_up_to_date():
        print("[info]Repository is not up to date. Pulling latest changes...")
        repo.pull()
    else:
        print("[info]Repository is up to date.")

    # Check if the build directory exists
    petsc_config = config.get_fallback("PETSC_CONFIG", "")
    if petsc_config == "":
        petsc_config = get_config(detect_machine())
    petsc_config = Path(petsc_config).resolve()
    if not petsc_config.exists():
        raise FileNotFoundError(f"Configuration file {petsc_config} does not exist")

    # Copy the configuration file to the repository directory
    shutil.copy(petsc_config, repo.dir / 'reconfigure.py')

    # Run the configure script
    print("[info]Running configure script:")
    print("  > python3", f"{repo.dir / 'reconfigure.py'}")
    subprocess.run(['python3', 'reconfigure.py'], cwd=repo.dir, check=True)
    output = subprocess.run(['tail', '-n', '10', f'configure.log'], cwd=repo.dir, text=True, capture_output=True)
    output = output.stdout.splitlines()

    configured = False
    for i in range(len(output)):
        if "Configure stage complete" in output[i]:
            configured = True
            make_cmd = output[i + 1].strip().split(" ")
            break

    up_to_date = any("Your configure options and state has not changed" in line for line in output)
    if not up_to_date and not configured:
        raise RuntimeError("Configuration failed. Check the output for details.")

    if not up_to_date:
        # Run the make command
        print("[info]Running make command:")
        print("  > ", " ".join(make_cmd))
        subprocess.run(make_cmd, cwd=repo.dir, check=True)
    else:
        print("[info]Configuration is up to date. No need to rebuild.")

    # Determine PETSC_ARCH
    petsc_arch = ""
    petscvars = repo.dir / 'lib' / 'petsc' / 'conf' / 'petscvariables'
    matches = re.findall(r"PETSC_ARCH=([^\n]+)", petscvars.read_text())
    if len(matches) > 0:
        petsc_arch = matches[-1]
        print(f"[info]Using PETSC_ARCH={petsc_arch} from {petscvars}")

    print(f"[success]PETSc build complete with PETSC_DIR={repo.dir} and PETSC_ARCH={petsc_arch}.")
    return repo.dir, petsc_arch
