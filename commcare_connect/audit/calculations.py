from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

_REGISTRY: list[AuditCalculation] = []


@dataclass
class CalculationResult:
    name: str
    label: str
    value: Any
    has_sufficient_data: bool
    in_range: bool
    numerator: int | None = None
    denominator: int | None = None

    def to_dict(self) -> dict:
        d = {
            "value": self.value,
            "has_sufficient_data": self.has_sufficient_data,
            "in_range": self.in_range,
            "label": self.label,
        }
        if self.numerator is not None:
            d["numerator"] = self.numerator
        if self.denominator is not None:
            d["denominator"] = self.denominator
        return d


class AuditCalculation(ABC):
    """Base class for audit calculations.

    Subclasses declare a ``name`` and ``label`` and implement :meth:`compute`,
    returning ``(value, sample_size)``. The base class handles the
    "insufficient data" short-circuit and the bounds check, so concrete
    subclasses don't repeat that boilerplate.

    Tuning knobs (override as class attributes):

    - ``min_sample_size``: if the reported sample size is less than this,
      ``has_sufficient_data`` is False and the result is considered in-range
      by convention (no actionable data).
    - ``lower_bound`` / ``upper_bound``: inclusive acceptability range for
      the value (``lower_bound <= value <= upper_bound``). Either may be
      ``None`` to disable that side.
    """

    name: ClassVar[str]
    label: ClassVar[str]
    tooltip: ClassVar[str] = ""
    is_percentage: ClassVar[bool] = False
    min_sample_size: ClassVar[int] = 1
    lower_bound: ClassVar[float | None] = None
    upper_bound: ClassVar[float | None] = None

    @abstractmethod
    def compute(self, opportunity_access, period_start, period_end) -> tuple[Any, int]:
        """Return ``(value, sample_size)``. ``value`` may be ``None`` when
        ``sample_size == 0``.
        """

    def run(self, opportunity_access, period_start, period_end) -> CalculationResult:
        value, sample_size = self.compute(opportunity_access, period_start, period_end)
        has_sufficient_data = sample_size >= self.min_sample_size
        if not has_sufficient_data:
            return CalculationResult(
                name=self.name,
                label=self.label,
                value=None,
                has_sufficient_data=False,
                in_range=True,
            )
        numerator = None
        denominator = None
        if self.is_percentage and value is not None:
            denominator = sample_size
            numerator = round(value * sample_size / 100)
        return CalculationResult(
            name=self.name,
            label=self.label,
            value=value,
            has_sufficient_data=True,
            in_range=self._in_range(value),
            numerator=numerator,
            denominator=denominator,
        )

    def _in_range(self, value) -> bool:
        if self.lower_bound is not None and value < self.lower_bound:
            return False
        if self.upper_bound is not None and value > self.upper_bound:
            return False
        return True


def register_calculation(cls):
    """Class decorator: instantiate ``cls`` once and add the instance to the registry."""
    _REGISTRY.append(cls())
    return cls


def get_registered_calculations() -> list[AuditCalculation]:
    return list(_REGISTRY)
