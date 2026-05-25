# QMK Tools — Agent Instructions

## Repo Overview

Host-side tooling for Keychron QMK firmware: QMKata GUI, module build
pipeline, SRAM module examples, firmware communication.

## Key Directories

```
qmk/QMKata/
    module_api.h        # ABI header (kbsm_env_t, hook indices, version)
    ModuleBuild.py      # Build pipeline (compile → link → assemble → CRC)
    ModuleTab.py        # QMKata GUI modules tab
    module_linker.ld    # Linker script for module builds
    module_examples/    # Working kbsm SRAM module examples
        kbsm_dyad/      # Hold + single tap → output
        kbsm_holdseq/   # Hold + variable-length sequence → output
        kbsm_autotext/  # Abbreviation expansion
    docs/
        kbsm-agent-instructions.md   # LLM agent guide for generating modules
        authoring-sram-modules.md    # Step-by-step authoring guide
        sram-module-compilation.md  # Build pipeline details
        sram-module-relocation.md    # Relocation + pointer gap explanation
```

## Common Tasks

### Build an SRAM module

```bash
cd ~/qmk/keychron_qmk_firmware
python3 emulator/scripts/build_sram_module.py --feature <name>
```

### Generate a new kbsm module

Read `qmk/QMKata/docs/kbsm-agent-instructions.md` — the complete LLM agent
guide with mandatory patterns, gotchas, and templates.

### Run the QMKata GUI

```bash
python3 qmk/QMKata/QMKata.py
```

## Related Repo

The firmware repo lives at `~/qmk/keychron_qmk_firmware/` (branch `2025q3_q3_max`).
