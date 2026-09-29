"""Versioned hypotheses; registration never depends on evaluated returns."""

from dataclasses import dataclass
from itertools import product

FAMILIES = ("momentum", "risk_momentum", "reversal", "low_volatility", "breakout")
LOOKBACKS = (10, 20, 40, 60)
SIZES = (1, 3, 5, 10, 20)


@dataclass(frozen=True)
class SelectionSpec:
    family: str
    lookback: int
    size: int

    def __post_init__(self) -> None:
        if self.family not in FAMILIES or self.lookback not in LOOKBACKS or self.size not in SIZES:
            raise ValueError("unregistered selection configuration")

    @property
    def selection_id(self) -> str:
        return f"v1_{self.family}_l{self.lookback}_k{self.size}"


def selection_specs() -> tuple[SelectionSpec, ...]:
    return tuple(SelectionSpec(*values) for values in product(FAMILIES, LOOKBACKS, SIZES))
