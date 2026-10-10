"""Asignación de puertos dentro del rango configurado."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.errors import PortRangeExhausted


@dataclass(frozen=True, slots=True)
class PortUsage:
    used: int
    total: int
    range_start: int
    range_end: int

    @property
    def free(self) -> int:
        return self.total - self.used


class PortAllocator:
    def __init__(self, port_range: range) -> None:
        if len(port_range) == 0:
            raise ValueError("El rango de puertos está vacío")
        self._range = port_range

    def choose(self, used: set[int]) -> int:
        """Primer puerto libre del rango. Pensado para llamarse dentro de la transacción."""
        for port in self._range:
            if port not in used:
                return port
        raise PortRangeExhausted(
            f"No quedan puertos libres en el rango {self._range.start}-{self._range.stop - 1} "
            f"({len(self._range)} en uso). Elimina alguna redirección o amplía el rango."
        )

    def usage(self, used: set[int]) -> PortUsage:
        in_range = sum(1 for p in used if p in self._range)
        return PortUsage(
            used=in_range,
            total=len(self._range),
            range_start=self._range.start,
            range_end=self._range.stop - 1,
        )
