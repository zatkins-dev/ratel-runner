# Ratel Implicit Material Point Method (iMPM) Experiments

Questions, comments, or concerns? Contact Zach Atkins or leave an issue.


## Installation
If building on Tioga or Tuolumne, ensure you have a new enough Python version:
```sh
ml +cray-python
```

To install the python package, run:
```sh
pip install --user --upgrade git+https://github.com/zatkins-dev/Ratel-iMPM-Press.git
```

## Building Ratel
### Supported Machines

This package supports automatically building Ratel and its dependencies with optimal configurations on:
- [Tioga](https://hpc.llnl.gov/hardware/compute-platforms/tioga)
- [Tuolumne](https://hpc.llnl.gov/hardware/compute-platforms/tuolumne)

If building on Tioga or Tuolumne, ensure you have a new enough Python version:
```sh
ml +cray-python
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

**ALWAYS** build on a debug node. For Tuolumne, you can get such a node with the command:
```sh
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

For Tuolumne, the scratch directory defaults to the `lustre5` parallel filesystem:
```
/p/lustre5/$USER/ratel-scratch
```

**ALWAYS** build on a debug node. For Tuolumne, you can get such a node with the command:
```sh
flux alloc --queue=pdebug --setattr=thp=always --setattr=hugepages=512GB -x -N1 -n1 -t 1h
```

### General Build instructions

Set an appropriate `SCRATCH_DIR` and `OUTPUT_DIR`, e.g.
```sh
# on supported machines, defaults to /parallel/filesystem/path/$USER/ratel-scratch
ratel-impm config set SCRATCH_DIR /p/lustre5/$USER/ratel-scratch
# typically defaults to the directory where commands are run
ratel-impm config set OUTPUT_DIR /usr/workspace/$USER/ratel-impm-press
```
If you are running on a supported machine, these configuration variables are *optional*.
If you are building on an unsupported machine, you must also set `PETSC_CONFIG` to the path to a Python PETSc configuration script:
```sh
ratel-impm config set PETSC_CONFIG /path/to/reconfigure.py
```
Examples can be found in the [PETSc repository](https://gitlab.com/petsc/petsc/-/tree/main/config/examples).

If you are building on a machine with job scheduling, you should now acquire an interactive allocation, see [#supported-machines] for examples.

Then, Ratel and its dependencies can be built via:
```sh
ratel-impm build ratel
```

#### Configuration Variables
The following configuration variables are used to build Ratel and run experiments.
The preferred way to set configuration variables is through the `ratel-impm config` command.
```console
> ratel-impm config --help

 Usage: ratel-impm config [OPTIONS] COMMAND [ARGS]...

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
| `SCRATCH_DIR` | Location to clone and build repositories, store output files from experiments, etc. This should be on a parallel filesystem for most supercomputers. | See [#supported-machines] |
| `OUTPUT_DIR`  | Location in which symbolic links to experiment result directories will be created. | Current runtime directory. |
| `PETSC_DIR`   | Location of cloned PETSc repository. This can be an existing repository, or PETSc will be cloned to this directory if it does not exist. | `$SCRATCH_DIR/build/petsc` |
| `LIBCEED_DIR` | Location of cloned libCEED repository. This can be an existing repository, or libCEED will be cloned to this directory if it does not exist. | `$SCRATCH_DIR/build/libCEED` |
| `RATEL_DIR`   | Location of cloned Ratel repository. This can be an existing repository, or Ratel will be cloned to this directory if it does not exist. | `$SCRATCH_DIR/build/ratel` |


## Running experiments

Experiments are run through the `ratel-impm press` command, use the help flag for a list of options.
```sh
ratel-impm press --help
```

### Press - Sticky Air
The "sticky-air" experiment models voids as a soft, perfectly compressible solid.
The experiment requires the path to the voxel data file, the characteristic length (in mm), and the desired load fraction.
See the help pages for the `run` and `flux-run` subcommands for other options:
```sh
ratel-impm press sticky-air run --help
ratel-impm press sticky-air flux-run --help
```

Note: The `flux-run` subcommand will only launch a batch job *after* the background mesh is generated.
The background mesh generation may be quite expensive for characteristic lengths below `0.02`, so you should first acquire an interactive allocation, generate the background mesh with a dry run, then finally submit the job from a login node.
For example, to run an experiment with CL 0.02 and load fraction 0.4:
```sh
# Get allocation
flux alloc --queue=pdebug --setattr=thp=always --setattr=hugepages=512GB -x -N1 -n1 -t 1h
# Pre-generate mesh (only use 1 process, since we aren't launching the job)
ratel-impm press sticky-air flux-run /path/to/voxel/data 0.02 0.4 -n 1 --dry-run
# Return allocation
exit

# Submit job to queue using generated mesh (note, use 16 processes)
ratel-impm press sticky-air flux-run /path/to/voxel/data 0.02 0.4 -n 16
```

Alternate material properties can be provided as additional flags to the `flux-run` command.
For example, to change the fracture toughness of the `binder` material, you could run
```sh
ratel-impm press sticky-air flux-run /path/to/voxel/data 0.02 0.4 -n 1 --mpm_binder_fracture_toughness 1e2
```
Note: an extra `-` is required when compared to executing Ratel directly.
