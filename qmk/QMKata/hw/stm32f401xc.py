"""
STM32F401xC — 256 KB flash, 64 KB SRAM, Cortex-M4F.

Source: ST RM0368 (STM32F401xB/C/D/E reference manual), section 3.3
(embedded flash memory / sector organization) and chapter 2 (memory
map). Confirmed matches ChibiOS linker script
platforms/chibios/boards/common/ld/STM32F401xC.ld which sets
f4xx_flash_size=256k and f4xx_ram1_size=64k.

No CCM RAM on F401 (that region exists only on F405/F407/F41x/F42x/F43x).
"""

from .mcu import FlashSector, McuProfile, RamRegion


PROFILE = McuProfile(
    name="STM32F401xC",
    core="cortex-m4",
    flash_total=256 * 1024,
    flash_sectors=(
        FlashSector(0, 0x08000000, 16 * 1024),
        FlashSector(1, 0x08004000, 16 * 1024),
        FlashSector(2, 0x08008000, 16 * 1024),
        FlashSector(3, 0x0800C000, 16 * 1024),
        FlashSector(4, 0x08010000, 64 * 1024),
        FlashSector(5, 0x08020000, 128 * 1024),
    ),
    ram_regions=(
        RamRegion("SRAM", 0x20000000, 64 * 1024),
    ),
)
