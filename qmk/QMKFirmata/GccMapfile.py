import re

class GccMapfile:
    def __init__(self, map_file_path):
        if map_file_path is None:
            map_file_path = 'V:\shared\keychron\keychron_q3_max_ansi_encoder_via.map'
        self.functions, self.variables = self.parse_file(map_file_path)

    def fun_addr(self, name):
        return int(self.functions[name]['address'])

    def parse_file(self, file_path):
        def symbol_entry_pattern(section):
            return re.compile(r'''
                \s*\.(%s)\.\w+\s*       # section name
                \s*(0x[\da-fA-F]+)\s*   # address
                \s*(0x[\da-fA-F]+)\s*   # size
                \s*(\S+)\s*             # object file path
                \s*(0x[\da-fA-F]+)\s*   # second address (same as the first address)
                \s*(.*)                 # symbol name
            ''' % section, re.VERBOSE)

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
                    section = None
                    continue
                if section is None:
                    continue

                if line.strip().startswith(f'.{section}.'):
                    if symbol_entry:
                        # regex pattern to match each variable symbol
                        symbol_pattern = symbol_entry_pattern(section)
                        matches = symbol_pattern.findall(symbol_entry)
                        for match in matches:
                            entry = {
                                "section": match[0],
                                "address": int(match[1], 16),
                                "size": int(match[2], 16),
                                "object_file": match[3],
                                "symbol_address": int(match[4], 16),
                                "symbol_name": match[5],
                            }
                            if section == 'text':
                                functions[entry["symbol_name"]] = entry
                                #print(f"function: {entry['symbol_name']} {entry['address']} {entry['size']} {entry['object_file']}")
                            else:
                                variables[entry["symbol_name"]] = entry
                                #print(f"variable: {entry['symbol_name']} {entry['address']} {entry['size']} {entry['object_file']}")
                    symbol_entry = line
                else:
                    symbol_entry += line

        return functions, variables

if __name__ == '__main__':
    map_file_path = 'V:\shared\keychron\keychron_q3_max_ansi_encoder_via.map'
    mapfile = GccMapfile(map_file_path)
    #print("functions:", mapfile.functions)
    #print("variables:", mapfile.variables)
