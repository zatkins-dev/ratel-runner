# Ratel Implicit Material Point Method (iMPM) Press Experiments

Questions, comments, or concerns? Contact Zach Atkins or leave an issue.


## Installation
If building on Tuolumne, ensure you have a new enough Python version:
```
ml +cray-python
```

To install the python package, run:
```sh
pip install --user --upgrade git+https://github.com/zatkins-dev/Ratel-iMPM-Press.git
```

Set an appropriate `SCRATCH_DIR` and `OUTPUT_DIR`, e.g.
```sh
ratel-impm-press config set SCRATCH_DIR /p/lustre5/$USER/ratel-cache
ratel-impm-press config set OUTPUT_DIR /usr/workspace/$USER/ratel-impm-press
```

If you are building on a machine other than Tuolumne, you must also set `PETSC_CONFIG` to the path to a Python PETSc configuration script:
```sh
ratel-impm-press config set PETSC_CONFIG /path/to/reconfigure.py
```

If you are building on Tuolumne, add these commands to your `~/.bashrc` file:
```bash
if [[ "$(hostname)" == "tuolumne"* ]]; then
	module reset
	ml +rocmcc/6.3.1hangfix-cce-19.0.0a-magic
	ml +rocm/6.3.1
	ml +craype-accel-amd-gfx942
	ml +cray-python
	ml +cray-libsci_acc
	ml +cray-hdf5-parallel/1.14.3.5
	ml +flux_wrappers
	export HSA_XNACK=1
	export MPICH_GPU_SUPPORT_ENABLED=1
fi
```

If you are building on a machine with job scheduling, you should now acquire an interactive allocation, e.g. with
```sh
flux alloc --queue=pdebug --setattr=thp=always --setattr=hugepages=512GB -x -N1 -n1 -t 1h
```

Then, Ratel and its dependencies can be built via:
```sh
ratel-impm-press build ratel
```

## Running experiments

Experiments are run through the `ratel-impm-press press` command, use the help flag for a list of options.
```sh
ratel-impm-press press --help
```

### Press - Sticky Air
The "sticky-air" experiment models voids as a soft, perfectly compressible solid.
The experiment requires the path to the voxel data file, the characteristic length (in mm), and the desired load fraction.
See the help pages for the `run` and `flux-run` subcommands for other options:
```sh
ratel-impm-press press sticky-air run --help
ratel-impm-press press sticky-air flux-run --help
```

Note: The `flux-run` subcommand will only launch a batch job *after* the background mesh is generated.
The background mesh generation may be quite expensive for characteristic lengths below `0.02`, so you should first acquire an interactive allocation, generate the background mesh with a dry run, then finally submit the job from a login node.
For example, to run an experiment with CL 0.02 and load fraction 0.4:
```sh
# Get allocation
flux alloc --queue=pdebug --setattr=thp=always --setattr=hugepages=512GB -x -N1 -n1 -t 1h
# Pre-generate mesh (only use 1 process, since we aren't launching the job)
ratel-impm-press press sticky-air flux-run /path/to/voxel/data 0.02 0.4 -n 1 --dry-run
# Return allocation
exit

# Submit job to queue using generated mesh (note, use 16 processes)
ratel-impm-press press sticky-air flux-run /path/to/voxel/data 0.02 0.4 -n 16
```

Alternate material properties can be provided via the `--additional-args` flag.
For example, to change the fracture toughness of the `binder` material, you could run
```sh
ratel-impm-press press sticky-air flux-run /path/to/voxel/data 0.02 0.4 -n 1 --additional-args '-mpm_binder_fracture_toughness 1e2'
```
Note: single quotes around the additional arguments are needed to prevent bash from getting confused.
If desired, more flags for commonly changed properties can be added.
