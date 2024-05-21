tracer = DebugTracer.registry()["KeybScriptEnv"]
tracer.zones["D"] = 0

elo = kb.e['l']
print(f"eeprom layout: {elo.hex(' ')}")

kb_mem_eeprom = [ ("memory", kb.m), ("eeprom", kb.e) ]
word_sizes = [1, 2, 4]
read_len = 64

for me in kb_mem_eeprom:
    mem_eeprom = me[0]
    me = me[1]
    print("="*40)
    print(mem_eeprom)
    print("="*40)
    for size in word_sizes:
        i = 0
        while i < read_len:
            if size == 1:
                val = me[i]
            else:
                val = me[i,size]
            print(f"[{i},{size}] = {hex(val)}")
            i += size

# stm32f4xx 64k sram
test_mem_addr=0x2000f000
test_values = [ (test_mem_addr,4,0x1234abcd), (test_mem_addr+4,2,0x1234), (test_mem_addr+6,1,0xab) ]
for tv in test_values:
    addr = tv[0]
    size = tv[1]
    val = tv[2]
    print(f"write mem[{hex(addr)},{size}] = {hex(val)}")
    if size == 1:
        kb.m[addr] = val
        val_read = kb.m[addr]
    else:
        kb.m[addr,size] = val
        val_read = kb.m[addr,size]

    if val != val_read:
        print(f"error: {hex(val)} != {hex(val_read)}")
