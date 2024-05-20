import re, io

class GccMapfile:
    def __init__(self, map_file_path = ""):
        if not map_file_path:
            map_file_path = 'V:\shared\keychron\keychron_q3_max_ansi_encoder_via.map'
        self.functions, self.variables = self.parse_file(map_file_path)

    def fun_addr(self, name):
        return int(self.functions[name]['address'])

    def parse_file(self, file_path):
        def symbol_entry_pattern(section):
            return re.compile(r'''
                \s*\.%s\.(\w+)\s*       # symbol name
                \s*(0x[\da-fA-F]+)\s*   # address
                \s*(0x[\da-fA-F]+)\s*   # size
                \s*(\S+)\s*             # object file path
            ''' % section, re.VERBOSE)

        def symbol_entry_match(section, symbol_entry):
            if not symbol_entry:
                return

            # bss COMMON section
            if symbol_entry.strip().startswith('COMMON'):
                if section == 'bss':
                    #print(f"{symbol_entry}")
                    buf = io.StringIO(symbol_entry)
                    common = {}
                    for line in buf:
                        if line.strip().startswith('COMMON'):
                            _addr_size_obj = line.split()
                            common['addr'] = int(_addr_size_obj[1], 16)
                            common['size'] = int(_addr_size_obj[2], 16)
                            common['obj'] = _addr_size_obj[3]
                            common['symbols'] = []
                            #print(f"common: {common}")
                            try:
                                if "~last_common~" in variables:
                                    prev_sym_size = common['addr'] - variables["~last_common~"]['address']
                                    variables["~last_common~"]['size'] = prev_sym_size
                            except:
                                pass
                        else:
                            _addr_symbol = line.split()
                            try:
                                sym_addr = int(_addr_symbol[0], 16)
                            except:
                                pass
                            sym_name = _addr_symbol[1]
                            if len(common['symbols']) > 0:
                                prev_sym = common['symbols'][-1]
                                prev_sym_size = sym_addr - prev_sym[0]
                                common['symbols'][-1] = (prev_sym[0], prev_sym_size, prev_sym[2])
                            common['symbols'].append((sym_addr, 0, sym_name))
                    #print(f"common: {common}")
                    for sym in common['symbols']:
                        entry = {
                            "section": section,
                            "address": sym[0],
                            "size": sym[1],
                            "object_file": common['obj'],
                            "symbol_address": sym[0],
                            "symbol_name": sym[2],
                        }
                        variables[entry["symbol_name"]] = entry
                        variables["~last_common~"] = entry
                    return

            # regex pattern to match symbol entry
            symbol_pattern = symbol_entry_pattern(section)
            matches = symbol_pattern.findall(symbol_entry)
            for match in matches:
                entry = {
                    "section": section,
                    "address": int(match[1], 16),
                    "size": int(match[2], 16),
                    "object_file": match[3],
                    #"symbol_address": int(match[4], 16),
                    "symbol_name": match[0],
                }
                if section == 'text':
                    functions[entry["symbol_name"]] = entry
                    #print(f"function: {entry['symbol_name']} {entry['address']} {entry['size']} {entry['object_file']}")
                else:
                    variables[entry["symbol_name"]] = entry
                    #print(f"variable: {entry['symbol_name']} {entry['address']} {entry['size']} {entry['object_file']}")

        functions = {}
        variables = {}
        with open(file_path, 'r') as file:
            section = None
            symbol_entry = None
            for line in file:
                sections = ['text', 'data', 'bss', 'rodata']
                section_start = False
                section_end = False
                for _section in sections:
                    if line.strip().startswith(f'*(.{_section}.*'):
                        section = _section
                        section_start = True
                        #print(f"section: {section}")
                        break
                    if f"__{_section}_end__" in line:
                        section_end = True
                        break
                if section_start:
                    continue
                if section_end:
                    symbol_entry_match(section, symbol_entry)
                    section = None
                    continue
                if section is None:
                    continue

                if line.strip().startswith(f'.{section}.'):
                    if symbol_entry:
                        symbol_entry_match(section, symbol_entry)
                    symbol_entry = line
                else:
                    if section == 'bss' and line.strip().startswith('COMMON'):
                        if symbol_entry:
                            symbol_entry_match(section, symbol_entry)
                        symbol_entry = line
                    else:
                        symbol_entry += line

        return functions, variables

if __name__ == '__main__':
    map_file_path = 'V:\shared\keychron\keychron_q3_max_ansi_encoder_via.map'
    mapfile = GccMapfile(map_file_path)
    print("================================== functions ==================================")
    #print(mapfile.functions)
    print("================================== variables ==================================")
    #print(mapfile.variables)
    print("===============================================================================")
    funs = [ "matrix_init", "debug_led_on", "printf" ]
    for fun in funs:
        print(f"{fun}: {mapfile.functions[fun]['section']} {hex(mapfile.functions[fun]['address'])},{mapfile.functions[fun]['size']} {mapfile.functions[fun]['object_file']}")

    vars = [ "keymaps", "g_rgb_matrix_host_buf", "dynld_func_buf" ]
    for var in vars:
        print(f"{var}: {mapfile.variables[var]['section']} {hex(mapfile.variables[var]['address'])},{mapfile.variables[var]['size']} {mapfile.variables[var]['object_file']}")
