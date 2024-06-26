# todo: load all relevant elf sections into keyboard memory
# for now only text is loaded and no relocation support.
# below example of compiling a c function and loading its code (elf text section)
# into keyboard memory and executing it.
# function and variable symbol addresses of running firmware can be loaded from
# the map file and used in the c code as constants so it is included in the text section.
# printf function and __QMK_BUILDDATE__ variable are used in the example.

def compile_and_exec(c_file):
    code = kb.compile(c_file)
    if not code:
        print("compile nok")
        exit()
    #rc = kb.exec(code['elf']) # todo: load relevant elf sections into kb memory
    rc = kb.exec(code['bin'])
    print(f"rc: {hex(rc)}")

#----------------------------------------------
printf_func = kb.fun["printf"]
printf_addr = printf_func["address"]
print(f"printf: {hex(printf_addr)}")

builddate = kb.var["__QMK_BUILDDATE__"]
builddate_addr = builddate["address"]
print(f"builddate: {hex(builddate_addr)}")

hello_world_c = '''
#include <stdint.h>
typedef int (*funptr_printf)(const char* fmt, ...);

int hello_world(int a) {{
    uint32_t printf_addr = {printf_addr};
    uint32_t qmk_builddate_addr = {builddate_addr};
    funptr_printf printf = (funptr_printf) (printf_addr | 1);
    printf((const char*) qmk_builddate_addr);
    return 0x5adcbaa5;
}}
'''
hello_world_c_file = hello_world_c.format(printf_addr=hex(printf_addr), builddate_addr=hex(builddate_addr))
print("-"*40)
print(hello_world_c_file)
print("-"*40)
with open("exec.c", "w") as f:
    f.write(hello_world_c_file)

compile_and_exec("exec.c")

#----------------------------------------------
putchar_fun = kb.fun["putchar_"]
putchar_addr = putchar_fun["address"]
print(f"putchar: {hex(putchar_addr)}")

putchar_c = '''
#include <stdint.h>
typedef void (*funptr_putchar)(char ch);
int putchar_test(int a) {{
    uint32_t putchar_addr = {putchar_addr};
    funptr_putchar putchar = (funptr_putchar)( putchar_addr | 1);
    putchar('\\n');
    for (int i = 0; i < 26; i++) {{
        putchar('A' + i);
    }}
    putchar('\\n');
    return 0xa5abcd5a;
}}
'''
putchar_c_file = putchar_c.format(putchar_addr=hex(putchar_addr))
print("-"*40)
print(putchar_c_file)
print("-"*40)
with open("exec.c", "w") as f:
    f.write(putchar_c_file)

compile_and_exec("exec.c")
