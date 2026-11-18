"""Одиниці вимірювання: метрична та англійська системи (ФМ-10).

Сервер зберігає фізичні величини в метричних одиницях і перетворює їх
у систему, обрану користувачем, лише під час відповіді.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.models.enums import MeasurementSystem

FEET_PER_METRE = Decimal("3.28084")
ONE_DECIMAL = Decimal("0.1")


@dataclass(frozen=True)
class Quantity:
    """Значення з одиницею виміру."""

    value: Decimal
    unit: str


def metres_to_feet(metres: Decimal) -> Decimal:
    """Довжина: метри -> фути."""
    return metres * FEET_PER_METRE


def feet_to_metres(feet: Decimal) -> Decimal:
    """Довжина: фути -> метри."""
    return feet / FEET_PER_METRE


def celsius_to_fahrenheit(celsius: Decimal) -> Decimal:
    """Температура: °C -> °F."""
    return celsius * 9 / 5 + 32


def fahrenheit_to_celsius(fahrenheit: Decimal) -> Decimal:
    """Температура: °F -> °C."""
    return (fahrenheit - 32) * 5 / 9


def length(metres: Decimal, system: MeasurementSystem) -> Quantity:
    """Довжина в обраній системі, округлена до 0,1."""
    if system == MeasurementSystem.IMPERIAL:
        return Quantity(_round(metres_to_feet(metres)), "ft")
    return Quantity(_round(metres), "m")


def temperature(celsius: Decimal, system: MeasurementSystem) -> Quantity:
    """Температура в обраній системі, округлена до 0,1."""
    if system == MeasurementSystem.IMPERIAL:
        return Quantity(_round(celsius_to_fahrenheit(celsius)), "°F")
    return Quantity(_round(celsius), "°C")


def _round(value: Decimal) -> Decimal:
    return value.quantize(ONE_DECIMAL, rounding=ROUND_HALF_UP)
