from enum import Enum
from dataclasses import dataclass
from abc import abstractmethod, ABC


class BoundaryType(Enum):
    SLIP_FREE_ENDS = "slip_free_ends"
    CLAMPED = "clamped"
    CONTACT = "contact"


class PressBoundary(ABC):
    """Dataclass for press boundary condition parameters."""
    bc_type: BoundaryType

    def __init__(self, bc_type: BoundaryType, **kwargs):
        self.bc_type = bc_type

    @classmethod
    def create(cls, bc_type: BoundaryType, **kwargs) -> 'PressBoundary':
        if bc_type == BoundaryType.CONTACT:
            return PressBoundaryContact(**kwargs)
        elif bc_type == BoundaryType.CLAMPED:
            return PressBoundaryClamped(**kwargs)
        elif bc_type == BoundaryType.SLIP_FREE_ENDS:
            return PressBoundarySlipFreeEnds(**kwargs)
        else:
            raise ValueError(f"Unknown boundary condition type: {bc_type}")

    @property
    @abstractmethod
    def snes_options(self) -> str:
        pass

    @abstractmethod
    def options(self, center, radius, height, load_fraction) -> str:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass


class PressBoundaryContact(PressBoundary):
    friction_coefficient: float

    def __init__(self, friction_coefficient: float = 0.5, **kwargs):
        super().__init__(bc_type=BoundaryType.CONTACT, **kwargs)
        self.friction_coefficient = friction_coefficient

    @property
    def snes_options(self) -> str:
        if not hasattr(self, '_snes_options'):
            self._snes_options = '\n'.join([
                "# SNES options for contact boundary conditions",
                "snes:",
                "  monitor:",
                "  max_it: 15",
                "  rtol: 1e-6",
                "augmented_lagrangian_inner_snes:",
                "  linesearch:",
                "    type: bt",
                "    monitor:",
                "  max_it: 20",
                "  monitor:",
                "  ksp:",
                "    ew:",
                "    ew_version: 3",
                "    ew_rtol0: 1e-4",
                "    ew_rtolmax: 1e-4",
                ""
            ])
        return self._snes_options

    def options(self, center, radius, height, load_fraction) -> str:
        if self.friction_coefficient == 0.0:
            friction_options = "\n".join([
                "    friction:",
                "      type: none",
            ])
        else:
            friction_options = '\n'.join([
                "    friction:",
                "      type: coulomb",
                f"      kinetic: {self.friction_coefficient}",
                "      penalty_min: 10",
                "      penalty_max: 5e3",
                "      penalty_scale: 2",
            ])
        penalty_ops = '\n'.join([
            "    penalty_min: 100",
            "    penalty_max: 5e4",
            "    penalty_scale: 4",
        ])
        ops = '\n'.join([
            "bc:",
            "  allow_no_clamp:",
            "  contact: 1,2,3,4,5,6",
            "  # Bottom",
            "  contact_1:",
            "    shape: platen",
            "    normal: 0,0,1",
            f"    center: {center[0]},{center[1]},{center[2]}",
            penalty_ops,
            "    type: augmented_lagrangian",
            friction_options,
            "  # Top, compressing 40%",
            "  contact_2:",
            "    shape: platen",
            penalty_ops,
            "    normal: 0,0,-1",
            f"    center: {center[0]},{center[1]},{center[2]+height}",
            f"    distance: {load_fraction * height} # load_fraction * height",
            "    type: augmented_lagrangian",
            friction_options,
            "  # Outside",
            "",
        ])
        for i in range(3, 7):
            ops += '\n'.join([
                f"  contact_{i}:",
                "    shape: cylinder",
                "    axis: 0,0,1",
                f"    radius: {radius}",
                f"    center: {center[0]},{center[1]},{center[2]}",
                "    inside:",
                penalty_ops,
                "    type: augmented_lagrangian",
                friction_options,
                "",
            ])
        return ops

    @property
    def name(self) -> str:
        friction_str = f"mu{self.friction_coefficient}" if self.friction_coefficient != 0.0 else "frictionless"
        return f"{self.bc_type.value}_{friction_str}"

    def __str__(self) -> str:
        friction_str = f"Coulomb friction with μ={self.friction_coefficient}" if self.friction_coefficient != 0.0 else "frictionless"
        return f"Contact Boundaries, {friction_str}"


class PressBoundaryClamped(PressBoundary):
    def __init__(self, **kwargs):
        super().__init__(bc_type=BoundaryType.CLAMPED, **kwargs)

    @property
    def snes_options(self) -> str:
        if not hasattr(self, '_snes_options'):
            self._snes_options = '\n'.join([
                "# SNES options for slip/clamped boundary conditions",
                "snes:",
                "  linesearch:",
                "    type: bisection",
                "    monitor:",
                "  max_it: 20",
                "  monitor:",
                "  ksp:",
                "    ew:",
                "    ew_version: 3",
                "    ew_rtol0: 1e-4",
                "    ew_rtolmax: 1e-4",
                "",
            ])
        return self._snes_options

    def options(self, center, radius, height, load_fraction) -> str:
        return '\n'.join([
            "bc:",
            "  clamp: 1,2",
            "  # Clamped displacement for top and bottom",
            "  clamp_2:",
            f"    translate: 0,0,{-load_fraction * height} # -load_fraction * height",
            "  # Prevent x,y expansion beyond the die boundary",
            "  slip: 3,4,5,6",
            "  slip_3:",
            "    components: 0,1",
            "  slip_4:",
            "    components: 0,1",
            "  slip_5:",
            "    components: 0,1",
            "  slip_6:",
            "    components: 0,1",
            "",
        ])

    @property
    def name(self) -> str:
        return f"{self.bc_type.value}"

    def __str__(self) -> str:
        return "Clamped Boundaries"


class PressBoundarySlipFreeEnds(PressBoundary):
    def __init__(self, **kwargs):
        super().__init__(bc_type=BoundaryType.SLIP_FREE_ENDS, **kwargs)

    @property
    def snes_options(self) -> str:
        if not hasattr(self, '_snes_options'):
            self._snes_options = '\n'.join([
                "# SNES options for slip/clamped boundary conditions",
                "snes:",
                "  linesearch:",
                "    type: bisection",
                "    monitor:",
                "  max_it: 20",
                "  monitor:",
                "  ksp:",
                "    ew:",
                "    ew_version: 3",
                "    ew_rtol0: 1e-4",
                "    ew_rtolmax: 1e-4",
                "",
            ])
        return self._snes_options

    def options(self, center, radius, height, load_fraction) -> str:
        return '\n'.join([
            "bc:",
            "  slip: 1,2,3,4,5,6",
            "  # Allow x,y displacement for top and bottom, prescribe z displacement",
            "  slip_1:",
            "    components: 2",
            "  slip_2:",
            "    components: 2",
            f"    translate: {-load_fraction * height} # -load_fraction * height",
            "  slip_3:",
            "    components: 0,1",
            "  slip_4:",
            "    components: 0,1",
            "  slip_5:",
            "    components: 0,1",
            "  slip_6:",
            "    components: 0,1",
            "",
        ])

    @property
    def name(self) -> str:
        return f"{self.bc_type.value}"

    def __str__(self) -> str:
        return "Clamped Wall Boundary with Free-Slip Boundaries on Top and Bottom"
