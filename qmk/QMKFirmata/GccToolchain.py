import subprocess, os, fnmatch
try:
    from elftools.elf.elffile import ELFFile
except ImportError:
    print("E: elftools not installed, run: pip install pyelftools")

class GccToolchain:
    def __init__(self, toolchain_path=""):
        self.debug = False
        if not toolchain_path:
            toolchain_path = 'V:\\toolchain\\gcc-arm-none-eabi-10.3-2021.10\\bin\\'
        self.toolchain_path = toolchain_path
        self.tool_names = ["gcc", "objcopy", "objdump"] # todo extend as needed
        self.tool = {}
        self.triplet = {}
        exe_extension = '.exe' if os.name == 'nt' else ''
        try:
            for file in os.listdir(toolchain_path):
                for tool_name in self.tool_names:
                    if fnmatch.fnmatch(file, f"*{tool_name}{exe_extension}"):
                        if tool_name == "gcc":
                            triplet = file.split('-')
                            self.triplet["arch"] = triplet[0]
                            self.triplet["vendor"] = triplet[1]
                            self.triplet["os"] = triplet[2]
                        self.tool[tool_name] = self.toolchain_path + file
        except:
            print(f"E: {toolchain_path} invalid")

        if not all(tool in self.tool for tool in self.tool_names):
            print(f"E: toolchain incomplete")

        if self.debug:
            print(f"toolchain: {self.triplet} {self.tool}")

    def compile(self, source_file, output_file, compiler_options=None):
        if compiler_options is None:
            compiler_options = QmkFirmwareCompilerOptions()
        # compile command
        gcc = self.tool["gcc"]
        compiler_options = compiler_options.options() + compiler_options.includes() + "-o "

        compile_command = [ gcc ]
        compile_command.extend(compiler_options.split())
        compile_command.append(output_file)
        compile_command.append(source_file)
        if self.debug:
            print(f"{compile_command}")
        try:
            result = subprocess.run(compile_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if self.debug:
                print(f"compilation ok")
            return True
        except subprocess.CalledProcessError as e:
            print(f"E: compilation nok: {e.stderr.decode()}")
            return False

    def elf2bin(self, elf_file):
        objcopy = self.tool["objcopy"]
        objcopy_options = "-O binary"
        objcopy_command = [ objcopy ]
        objcopy_command.extend(objcopy_options.split())
        objcopy_command.append(elf_file)
        objcopy_command.append(f"{elf_file.split('.')[0]}.bin")
        try:
            result = subprocess.run(objcopy_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if self.debug:
                print(f"objcopy ok")
        except subprocess.CalledProcessError as e:
            print(f"E: objcopy nok: {e.stderr.decode()}")

    def load_elf(self, elf_file):
        return GccElfFile(elf_file)

    def disasm(self, elf_file):
        print("="*80)
        objdump = self.tool["objdump"]
        objdump_options = "-d"
        objdump_command = [ objdump ]
        objdump_command.extend(objdump_options.split())
        objdump_command.append(elf_file)
        try:
            result = subprocess.run(objdump_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(result.stdout.decode())
        except subprocess.CalledProcessError as e:
            print(f"E: objdump nok: {e.stderr.decode()}")

class QmkFirmwareCompilerOptions:
    def __init__(self, qmk_firmware_path="", options="", includes=""):
        if not qmk_firmware_path:
            qmk_firmware_path = 'V:\\qmk_firmware\\'
        self.qmk_firmware_path = qmk_firmware_path

        self.compiler_options = includes
        self.compiler_includes = options
        if not options:
            self.options("-c", "-mcpu=cortex-m4", "-mthumb", "-DTHUMB_PRESENT", "-mno-thumb-interwork", "-DTHUMB_NO_INTERWORKING", "-mno-unaligned-access", "-mfloat-abi=hard", "-mfpu=fpv4-sp-d16", "-fsingle-precision-constant", "-fomit-frame-pointer", "-ffunction-sections", "-fdata-sections", "-fno-common", "-fshort-wchar", "-fno-builtin-printf", "-ggdb", "-Os", "-Wall", "-Wstrict-prototypes", "-Werror", "-std=gnu11", "-fcommon", "-fPIC")
        if not includes:
            self.includes("quantum\\rgb_matrix\\animations", "quantum\\rgb_matrix\\", "quantum\\", "platforms\\", ".build\\obj_keychron_q3_max_ansi_encoder_via\\src\\")

    def includes(self, *args):
        for arg in args:
            self.compiler_includes += f"-I {self.qmk_firmware_path}{arg} "
        return self.compiler_includes

    def options(self, *args):
        for arg in args:
            self.compiler_options += f"{arg} "
        return self.compiler_options


class GccElfFile:
    def __init__(self, elf_file):
        self.elf_file = elf_file
        self.elf = ELFFile(open(elf_file, "rb"))
        print(f"elf:{self.elf}")

        self.data = {}
        self.data['text'] = self.load_text()
        self.data['rodata'] = self.load_rodata()

    def load_text(self):
        text = {}
        for section in self.elf.iter_sections():
            if section.name.startswith('.text'):
                text_symbol = section.name.split('.')
                try:
                    text[text_symbol[2]] = section.data()
                except:
                    pass
        return text

    def load_rodata(self):
        rodata = {}
        for section in self.elf.iter_sections():
            if section.name.startswith('.rodata'):
                rodata_symbol = section.name.split('.')
                try:
                    rodata[rodata_symbol[2]] = section.data()
                except:
                    pass
        return rodata

    def print_sections(self):
        for section in self.elf.iter_sections():
            if section.name.startswith('.debug'):
                continue
            print("="*80)
            print(f"section {section.name} {section.header}")
            print("-"*80)
            print(section.data().hex(' '))
            print(section.data().decode('utf-8', errors='ignore'))

    def print_segments(self):
        for segment in self.elf.iter_segments():
            print(f"segment {segment}")

    def load_segments(self):
        for segment in self.elf.iter_segments():
            print(f"segment {segment}")
            if segment['p_type'] == 'PT_LOAD':
                mem_size = segment['p_memsz']
                mem = segment.data()
                print(f"segment {segment}, mem_size:{mem_size} mem:{mem}")


    def find_symbol(self, symbol_name):
        for section in self.elf.iter_sections():
            if section.name == '.symtab':
                symbol_table = section
                for symbol in symbol_table.iter_symbols():
                    if symbol.name == symbol_name:
                        return symbol['st_value']
        return None

    def resolve_symbols(self, memory_map):
        print(f"resolve_symbols:{memory_map}")
        symtab = self.elf.get_section_by_name('.symtab')
        for section in self.elf.iter_sections():
            if section['sh_type'] == 'SHT_REL':
                rel_section = section
                for rel in rel_section.iter_relocations():
                    symbol = symtab.get_symbol(rel['r_info_sym'])
                    symbol_name = symbol.name
                    symbol_addr = memory_map[symbol['st_value']]
                    rel_offset = rel['r_offset']
                    rel_type = rel['r_info_type']

                    print(f"symbol_name:{symbol_name} symbol_addr:{symbol_addr} rel_offset:{rel_offset} rel_type:{rel_type}")



if __name__ == "__main__":
    toolchain = GccToolchain()
    toolchain.compile("exec.c", "exec.elf")
    toolchain.elf2bin("exec.elf")

    elf = toolchain.load_elf("exec.elf")
    elf.load_segments()

    data = None
    with open("exec.bin", "rb") as f:
        data = f.read()
        print(data.hex(' '))

    elf = toolchain.load_elf("exec.elf")
    elf.print_segments()
    elf.print_sections()

    print("="*80)
    print("text data:")
    for sym in elf.data['text']:
        print(f"{sym}: {elf.data['text'][sym].hex(' ')}")

    print("rodata data:")
    for sym in elf.data['rodata']:
        print(f"{sym}: {elf.data['rodata'][sym].hex(' ')}")

    toolchain.disasm("exec.elf")
