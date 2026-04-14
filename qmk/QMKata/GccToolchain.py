import subprocess, os, fnmatch, glob as _glob

try:
    from elftools.elf.elffile import ELFFile
except ImportError:
    print("I: elftools not installed, run: pip install pyelftools")


class GccToolchain:
    @staticmethod
    def find_toolchain_path():
        """Auto-discover arm-none-eabi GCC toolchain on PATH.
        Returns (path, prefix) where prefix is e.g. 'arm-none-eabi-'."""
        import shutil

        gcc = shutil.which("arm-none-eabi-gcc")
        if gcc:
            return os.path.dirname(gcc) + os.sep, "arm-none-eabi-"
        return "", ""

    @staticmethod
    def find_build_obj_src(firmware_path):
        """Auto-discover the most recently modified .build/obj_keychron*/src/ dir."""
        pattern = os.path.join(firmware_path, ".build", "obj_keychron*", "src")
        candidates = _glob.glob(pattern)
        if not candidates:
            return None
        candidates.sort(key=os.path.getmtime, reverse=True)
        return candidates[0]

    def __init__(self, toolchain_config=None, firmware_path=None):
        self.debug = False
        if self.debug:
            print(toolchain_config)

        toolchain_path = ""
        self.compiler_options = CompilerOptions()
        if toolchain_config:
            toolchain_path = toolchain_config.get("path", "")
            self.compiler_options.options(toolchain_config.get("options", []))

            # resolve include_base: prefer firmware_path, fall back to config
            include_base = toolchain_config.get("include_base", "")
            if firmware_path:
                include_base = firmware_path + os.sep
            self.compiler_options.include_base(include_base)

            includes = list(toolchain_config.get("includes", []))
            # auto-discover .build/obj_*/src/ and prepend it
            if firmware_path:
                build_obj_src = self.find_build_obj_src(firmware_path)
                if build_obj_src:
                    # make it relative to firmware_path for include_base joining
                    rel = os.path.relpath(build_obj_src, firmware_path)
                    includes.insert(0, rel + os.sep)
            self.compiler_options.includes(includes)

        # resolve toolchain path: prefer config, fall back to auto-discover on PATH
        toolchain_prefix = ""
        if not toolchain_path:
            toolchain_path, toolchain_prefix = self.find_toolchain_path()

        self.toolchain_path = toolchain_path
        self.tool_names = ["gcc", "objcopy", "objdump"]  # todo extend as needed
        self.tool = {}
        self.triplet = {}
        exe_extension = ".exe" if os.name == "nt" else ""
        try:
            for file in os.listdir(toolchain_path):
                for tool_name in self.tool_names:
                    if toolchain_prefix:
                        # when prefix known, match exactly (e.g. arm-none-eabi-gcc)
                        expected = f"{toolchain_prefix}{tool_name}{exe_extension}"
                        if file != expected:
                            continue
                    else:
                        # legacy: scan for cross-compiler pattern or any match
                        is_cross = fnmatch.fnmatch(
                            file, f"*-*-*-{tool_name}{exe_extension}"
                        )
                        is_any = fnmatch.fnmatch(file, f"*{tool_name}{exe_extension}")
                        if not (is_cross or (is_any and tool_name not in self.tool)):
                            continue
                    if tool_name == "gcc":
                        parts = file.replace(exe_extension, "").split("-")
                        if len(parts) >= 4:  # e.g. arm-none-eabi-gcc
                            self.triplet["arch"] = parts[0]
                            self.triplet["vendor"] = parts[1]
                            self.triplet["os"] = parts[2]
                    self.tool[tool_name] = self.toolchain_path + file
        except:
            print(f"I: {toolchain_path} invalid")
            raise Exception("invalid toolchain path")

        if not all(tool in self.tool for tool in self.tool_names):
            print(f"I: toolchain incomplete")
            raise Exception("invalid toolchain path")

        if self.debug:
            print(f"toolchain: {self.triplet} {self.tool}")

    def compile(self, source_file, output_file, compiler_options=None):
        if compiler_options is None:
            compiler_options = self.compiler_options
        # compile command
        gcc = self.tool["gcc"]
        compiler_options_str = (
            compiler_options.options() + compiler_options.includes() + "-o "
        )

        compile_command = [gcc]
        compile_command.extend(compiler_options_str.split())
        compile_command.append(output_file)
        compile_command.append(source_file)
        if self.debug:
            print(f"{compile_command}")
        try:
            result = subprocess.run(
                compile_command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if self.debug:
                print(f"compilation ok")
            return True
        except subprocess.CalledProcessError as e:
            print(f"E: compilation nok: {e.stderr.decode()}")
            return False

    def elf2bin(self, elf_file, bin_file=""):
        if not bin_file:
            bin_file = elf_file.replace(".elf", ".bin")
        objcopy = self.tool["objcopy"]
        objcopy_options = "-O binary"
        objcopy_command = [objcopy]
        objcopy_command.extend(objcopy_options.split())
        objcopy_command.append(elf_file)
        objcopy_command.append(bin_file)
        try:
            result = subprocess.run(
                objcopy_command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if self.debug:
                print(f"objcopy ok")
            return True
        except subprocess.CalledProcessError as e:
            print(f"E: objcopy nok: {e.stderr.decode()}")
        return False

    def load_elf(self, elf_file):
        return GccElfFile(elf_file)

    def disasm(self, elf_file):
        print("=" * 80)
        objdump = self.tool["objdump"]
        objdump_options = "-d"
        objdump_command = [objdump]
        objdump_command.extend(objdump_options.split())
        objdump_command.append(elf_file)
        try:
            result = subprocess.run(
                objdump_command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            print(result.stdout.decode())
        except subprocess.CalledProcessError as e:
            print(f"E: objdump nok: {e.stderr.decode()}")


class CompilerOptions:
    def __init__(self, base_path="", options="", includes=""):
        self.debug = False
        self.base_path = base_path
        self.compiler_options = includes
        self.compiler_includes = options

    def include_base(self, base_path=""):
        if base_path:
            self.base_path = base_path
        return self.base_path

    def includes(self, path_list=[]):
        for path in path_list:
            if self.debug:
                print(f"include: {path}")
            if path.startswith("/") or path.startswith("\\"):
                self.compiler_includes += f"-I {path} "
            else:
                self.compiler_includes += f"-I {self.base_path}{path} "
        return self.compiler_includes

    def options(self, option_list=[]):
        for arg in option_list:
            if self.debug:
                print(f"option: {arg}")
            self.compiler_options += f"{arg} "
        return self.compiler_options


class GccElfFile:
    def __init__(self, elf_file):
        self.elf_file = elf_file
        self.elf = ELFFile(open(elf_file, "rb"))
        print(f"elf:{self.elf}")

        self.data = {}
        self.data["text"] = self.load_text()
        self.data["rodata"] = self.load_rodata()

    def load_text(self):
        text = {}
        for section in self.elf.iter_sections():
            if section.name.startswith(".text"):
                text_symbol = section.name.split(".")
                try:
                    text[text_symbol[2]] = section.data()
                except:
                    pass
        return text

    def load_rodata(self):
        rodata = {}
        for section in self.elf.iter_sections():
            if section.name.startswith(".rodata"):
                rodata_symbol = section.name.split(".")
                try:
                    rodata[rodata_symbol[2]] = section.data()
                except:
                    pass
        return rodata

    def print_sections(self):
        for section in self.elf.iter_sections():
            if section.name.startswith(".debug"):
                continue
            print("=" * 80)
            print(f"section {section.name} {section.header}")
            print("-" * 80)
            print(section.data().hex(" "))
            print(section.data().decode("utf-8", errors="ignore"))

    def print_segments(self):
        for segment in self.elf.iter_segments():
            print(f"segment {segment}")


if __name__ == "__main__":
    toolchain = GccToolchain()
    toolchain.compile("exec.c", "exec.elf")
    toolchain.elf2bin("exec.elf")

    elf = toolchain.load_elf("exec.elf")

    data = None
    with open("exec.bin", "rb") as f:
        data = f.read()
        print(data.hex(" "))

    elf = toolchain.load_elf("exec.elf")
    elf.print_segments()
    elf.print_sections()

    print("=" * 80)
    print("text data:")
    for sym in elf.data["text"]:
        print(f"{sym}: {elf.data['text'][sym].hex(' ')}")

    print("rodata data:")
    for sym in elf.data["rodata"]:
        print(f"{sym}: {elf.data['rodata'][sym].hex(' ')}")

    toolchain.disasm("exec.elf")
