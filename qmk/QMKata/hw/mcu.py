"""
MCU hardware profile data structures.

A McuProfile captures the static facts about an MCU: flash layout,
RAM regions, core family. These are silicon-level details that never
change for a given part number, so we store them here rather than
querying the firmware at runtime.

Keyboard-level choices (which sectors the module loader claims, slot
size, etc.) live on the keyboard class, not in the MCU profile.
"""

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class FlashSector:
    """One erasable flash sector. STM32F4 has variable sector sizes."""
    index: int
    base: int
    size: int

    @property
    def end(self) -> int:
        return self.base + self.size

    def contains(self, addr: int) -> bool:
        return self.base <= addr < self.end


@dataclass(frozen=True)
class RamRegion:
    """A contiguous RAM region. Names follow ST's datasheet conventions:
    SRAM, SRAM1, SRAM2, CCM, BKPSRAM. Not all MCUs have all regions.
    """
    name: str
    base: int
    size: int

    @property
    def end(self) -> int:
        return self.base + self.size


@dataclass(frozen=True)
class McuProfile:
    name: str                                # e.g. "STM32F401xC"
    core: str                                # e.g. "cortex-m4"
    flash_total: int
    flash_sectors: Tuple[FlashSector, ...]
    ram_regions: Tuple[RamRegion, ...]

    def sector_containing(self, addr: int) -> Optional[FlashSector]:
        for s in self.flash_sectors:
            if s.contains(addr):
                return s
        return None

    def sector_by_index(self, idx: int) -> Optional[FlashSector]:
        for s in self.flash_sectors:
            if s.index == idx:
                return s
        return None

    def ram_by_name(self, name: str) -> Optional[RamRegion]:
        for r in self.ram_regions:
            if r.name == name:
                return r
        return None
