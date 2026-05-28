# Cross-Compiler Setup

QMKata uses the ARM GCC cross-compiler to build SRAM modules and dynamically-loaded functions for the keyboard's Cortex-M4 MCU. This document covers installation and configuration.

## What You Need

The `arm-none-eabi` toolchain provides:

| Tool | Purpose |
|------|---------|
| `arm-none-eabi-gcc` | Compile C to ARM machine code |
| `arm-none-eabi-ld` | Link object files |
| `arm-none-eabi-nm` | List symbols (for firmware symbol resolution) |
| `arm-none-eabi-objcopy` | Convert ELF to raw binary |
| `arm-none-eabi-objdump` | Disassemble and inspect binaries |
| `arm-none-eabi-readelf` | Inspect ELF headers |

## Windows

1. Download from [ARM Developer - GNU Toolchain](https://developer.arm.com/downloads/-/gnu-rm)
2. Choose the **Windows** release (`.zip` or installer)
3. Extract to a permanent location, e.g., `C:\gcc-arm-none-eabi\`
4. Add the `bin` directory to your system PATH:
   - Settings → System → About → Advanced system settings
   - Environment Variables → Path → Edit → New
   - Add: `C:\gcc-arm-none-eabi\bin`
5. Restart your terminal

## Linux

### Ubuntu/Debian

```bash
sudo apt install gcc-arm-none-eabi
```

### Fedora

```bash
sudo dnf install arm-none-eabi-gcc
```

### Arch Linux

```bash
sudo pacman -S arm-none-eabi-gcc
```

### Other

Download from [GNU Arm Embedded Toolchain](https://developer.arm.com/downloads/-/gnu-rm), extract, and add `bin/` to your PATH.

## Verification

Open a new terminal and run:

```bash
arm-none-eabi-gcc --version
arm-none-eabi-nm --version
arm-none-eabi-objcopy --version
```

All should report a version without errors.

## Configure QMKata

### Set TOOLCHAIN path

Each keyboard model defines a `TOOLCHAIN` dict. Edit your keyboard's `.py` file in `qmk/QMKata/keyboards/` and set the `path`:

```python
TOOLCHAIN = {
    "path": "C:\\gcc-arm-none-eabi\\bin\\",  # Windows
    # "path": "/usr/bin/",                    # Linux (package install)
    "options": [...],
    "include_base": "",
    "includes": ["quantum/", "platforms/", ...],
}
```

Or pass the firmware path at runtime:

```bash
python QMKata.py --firmware-path /path/to/keychron_qmk_firmware
```

### Verify

In QMKata, go to the **kbsm modules** tab, browse to a `.c` source file, and click **Build**. A successful build confirms the toolchain is working.
