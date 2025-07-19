#!/usr/tce/bin/python3

if __name__ == '__main__':
    import sys
    import os
    import shutil
    from pathlib import Path
    sys.path.insert(0, os.path.abspath('config'))
    import configure

    mpi_dir = Path(shutil.which('mpicc'))
    mpi_dir = mpi_dir.resolve().parent.parent

    # I hate hardcoding this, make sure to update if packages change
    XLLIBDIR = '/usr/tce/packages/xl/xl-2023.06.28-cuda-11.8.0-gcc-11.2.1/alllibs'

    configure_options = [
        '--download-kokkos',
        '--download-kokkos-kernels',
        '--download-zlib',
        '--download-hypre',
        '--download-metis',
        '--download-parmetis',
        '--download-triangle',
        '--download-hdf5',
        '--download-cgns',
        f'--with-blaslapack-dir={os.environ["ESSLLIBDIR64"]}',
        '--download-cmake',
        '--with-cuda-arch=70',
        '--with-cuda=1',
        f'--with-cuda-dir={os.environ["CUDA_HOME"]}',
        '--with-debugging=0',
        '--with-fc=0',
        '--with-mpi=1',
        f'--with-mpi-dir={mpi_dir}',
        '--with-64-bit-indices',
        '--COPTFLAGS=-O3 -g -mcpu=native -Wno-pass-failed -fassociative-math -fno-math-errno -fno-omit-frame-pointer -ffp-contract=fast',
        '--CXXOPTFLAGS=-O3 -g -mcpu=native -Wno-pass-failed -fassociative-math -fno-math-errno -fno-omit-frame-pointer -ffp-contract=fast',
        '--FCOPTFLAGS=-O3 -g',
        '--CUDAOPTFLAGS=-O3 -g',
        '--CUDAPPFLAGS=-std=c++17',
        '--LIBS=-lesslsmp -llapackforessl -lxlfmath -lxlf90_r -lxlsmp -lm -lblas -llapack -lscalapack -lcblas -llapacke',
        f'--LDFLAGS=-L{XLLIBDIR} -Wl,-rpath,{XLLIBDIR} -L{os.environ["ESSLLIBDIR64"]} ' +
        f'-Wl,-rpath,{os.environ["ESSLLIBDIR64"]} -L{os.environ["LAPACK_DIR"]}  -Wl,-rpath,{os.environ["LAPACK_DIR"]}',
        # f'--CFLAGS+=-L{XLLIBDIR} -Wl,-rpath,{XLLIBDIR} -L{os.environ["ESSLLIBDIR64"]} -Wl,-rpath,{os.environ["ESSLLIBDIR64"]} -L{os.environ["LAPACK_DIR"]}  -Wl,-rpath,{os.environ["LAPACK_DIR"]}',
        # f'--CXXFLAGS+=-L{XLLIBDIR} -Wl,-rpath,{XLLIBDIR} -L{os.environ["ESSLLIBDIR64"]} -Wl,-rpath,{os.environ["ESSLLIBDIR64"]} -L{os.environ["LAPACK_DIR"]}  -Wl,-rpath,{os.environ["LAPACK_DIR"]}',
        '--PETSC_ARCH=arch-lassen-kokkos-opt',
    ]
    configure.petsc_configure(configure_options)
