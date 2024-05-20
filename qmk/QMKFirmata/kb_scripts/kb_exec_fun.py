
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
    return 0x5a;
}}
'''
toolchain = kb.toolchain

hello_world_c_file = hello_world_c.format(printf_addr=hex(printf_addr), builddate_addr=hex(builddate_addr))
print("-"*40)
print(hello_world_c_file)
print("-"*40)
with open("exec.c", "w") as f:
    f.write(hello_world_c_file)

if not toolchain.compile("exec.c", "exec.elf"):
    print("compile failed")
    exit()

#exit()
toolchain.elf2bin("exec.elf")
code = None
with open("exec.bin", "rb") as f:
    code = f.read()
    print(code.hex(' '))
if code:
    rc = kb.exec(code)
    print(f"rc: {hex(rc)}")
#exit()
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
    return 0xa5;
}}
'''
putchar_c_file = putchar_c.format(putchar_addr=hex(putchar_addr))
print("-"*40)
print(putchar_c_file)
print("-"*40)
with open("exec.c", "w") as f:
    #c_file = c_function.format(printf_addr=hex(printf_addr))
    f.write(putchar_c_file)

toolchain = kb.toolchain
if not toolchain.compile("exec.c", "exec.elf"):
    print("compile failed")
    exit()

toolchain.elf2bin("exec.elf")
code = None
with open("exec.bin", "rb") as f:
    code = f.read()
    print(code.hex(' '))
if code:
    rc = kb.exec(code)
    print(f"rc: {hex(rc)}")
