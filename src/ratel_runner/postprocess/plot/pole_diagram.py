from importlib.util import find_spec
from pathlib import Path
import yaml
from rich import print
import typer

from ...helper.utilities import run_once


@run_once
def check_imports():
    missing = []
    for module in ['matplotlib', 'pyvista', 'yaml', 'orix', 'diffpy', 'numpy']:
        if find_spec(module) is None:
            missing.append(module)
    if missing:
        raise ModuleNotFoundError(
            f"Missing required modules for pole diagram plotting: {', '.join(missing)}. "
            "Please install the 'ratel-impm-press[pole-diagram]' extra to use this feature."
        )


@run_once
def import_all():
    global plt, pv, Figure, np
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure
    import pyvista as pv
    import numpy as np
    global Phase, Lattice, Structure, Orientation, Misorientation, symmetry, Miller, Vector3d
    from orix.crystal_map import Phase
    from diffpy.structure import Lattice, Structure
    from orix.quaternion import Orientation, Misorientation, symmetry
    from orix.vector import Miller, Vector3d
    import orix.plot


check_imports()


app = typer.Typer()


def vec_rotate(n, theta, v):
    n_dot_v = np.einsum("ij,ij->i", n, v)
    cos_theta = np.cos(theta)
    n_cross_v = np.cross(n, v)
    v_rot = cos_theta[:, None] * v + (np.sin(theta))[:, None] * n_cross_v + (n_dot_v * (1 - cos_theta))[:, None] * n
    return v_rot


def read_mesh(file, time_step=0):
    """Read a mesh from a file."""
    reader: pv.XdmfReader = pv.get_reader(file)  # type: ignore
    reader.set_active_time_point(time_step)
    reader.disable_all_point_arrays()
    reader.enable_point_array("material")
    reader.enable_point_array("elastic parameters")
    reader.enable_point_array("model state")
    mesh: pv.DataSet = reader.read()
    grains = mesh.threshold(1.5, scalars='material', method='upper', preference='point')
    del mesh
    return grains


def pole_plot_bounds(
    poles,
    resolution: float = 1,
    sigma: float = 5,
    log: bool = False,
):
    from orix import measure  # pep8-ignore
    hist, _ = measure.pole_density_function(
        poles,
        resolution=resolution,
        sigma=sigma,
        log=log,
        hemisphere="upper",
    )
    vmin = hist.min()
    vmax = hist.max()
    hist, _ = measure.pole_density_function(
        poles,
        resolution=resolution,
        sigma=sigma,
        log=log,
        hemisphere="lower",
    )
    vmin = min(vmin, hist.min())
    vmax = max(vmax, hist.max())
    return vmin, vmax


def compute_poles(mesh):
    props = np.asarray(mesh.point_data["elastic parameters"])
    state = np.asarray(mesh.point_data["model state"])
    npts = props.shape[0]
    print(f"Computing pole orientations for {npts} points...")
    F = state.reshape((npts, 3, 3)) + np.eye(3)
    Finv = np.linalg.inv(F)
    J = np.linalg.det(F)
    n0 = props[:, 21:24]
    theta0 = props[:, 24]
    V = np.zeros_like(n0)
    V[:, 2] = 1.
    ab_normal0 = vec_rotate(n0, theta0, V)
    ab_normal = J[:, None] * np.einsum("ijk,ij->ik", Finv, ab_normal0)
    vab0 = Vector3d(ab_normal0)
    vab = Vector3d(ab_normal)
    axes = vab0.cross(vab)
    axes /= axes.norm
    angles = vab0.angle_with(vab)
    print(f"Computed pole orientations for {axes.shape[0]} points.")
    return axes, angles, Vector3d(n0), theta0


@app.command()
def pole_diagram(
    run_dir: Path,
    swarm_file: str = "swarm.xdmf",
    time_step: int = 0,
    log: bool = False,
    out: Path = Path("orientations.png"),
):
    """Plot pole diagrams from swarm data."""
    import_all()

    plt.rcParams.update(
        {
            "figure.figsize": (5, 5),
            "lines.markersize": 2,
            "font.size": 15,
            "axes.grid": False,
        }
    )

    monoclinic = Phase(
        point_group=symmetry.C2h,
        structure=Structure(lattice=Lattice(6.53, 11.03, 7.35, 90, 102.689, 90)),
    )

    triclinic = Phase(
        point_group=symmetry.C1,
        structure=Structure(lattice=Lattice(9.015, 9.0325, 6.825, 108.65, 91.98, 119.94)),
    )

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
        a = grain_options['a']
        b = grain_options['b']
        c = grain_options['c']
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
    except (KeyError, ValueError):
        # guess
        if "monoclinic" in f'{run_dir}':
            phase = monoclinic
            print(f"Using monoclinic phase with lattice parameters: {phase.structure.lattice}")
        else:
            phase = triclinic
            print(f"Using triclinic phase with lattice parameters: {phase.structure.lattice}")

    axes, angles, axes0, angles0 = compute_poles(read_mesh(run_dir / swarm_file, time_step=time_step))

    O0 = Orientation.from_axes_angles(axes0, angles0, symmetry=phase.point_group)
    g = Miller(hkl=[0, 0, 1], phase=phase).symmetrise(unique=True)
    poles0: Vector3d = O0.inv().outer(g, lazy=True, chunk_size=200000)  # type: ignore
    poles: Vector3d = (Misorientation.from_axes_angles(axes, angles) * O0).inv().outer(  # type: ignore
        g,  # type: ignore
        lazy=True,
        chunk_size=200000
    )  # type: ignore

    w, h = plt.rcParams["figure.figsize"]

    plot_args = dict(resolution=1, sigma=5, log=log)

    vmin, vmax = pole_plot_bounds(poles0, **plot_args)  # type: ignore
    vmin2, vmax2 = pole_plot_bounds(poles, **plot_args)  # type: ignore
    vmin = min(vmin, vmin2)
    vmax = max(vmax, vmax2)

    out_init = out.parent / f"{out.stem}_initial{out.suffix}"
    out_deformed = out.parent / f"{out.stem}_deformed{out.suffix}"
    fig1: Figure = poles0.pole_density_function(
        **plot_args,  # type: ignore
        hemisphere='both',
        colorbar=False,
        vmin=vmin, vmax=vmax,
        axes_labels=["X", "Y", None],  # type: ignore
        return_figure=True,
        figure_kwargs={"figsize": (2 * w, h)}
    )  # type: ignore
    fig1.suptitle("Initial")
    fig1.tight_layout()
    fig1.colorbar(fig1.axes[-1].collections[-1], ax=fig1.axes,
                  label='log(MRD)' if plot_args['log'] else 'MRD')  # type: ignore
    fig1.savefig(out_init, dpi=300)
    print(f"Saved initial pole figure to {out_init}.")

    fig2: Figure = poles.pole_density_function(
        **plot_args,  # type: ignore
        hemisphere='both',
        colorbar=False,
        vmin=vmin, vmax=vmax,
        axes_labels=["X", "Y", None],  # type: ignore
        return_figure=True,
        figure_kwargs={"figsize": (2 * w, h)}
    )  # type: ignore
    fig2.suptitle("Deformed")
    fig2.tight_layout()
    fig2.colorbar(fig2.axes[-1].collections[-1], ax=fig2.axes,
                  label='log(MRD)' if plot_args['log'] else 'MRD')  # type: ignore
    fig2.savefig(out_deformed, dpi=300)
    print(f"Saved deformed pole figure to {out_deformed}.")
    plt.close()


if __name__ == "__main__":
    app()
