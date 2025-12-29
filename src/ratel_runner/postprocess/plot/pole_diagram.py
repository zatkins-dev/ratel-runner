import numpy as np
from matplotlib import pyplot as plt
from pathlib import Path
import pyvista as pv
from rich import print
import typer

import yaml

from orix.vector import Miller, Vector3d
from orix.quaternion import Orientation, Misorientation, symmetry
from diffpy.structure import Lattice, Structure
from orix.crystal_map import Phase
from orix import plot, data

app = typer.Typer()

# We'll want our plots to look a bit larger than the default size
plt.rcParams.update(
    {
        "figure.figsize": (10, 5),
        "lines.markersize": 2,
        "font.size": 15,
        "axes.grid": False,
    }
)
w, h = plt.rcParams["figure.figsize"]

monoclinic = Phase(
    point_group=symmetry.C2h,
    structure=Structure(lattice=Lattice(6.53, 11.03, 7.35, 90, 102.689, 90)),
)

triclinic = Phase(
    point_group=symmetry.C1,
    structure=Structure(lattice=Lattice(9.015, 9.0325, 6.825, 108.65, 91.98, 119.94)),
)


def vec_rotate(n, theta, v):
    n_dot_v = np.einsum("ij,ij->i", n, v)
    cos_theta = np.cos(theta)
    n_cross_v = np.cross(n, v)
    v_rot = cos_theta[:, None] * v + (np.sin(theta))[:, None] * n_cross_v + (n_dot_v * (1 - cos_theta))[:, None] * n
    return v_rot


def plot_orientations(orientation_axes, orientation_angles, orientation_axes0,
                      orientation_angles0, phase, out="orientations.png"):
    O0 = Orientation.from_axes_angles(Vector3d(orientation_axes0), orientation_angles0, symmetry=phase.point_group)
    mO = Misorientation.from_axes_angles(Vector3d(orientation_axes), orientation_angles)
    O = mO * O0
    g = Miller(hkl=[0, 0, 1], phase=phase)
    g = g.symmetrise(unique=True)
    poles0 = O0.inv().outer(g, lazy=True, progressbar=True, chunk_size=2000)  # type: ignore
    poles = O.inv().outer(g, lazy=True, progressbar=True, chunk_size=2000)  # type: ignore
    alpha = 10000 / orientation_axes.shape[0]

    fig = plt.figure(figsize=(2 * h, 2 * h))
    subplot_kw = {"projection": "stereographic"}

    ax0 = fig.add_subplot(221, **subplot_kw)
    ax0.scatter(poles0, alpha=alpha)  # type: ignore
    ax0.set_title("Initial")

    ax1 = fig.add_subplot(222, **subplot_kw)
    ax1.pole_density_function(poles0)  # type: ignore
    ax1.set_title("Initial")

    ax2 = fig.add_subplot(223, **subplot_kw)
    ax2.scatter(poles, alpha=alpha)  # type: ignore
    ax2.set_title("Deformed")

    ax3 = fig.add_subplot(224, **subplot_kw)
    ax3.pole_density_function(poles)  # type: ignore
    ax3.set_title("Deformed")
    plt.savefig(out)


def read_mesh(file, time_step=0):
    """Read a mesh from a file."""
    reader: pv.XdmfReader = pv.get_reader(file)  # type: ignore
    reader.set_active_time_point(time_step)
    mesh: pv.DataSet = reader.read()
    grains = mesh.threshold(1.5, scalars='material', method='upper', preference='point')
    del mesh
    return grains


def compute_poles(mesh: pv.DataSet):
    props = np.asarray(mesh.point_data["elastic parameters"])
    state = np.asarray(mesh.point_data["model state"])
    npts = props.shape[0]
    print(f"Computing pole orientations for {npts} points.")
    F = state.reshape((npts, 3, 3)) + np.eye(3)
    Finv = np.linalg.inv(F)
    n0 = props[:, 21:24]
    theta0 = props[:, 24]
    V = np.zeros_like(n0)
    V[:, 2] = 1.
    ab_normal0 = vec_rotate(n0, theta0, V)
    # n_tilde = F^-T * n0
    ab_normal = np.einsum("ijk,ij->ik", Finv, ab_normal0)
    ab_normal /= np.linalg.norm(ab_normal, axis=1, keepdims=True)
    orientation_axes = np.cross(ab_normal0, ab_normal)
    axes = orientation_axes / np.linalg.norm(orientation_axes, axis=1, keepdims=True)
    angles = np.arccos(np.einsum("ij,ij->i", ab_normal, ab_normal0))
    axes0 = n0
    angles0 = theta0
    return axes, angles, axes0, angles0


@app.command()
def pole_diagram(
    run_dir: Path,
    swarm_file: str = "swarm.xdmf",
    time_step: int = 0,
    out: str = "orientations.png",
):
    """Plot pole diagrams from swarm data."""
    swarm_file_path = run_dir / swarm_file
    if not swarm_file_path.exists():
        if swarm_file_path.with_suffix(".xmf").exists():
            swarm_file_path.write_text(swarm_file_path.with_suffix(".xmf").read_text())
        else:
            raise FileNotFoundError(f"Swarm file {swarm_file_path} not found.")
    options_file = run_dir / "options.yml"
    with open(options_file, 'r') as file:
        data = yaml.full_load(file)
    try:
        grain_options = data['mpm']['grains']
        a = grain_options['a'] * 1e7  # convert to angstroms
        b = grain_options['b'] * 1e7  # convert to angstroms
        c = grain_options['c'] * 1e7  # convert to angstroms
        alpha = grain_options['alpha']
        beta = grain_options['beta']
        gamma = grain_options['gamma']
        lattice = Lattice(a, b, c, alpha, beta, gamma)
        if alpha == 90.0 and gamma == 90.0 and beta != 90.0:
            phase = Phase(
                point_group=symmetry.C2h,
                structure=Structure(lattice=lattice),
            )
            print(f"Using monoclinic phase with lattice parameters: {a}, {b}, {c}, {alpha}, {beta}, {gamma}")
        elif alpha != 90.0 and beta != 90.0 and gamma != 90.0:
            phase = Phase(
                point_group=symmetry.C1,
                structure=Structure(lattice=lattice),
            )
            print(f"Using triclinic phase with lattice parameters: {a}, {b}, {c}, {alpha}, {beta}, {gamma}")
        else:
            raise ValueError("Unsupported lattice parameters for pole figure plotting.")
    except KeyError | ValueError:
        # guess
        if "monoclinic" in f'{run_dir}':
            phase = monoclinic
            print(f"Using monoclinic phase with lattice parameters: {phase.structure.lattice}")
        else:
            phase = triclinic
            print(f"Using triclinic phase with lattice parameters: {phase.structure.lattice}")

    axes, angles, axes0, angles0 = compute_poles(read_mesh(run_dir / swarm_file, time_step=time_step))  # type: ignore
    print(f"Computed pole orientations for {axes.shape[0]} points.")
    plot_orientations(axes, angles, axes0, angles0, phase, out=out)
    print(f"Saved pole figure to {out}.")


if __name__ == "__main__":
    app()
