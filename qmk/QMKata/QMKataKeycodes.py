import os
import hjson


class KeycodeResolver:
    """Resolves QMK keycode names to/from uint16 values.

    Loads keycode definitions from QMK firmware HJSON data files.
    Supports named keycodes (KC_A), raw hex (0x0004), and
    macro expressions (LCTL(KC_A), LT(1, KC_SPC)).
    """

    # QK_* range base addresses (from keycodes.h enum qk_keycode_ranges)
    QK_BASIC = 0x0000
    QK_MODS = 0x0100
    QK_MODS_MAX = 0x1FFF
    QK_MOD_TAP = 0x2000
    QK_MOD_TAP_MAX = 0x3FFF
    QK_LAYER_TAP = 0x4000
    QK_LAYER_TAP_MAX = 0x4FFF
    QK_LAYER_MOD = 0x5000
    QK_LAYER_MOD_MAX = 0x51FF
    QK_TO = 0x5200
    QK_TO_MAX = 0x521F
    QK_MOMENTARY = 0x5220
    QK_MOMENTARY_MAX = 0x523F
    QK_DEF_LAYER = 0x5240
    QK_DEF_LAYER_MAX = 0x525F
    QK_TOGGLE_LAYER = 0x5260
    QK_TOGGLE_LAYER_MAX = 0x527F
    QK_ONE_SHOT_LAYER = 0x5280
    QK_ONE_SHOT_LAYER_MAX = 0x529F
    QK_ONE_SHOT_MOD = 0x52A0
    QK_ONE_SHOT_MOD_MAX = 0x52BF
    QK_LAYER_TAP_TOGGLE = 0x52C0
    QK_LAYER_TAP_TOGGLE_MAX = 0x52DF

    # Modifier bits for QK_MODS range (OR'd into high byte)
    QK_LCTL = 0x0100
    QK_LSFT = 0x0200
    QK_LALT = 0x0400
    QK_LGUI = 0x0800
    QK_RCTL = 0x1100
    QK_RSFT = 0x1200
    QK_RALT = 0x1400
    QK_RGUI = 0x1800

    # 5-bit packed modifier constants (from modifiers.h)
    MOD_LCTL = 0x01
    MOD_LSFT = 0x02
    MOD_LALT = 0x04
    MOD_LGUI = 0x08
    MOD_RCTL = 0x11
    MOD_RSFT = 0x12
    MOD_RALT = 0x14
    MOD_RGUI = 0x18

    def __init__(self, firmware_path=None):
        self.name_to_value = {}  # "KC_A" -> 0x0004 (includes aliases)
        self.value_to_name = {}  # 0x0004 -> "KC_A" (canonical only)

        if firmware_path:
            self._load_hjson(firmware_path)
        self._register_mod_constants()
        self._register_macros()

    def _load_hjson(self, firmware_path):
        """Load keycodes from HJSON data files, layering versions."""
        data_dir = os.path.join(firmware_path, "data", "constants", "keycodes")
        if not os.path.isdir(data_dir):
            return

        # Collect and sort HJSON files by version then category
        hjson_files = []
        for f in os.listdir(data_dir):
            if f.startswith("keycodes_") and f.endswith(".hjson"):
                hjson_files.append(f)
        # Sort: 0.0.1 before 0.0.2 before 0.0.3, categories within version
        hjson_files.sort()

        for fname in hjson_files:
            fpath = os.path.join(data_dir, fname)
            try:
                with open(fpath, "r") as f:
                    data = hjson.load(f)
                keycodes = data.get("keycodes", {})
                for hex_str, entry in keycodes.items():
                    value = int(hex_str, 16)
                    key = entry.get("key", "")
                    if key:
                        self.name_to_value[key] = value
                        self.value_to_name[value] = key
                    for alias in entry.get("aliases", []):
                        self.name_to_value[alias] = value
            except Exception as e:
                import sys

                print(f"Warning: Failed to load {fname}: {e}", file=sys.stderr)

    def _register_mod_constants(self):
        """Register MOD_* constants so they can be used in macro args."""
        mod_constants = {
            "MOD_LCTL": self.MOD_LCTL,
            "MOD_LSFT": self.MOD_LSFT,
            "MOD_LALT": self.MOD_LALT,
            "MOD_LGUI": self.MOD_LGUI,
            "MOD_RCTL": self.MOD_RCTL,
            "MOD_RSFT": self.MOD_RSFT,
            "MOD_RALT": self.MOD_RALT,
            "MOD_RGUI": self.MOD_RGUI,
        }
        self.name_to_value.update(mod_constants)

    def _register_macros(self):
        """Build macro function lookup table."""
        # Single-arg modifier wrappers: name -> QK_* bits to OR
        self._mod_macros = {
            "LCTL": self.QK_LCTL,
            "LSFT": self.QK_LSFT,
            "LALT": self.QK_LALT,
            "LGUI": self.QK_LGUI,
            "LOPT": self.QK_LALT,
            "LCMD": self.QK_LGUI,
            "LWIN": self.QK_LGUI,
            "RCTL": self.QK_RCTL,
            "RSFT": self.QK_RSFT,
            "RALT": self.QK_RALT,
            "RGUI": self.QK_RGUI,
            "ALGR": self.QK_RALT,
            "ROPT": self.QK_RALT,
            "RCMD": self.QK_RGUI,
            "RWIN": self.QK_RGUI,
            "C": self.QK_LCTL,
            "S": self.QK_LSFT,
            "A": self.QK_LALT,
            "G": self.QK_LGUI,
            "HYPR": self.QK_LCTL | self.QK_LSFT | self.QK_LALT | self.QK_LGUI,
            "MEH": self.QK_LCTL | self.QK_LSFT | self.QK_LALT,
            "LCAG": self.QK_LCTL | self.QK_LALT | self.QK_LGUI,
            "LSG": self.QK_LSFT | self.QK_LGUI,
            "SGUI": self.QK_LSFT | self.QK_LGUI,
            "SCMD": self.QK_LSFT | self.QK_LGUI,
            "SWIN": self.QK_LSFT | self.QK_LGUI,
            "LAG": self.QK_LALT | self.QK_LGUI,
            "RSG": self.QK_RSFT | self.QK_RGUI,
            "RAG": self.QK_RALT | self.QK_RGUI,
            "LCA": self.QK_LCTL | self.QK_LALT,
            "LSA": self.QK_LSFT | self.QK_LALT,
            "RSA": self.QK_RSFT | self.QK_RALT,
            "RCS": self.QK_RCTL | self.QK_RSFT,
            "SAGR": self.QK_RSFT | self.QK_RALT,
        }

        # Single-arg layer macros: name -> (base_addr, mask)
        self._layer_macros = {
            "TO": (self.QK_TO, 0x1F),
            "MO": (self.QK_MOMENTARY, 0x1F),
            "DF": (self.QK_DEF_LAYER, 0x1F),
            "TG": (self.QK_TOGGLE_LAYER, 0x1F),
            "OSL": (self.QK_ONE_SHOT_LAYER, 0x1F),
            "TT": (self.QK_LAYER_TAP_TOGGLE, 0x1F),
        }

        # Mod-tap shortcut macros: name -> MOD_* value
        self._modtap_macros = {
            "LCTL_T": self.MOD_LCTL,
            "RCTL_T": self.MOD_RCTL,
            "CTL_T": self.MOD_LCTL,
            "LSFT_T": self.MOD_LSFT,
            "RSFT_T": self.MOD_RSFT,
            "SFT_T": self.MOD_LSFT,
            "LALT_T": self.MOD_LALT,
            "RALT_T": self.MOD_RALT,
            "ALT_T": self.MOD_LALT,
            "LOPT_T": self.MOD_LALT,
            "ROPT_T": self.MOD_RALT,
            "OPT_T": self.MOD_LALT,
            "ALGR_T": self.MOD_RALT,
            "LGUI_T": self.MOD_LGUI,
            "RGUI_T": self.MOD_RGUI,
            "GUI_T": self.MOD_LGUI,
            "LCMD_T": self.MOD_LGUI,
            "RCMD_T": self.MOD_RGUI,
            "CMD_T": self.MOD_LGUI,
            "LWIN_T": self.MOD_LGUI,
            "RWIN_T": self.MOD_RGUI,
            "WIN_T": self.MOD_LGUI,
            "ALL_T": self.MOD_LCTL | self.MOD_LSFT | self.MOD_LALT | self.MOD_LGUI,
            "MEH_T": self.MOD_LCTL | self.MOD_LSFT | self.MOD_LALT,
            "LCAG_T": self.MOD_LCTL | self.MOD_LALT | self.MOD_LGUI,
            "RCAG_T": self.MOD_RCTL | self.MOD_RALT | self.MOD_RGUI,
            "HYPR_T": self.MOD_LCTL | self.MOD_LSFT | self.MOD_LALT | self.MOD_LGUI,
            "C_S_T": self.MOD_LCTL | self.MOD_LSFT,
            "LSG_T": self.MOD_LSFT | self.MOD_LGUI,
            "SGUI_T": self.MOD_LSFT | self.MOD_LGUI,
            "SCMD_T": self.MOD_LSFT | self.MOD_LGUI,
            "SWIN_T": self.MOD_LSFT | self.MOD_LGUI,
            "LAG_T": self.MOD_LALT | self.MOD_LGUI,
            "RSG_T": self.MOD_RSFT | self.MOD_RGUI,
            "RAG_T": self.MOD_RALT | self.MOD_RGUI,
            "LCA_T": self.MOD_LCTL | self.MOD_LALT,
            "LSA_T": self.MOD_LSFT | self.MOD_LALT,
            "RSA_T": self.MOD_RSFT | self.MOD_RALT,
            "RCS_T": self.MOD_RCTL | self.MOD_RSFT,
            "SAGR_T": self.MOD_RSFT | self.MOD_RALT,
        }

    def _validate_uint16(self, value, expr):
        """Ensure value fits in uint16."""
        if not (0 <= value <= 0xFFFF):
            raise ValueError(f"Value 0x{value:x} from '{expr}' exceeds uint16 range")
        return value

    def resolve(self, expr):
        """Resolve a keycode expression to a uint16 value.

        Accepts:
          - Raw hex: "0x0004"
          - Raw decimal: "4"
          - Named keycode: "KC_A"
          - Modifier wrapper: "LCTL(KC_A)"
          - Layer macro: "TO(1)", "MO(2)"
          - Layer-Tap: "LT(1, KC_SPC)"
          - Mod-Tap: "MT(MOD_LCTL, KC_A)", "LCTL_T(KC_A)"
          - Layer-Mod: "LM(1, MOD_LCTL)"
          - One-shot mod: "OSM(MOD_LSFT)"
          - MOD_* expressions with |: "MOD_LCTL | MOD_LSFT"

        Returns: int (uint16 keycode value)
        Raises: ValueError if expression cannot be resolved
        """
        expr = expr.strip()
        if not expr:
            raise ValueError("Empty expression")

        # Raw hex
        if expr.startswith("0x") or expr.startswith("0X"):
            return self._validate_uint16(int(expr, 16), expr)

        # Raw decimal (only if all digits)
        if expr.isdigit():
            return self._validate_uint16(int(expr), expr)

        # Check for MOD_* bitwise OR expressions (e.g. "MOD_LCTL | MOD_LSFT")
        if "|" in expr and "(" not in expr:
            result = 0
            for part in expr.split("|"):
                result |= self.resolve(part.strip())
            return self._validate_uint16(result, expr)

        # Macro expression: NAME(args)
        paren_idx = expr.find("(")
        if paren_idx != -1:
            if not expr.endswith(")"):
                raise ValueError(f"Unbalanced parentheses: {expr}")
            func_name = expr[:paren_idx].strip()
            args_str = expr[paren_idx + 1 : -1].strip()
            return self._validate_uint16(self._eval_macro(func_name, args_str), expr)

        # Named keycode lookup
        if expr in self.name_to_value:
            return self._validate_uint16(self.name_to_value[expr], expr)

        raise ValueError(f"Unknown keycode: {expr}")

    def _split_args(self, args_str):
        """Split macro arguments respecting nested parentheses."""
        args = []
        depth = 0
        current = []
        for ch in args_str:
            if ch == "," and depth == 0:
                args.append("".join(current).strip())
                current = []
            else:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                current.append(ch)
        if current:
            args.append("".join(current).strip())
        return [a for a in args if a]

    def _eval_macro(self, func_name, args_str):
        """Evaluate a macro expression."""
        args = self._split_args(args_str)

        # Single-arg modifier wrappers: LCTL(kc), S(kc), HYPR(kc), etc.
        if func_name in self._mod_macros:
            if len(args) != 1:
                raise ValueError(f"{func_name}() takes 1 argument, got {len(args)}")
            kc = self.resolve(args[0])
            return self._mod_macros[func_name] | kc

        # Single-arg layer macros: TO(layer), MO(layer), etc.
        if func_name in self._layer_macros:
            if len(args) != 1:
                raise ValueError(f"{func_name}() takes 1 argument, got {len(args)}")
            base, mask = self._layer_macros[func_name]
            layer = self.resolve(args[0])
            return base | (layer & mask)

        # OSM(mod)
        if func_name == "OSM":
            if len(args) != 1:
                raise ValueError(f"OSM() takes 1 argument, got {len(args)}")
            mod = self.resolve(args[0])
            return self.QK_ONE_SHOT_MOD | (mod & 0x1F)

        # LT(layer, kc)
        if func_name == "LT":
            if len(args) != 2:
                raise ValueError(f"LT() takes 2 arguments, got {len(args)}")
            layer = self.resolve(args[0])
            kc = self.resolve(args[1])
            return self.QK_LAYER_TAP | ((layer & 0xF) << 8) | (kc & 0xFF)

        # MT(mod, kc)
        if func_name == "MT":
            if len(args) != 2:
                raise ValueError(f"MT() takes 2 arguments, got {len(args)}")
            mod = self.resolve(args[0])
            kc = self.resolve(args[1])
            return self.QK_MOD_TAP | ((mod & 0x1F) << 8) | (kc & 0xFF)

        # LM(layer, mod)
        if func_name == "LM":
            if len(args) != 2:
                raise ValueError(f"LM() takes 2 arguments, got {len(args)}")
            layer = self.resolve(args[0])
            mod = self.resolve(args[1])
            return self.QK_LAYER_MOD | ((layer & 0xF) << 5) | (mod & 0x1F)

        # Mod-tap shortcuts: LCTL_T(kc), MEH_T(kc), etc.
        if func_name in self._modtap_macros:
            if len(args) != 1:
                raise ValueError(f"{func_name}() takes 1 argument, got {len(args)}")
            mod = self._modtap_macros[func_name]
            kc = self.resolve(args[0])
            return self.QK_MOD_TAP | ((mod & 0x1F) << 8) | (kc & 0xFF)

        raise ValueError(f"Unknown macro: {func_name}()")

    def value_to_display(self, value):
        """Convert a uint16 keycode value to human-readable display string.

        Returns the most readable representation:
        - Named keycode if in value_to_name: "KC_A"
        - Macro decomposition for known ranges: "LCTL(KC_A)", "LT(1, KC_SPC)"
        - Hex fallback: "0x1234"
        """
        # Direct lookup
        if value in self.value_to_name:
            return self.value_to_name[value]

        # QK_MODS range: modifier + basic keycode
        if self.QK_MODS <= value <= self.QK_MODS_MAX:
            mods = (value >> 8) & 0x1F
            basic = value & 0xFF
            basic_name = self.value_to_name.get(basic, f"0x{basic:02x}")
            mod_name = self._mods_to_macro_name(mods)
            if mod_name:
                return f"{mod_name}({basic_name})"
            return f"0x{value:04x}"

        # QK_MOD_TAP range
        if self.QK_MOD_TAP <= value <= self.QK_MOD_TAP_MAX:
            mod = (value >> 8) & 0x1F
            kc = value & 0xFF
            kc_name = self.value_to_name.get(kc, f"0x{kc:02x}")
            # Try to find a shortcut name (LCTL_T, etc.)
            shortcut = self._mod_to_modtap_name(mod)
            if shortcut:
                return f"{shortcut}({kc_name})"
            mod_name = self._mod5_to_name(mod)
            return f"MT({mod_name}, {kc_name})"

        # QK_LAYER_TAP range
        if self.QK_LAYER_TAP <= value <= self.QK_LAYER_TAP_MAX:
            layer = (value >> 8) & 0xF
            kc = value & 0xFF
            kc_name = self.value_to_name.get(kc, f"0x{kc:02x}")
            return f"LT({layer}, {kc_name})"

        # QK_LAYER_MOD range
        if self.QK_LAYER_MOD <= value <= self.QK_LAYER_MOD_MAX:
            layer = (value >> 5) & 0xF
            mod = value & 0x1F
            mod_name = self._mod5_to_name(mod)
            return f"LM({layer}, {mod_name})"

        # Single-arg layer macros
        for name, (base, mask) in self._layer_macros.items():
            max_val = base | mask
            if base <= value <= max_val:
                layer = value & mask
                return f"{name}({layer})"

        # QK_ONE_SHOT_MOD
        if self.QK_ONE_SHOT_MOD <= value <= self.QK_ONE_SHOT_MOD_MAX:
            mod = value & 0x1F
            mod_name = self._mod5_to_name(mod)
            return f"OSM({mod_name})"

        # Fallback
        return f"0x{value:04x}"

    def _mods_to_macro_name(self, mods_5bit):
        """Convert 5-bit packed modifier value to wrapper macro name."""
        mod_combo_to_name = {
            0x01: "LCTL",
            0x02: "LSFT",
            0x04: "LALT",
            0x08: "LGUI",
            0x11: "RCTL",
            0x12: "RSFT",
            0x14: "RALT",
            0x18: "RGUI",
            0x0F: "HYPR",
            0x07: "MEH",
            0x0D: "LCAG",
            0x0A: "LSG",
            0x0C: "LAG",
            0x05: "LCA",
            0x06: "LSA",
            0x1A: "RSG",
            0x1C: "RAG",
            0x16: "RSA",
            0x13: "RCS",
        }
        return mod_combo_to_name.get(mods_5bit)

    def _mod5_to_name(self, mod5):
        """Convert 5-bit packed modifier to name string."""
        simple = {
            0x01: "MOD_LCTL",
            0x02: "MOD_LSFT",
            0x04: "MOD_LALT",
            0x08: "MOD_LGUI",
            0x11: "MOD_RCTL",
            0x12: "MOD_RSFT",
            0x14: "MOD_RALT",
            0x18: "MOD_RGUI",
        }
        if mod5 in simple:
            return simple[mod5]
        # Composite: build with | operator
        # Check right-hand mods (0x1x) before left-hand (0x0x) to avoid
        # greedy mismatch where MOD_LCTL(0x01) steals bits from MOD_RCTL(0x11)
        parts = []
        remaining = mod5
        for bit in [0x18, 0x14, 0x12, 0x11, 0x08, 0x04, 0x02, 0x01]:
            if remaining == 0:
                break
            if (remaining & bit) == bit:
                parts.append(simple[bit])
                remaining &= ~bit
        if parts:
            parts.reverse()  # Display left-hand before right-hand
            return " | ".join(parts)
        return f"0x{mod5:02x}"

    def _mod_to_modtap_name(self, mod5):
        """Find the shortest mod-tap shortcut name for a 5-bit mod value."""
        for name, mod_val in self._modtap_macros.items():
            if mod_val == mod5:
                return name
        return None
