# Ratel Runner

CLI tools for building and running [Ratel](https://gitlab.com/micromorph/ratel) experiments.

Questions, comments, or concerns? Contact Zach Atkins or leave an issue.

## Installation

### UV (Recommended)

First, install [uv](https://github.com/astral-sh/uv), an open-source Python package manager written in Rust.
Installing `uv` does not require root privileges and takes only a few seconds.

Then, you can either run `ratel-runner` without installing or install it using `uv`:
```bash
uvx ratel-runner
uv tool install 'ratel-runner@latest'
```

If you want to run iMPM experiments, specify the `[mpm]` optional dependency:
```bash
uvx ratel-runner
uv tool install 'ratel-runner[mpm]@latest'
```

### Virtual Environment
If building on Tioga or Tuolumne, ensure you have a new enough Python version:
```bash
ml +cray-python
```

To install the python package, run:
```bash
pip install --user --upgrade ratel-runner
```

On Lassen, you should first make a virtual environment and ensure new enough compilers are set for building `numpy`:
```bash
ml +python/3.11.5
ml +base-gcc/11.2.1

# create virtual environment
python -m virtualenv .venv
# activate virtual environment
. .venv/bin/activate
# install ratel-runner
CC=gcc CXX=g++ pip install --upgrade git+https://github.com/zatkins-dev/Ratel-iMPM-Press.git
```

If you want to run implicit MPM experiments, you will need to use the `--with gmsh` flag to ensure the dependency is installed:
```bash
pip install --with gmsh --user --upgrade git+https://github.com/zatkins-dev/Ratel-iMPM-Press.git
```
Note, the `gmsh` package is unavailable on Lassen.


## Building Ratel
### Supported Machines

This package supports automatically building Ratel and its dependencies with optimal configurations on:
- [Tioga](https://hpc.llnl.gov/hardware/compute-platforms/tioga)
- [Tuolumne](https://hpc.llnl.gov/hardware/compute-platforms/tuolumne)
- [Lassen](https://hpc.llnl.gov/hardware/compute-platforms/lassen)

If building on Tioga or Tuolumne, ensure you have a new enough Python version:
```bash
ml +cray-python
```
For Lassen, instead use
```bash
ml +python/3.11.5
```

#### Tioga
If you are building on Tioga, add these commands to your `~/.bashrc` or `~/.zshrc` file and ensure they are run before building or acquiring a debug node:
```bash
if [[ "$(hostname)" == "tioga"* ]]; then
	module reset
	ml +rocmcc/6.4.0-cce-19.0.0d-magic
	ml +rocm/6.4.0
	ml +craype-accel-amd-gfx90a
	ml +cray-python
	ml +cray-libsci_acc
	ml +cray-hdf5-parallel/1.14.3.5
	ml +flux_wrappers
	ml +cray-mpich/8.1.32
	export HSA_XNACK=1
	export MPICH_GPU_SUPPORT_ENABLED=1
fi
```

**ALWAYS** build on a debug node. For Tioga, you can get such a node with the command:
```bash
flux alloc --queue=pdebug --setattr=thp=always -x -N1 -n1 -t 1h
```

For Tioga, the scratch directory defaults to the `lustre2` parallel filesystem:
```
/p/lustre2/$USER/ratel-scratch
```

#### Tuolumne
If you are building on Tuolumne, add these commands to your `~/.bashrc` or `~/.zshrc` file and ensure they are run before building or acquiring a debug node:
```bash
if [[ "$(hostname)" == "tuolumne"* ]]; then
	module reset
	ml +rocmcc/6.4.0-cce-19.0.0d-magic
	ml +rocm/6.4.0
	ml +craype-accel-amd-gfx942
	ml +cray-python
	ml +cray-libsci_acc
	ml +cray-hdf5-parallel/1.14.3.5
	ml +flux_wrappers
	ml +cray-mpich/8.1.32
	export HSA_XNACK=1
	export MPICH_GPU_SUPPORT_ENABLED=1
	export MPICH_SMP_SINGLE_COPY_MODE=XPMEM
fi
```

**ALWAYS** build on a debug node. For Tuolumne, you can get such a node with the command:
```bash
flux alloc --queue=pdebug --setattr=thp=always --setattr=hugepages=512GB -x -N1 -n1 -t 1h
```

For Tuolumne, the scratch directory defaults to the `lustre5` parallel filesystem:
```
/p/lustre5/$USER/ratel-scratch
```

#### Lassen
```bash
if [[ "$(hostname)" == "lassen"* ]]; then
	ml +clang/ibm-18.1.8-cuda-11.8.0-gcc-11.2.1
	ml +cuda/11.8.0
	ml +base-gcc/11.2.1
	ml +essl
	ml +lapack
	ml +python/3.11.5
fi
```

**ALWAYS** build on a debug node. For Lassen, you can get such a node with the command:
```bash
lalloc 1
```

For Lassen, the scratch directory defaults to the `gpfs1` parallel filesystem:
```
/p/gpfs1/$USER/ratel-scratch
```


### General Build instructions

Set an appropriate `SCRATCH_DIR` and `OUTPUT_DIR`, e.g.
```bash
# on supported machines, defaults to /parallel/filesystem/path/$USER/ratel-scratch
ratel-runner config set SCRATCH_DIR /p/lustre5/$USER/ratel-scratch
# typically defaults to the directory where commands are run
ratel-runner config set OUTPUT_DIR /usr/workspace/$USER/ratel-runner
```
If you are running on a supported machine, these configuration variables are *optional*.
If you are building on an unsupported machine, you must also set `PETSC_CONFIG` to the path to a Python PETSc configuration script:
```bash
ratel-runner config set PETSC_CONFIG /path/to/reconfigure.py
```
Examples can be found in the [PETSc repository](https://gitlab.com/petsc/petsc/-/tree/main/config/examples).

If you are building on a machine with job scheduling, you should now acquire an interactive allocation, see [Supported Machines](#supported-machines) for examples.

Then, Ratel and its dependencies can be built via:
```bash
ratel-runner build ratel
```

#### Configuration Variables
The following configuration variables are used to build Ratel and run experiments.
The preferred way to set configuration variables is through the `ratel-runner config` command.
```console
> ratel-runner config --help

 Usage: ratel-runner config [OPTIONS] COMMAND [ARGS]...

 Read/write values in the application configuration file.

╭─ Options ─────────────────────────────────────────────────────────────╮
│ --machine        [tuolumne|tioga|default]  [default: None]            │
│ --help                                     Show this message and      │
│                                            exit.                      │
╰───────────────────────────────────────────────────────────────────────╯
╭─ Commands ────────────────────────────────────────────────────────────╮
│ unset   Remove a key from the configuration file.                     │
│ set     Set a key-value pair in the configuration file.               │
│ get     Get the value of a key in the configuration file.             │
│ list    List all keys and values in the configuration file.           │
│ copy    Copy all configuration variables from one machine to another. │
╰───────────────────────────────────────────────────────────────────────╯
```
Alternatively, you can set the variables as environmental variables.

The list of relevant variables is given below.

| Variable      | Description   | Default |
| ------------- | ------------- | ------- |
| `SCRATCH_DIR` | Location to clone and build repositories, store output files from experiments, etc. This should be on a parallel filesystem for most supercomputers. | See [Supported Machines](#supported-machines) |
| `OUTPUT_DIR`  | Location in which symbolic links to experiment result directories will be created. | Current runtime directory. |
| `PETSC_DIR`   | Location of cloned PETSc repository. This can be an existing repository, or PETSc will be cloned to this directory if it does not exist. | `$SCRATCH_DIR/build/petsc` |
| `PETSC_ARCH`   | PETSc arch/build to use. | Machine-dependent |
| `PETSC_CONFIG`   | Python configuration file to use when building PETSc.  | Machine-dependent |
| `LIBCEED_DIR` | Location of cloned libCEED repository. This can be an existing repository, or libCEED will be cloned to this directory if it does not exist. | `$SCRATCH_DIR/build/libCEED` |
| `RATEL_DIR`   | Location of cloned Ratel repository. This can be an existing repository, or Ratel will be cloned to this directory if it does not exist. | `$SCRATCH_DIR/build/ratel` |


## Running Implicit Material Point Method (iMPM) Experiments

Experiments are run through the `ratel-runner press` command, use the help flag for a list of options.
```bash
ratel-runner mpm press --help
```

### Press - Sticky Air
The "sticky-air" experiment models voids as a soft, perfectly compressible solid.
The experiment requires the path to the voxel data file, the characteristic length (in mm), and the desired load fraction.
See the help pages for the `run` and `flux-run` subcommands for other options:
```bash
ratel-runner mpm press sticky-air run --help
ratel-runner mpm press sticky-air flux-run --help
```

Note: The `flux-run` subcommand will only launch a batch job *after* the background mesh is generated.
The background mesh generation may be quite expensive for characteristic lengths below `0.02`, so you should first acquire an interactive allocation, generate the background mesh with a dry run, then finally submit the job from a login node.
For example, to run an experiment with CL 0.02 and load fraction 0.4:
```bash
# Get allocation
flux alloc --queue=pdebug --setattr=thp=always --setattr=hugepages=512GB -x -N1 -n1 -t 1h
# Pre-generate mesh (only use 1 process, since we aren't launching the job)
ratel-runner mpm press sticky-air flux-run /path/to/voxel/data 0.02 0.4 -n 1 --dry-run
# Return allocation
exit

# Submit job to queue using generated mesh (note, use 16 processes)
ratel-runner mpm press sticky-air flux-run /path/to/voxel/data 0.02 0.4 -n 16
```

Alternate material properties can be provided as additional flags to the `flux-run` command.
For example, to change the fracture toughness of the `binder` material, you could run
```bash
ratel-runner mpm press sticky-air flux-run /path/to/voxel/data 0.02 0.4 -n 1 --mpm_binder_fracture_toughness 1e2
```
Note: an extra `-` is required when compared to executing Ratel directly.
