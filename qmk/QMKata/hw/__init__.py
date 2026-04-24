"""
MCU hardware profile registry.

Keyboard classes declare their MCU by name (e.g. "STM32F401xC"); the
registry maps those names to the silicon-fact profile so host code
can look up flash sector layout, RAM regions, etc. without querying
firmware at runtime (the data is static per part number).

Usage:
    from qmk.QMKata import hw
    profile = hw.get("STM32F401xC")
    for sector in profile.flash_sectors:
        ...
"""

from .mcu import FlashSector, McuProfile, RamRegion
from . import stm32f401xc

_REGISTRY = {
    stm32f401xc.PROFILE.name: stm32f401xc.PROFILE,
}


def get(mcu_name: str):
    """Return McuProfile for the given MCU name, or None if unknown."""
    return _REGISTRY.get(mcu_name)


def register(profile: McuProfile) -> None:
    """Add a new MCU profile to the registry (for tests or out-of-tree MCUs)."""
    _REGISTRY[profile.name] = profile


__all__ = ["FlashSector", "McuProfile", "RamRegion", "get", "register"]
