#!/usr/bin/env python3
if __name__ == '__main__':
    import sys
    import os
    import shutil
    from pathlib import Path
    sys.path.insert(0, os.path.abspath('config'))
    import configure

    mpi_dir = Path(shutil.which('mpicc'))
    mpi_dir = mpi_dir.resolve().parent.parent

    configure_options = [
        f'--with-hdf5-dir={os.environ["HDF5_DIR"]}',
        '--download-cgns',
        '--download-hypre',
        '--download-hypre-configure-arguments=--enable-rocblas --enable-rocsolver --enable-rocsparse --enable-gpu-aware-mpi',
        '--download-kokkos',
        '--download-kokkos-kernels',
        '--download-metis',
        '--download-parmetis',
        '--download-zlib',
        '--with-debugging=0',
        '--with-hip-arch=gfx942_apu',
        f'--with-hip-dir={os.environ["ROCM_PATH"]}',
        f'--with-mpi-dir={mpi_dir}',
        '--with-mpich',
        '--with-64-bit-indices',
        '--with-batch',
        '--with-fc=0',
        'FOPTFLAGS=-O3 -g',
        'HIPOPTFLAGS=-O3 -g -march=native -ffp-contract=fast -fPIC -fno-math-errno -fassociative-math -freciprocal-math',
        'COPTFLAGS=-O3 -g -march=native -ffp-contract=fast -fPIC -fno-math-errno -fassociative-math -freciprocal-math',
        'CXXOPTFLAGS=-O3 -g -march=native -ffp-contract=fast -fPIC -fno-math-errno -fassociative-math -freciprocal-math',
        'PETSC_ARCH=arch-tuolumne-kokkos-O-64',
    ]
    configure.petsc_configure(configure_options)
