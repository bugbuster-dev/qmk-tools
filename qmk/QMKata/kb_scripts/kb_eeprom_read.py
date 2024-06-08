
el = kb.e['l']
print(el.hex(' '))
keymap_addr = struct.unpack_from('<H', el, 1)[0]
keymap_size = struct.unpack_from('<H', el, 5)[0]
print(f"keymap_addr={hex(keymap_addr)},{hex(keymap_size)}")
num_layers = 8

data = bytearray()
for i in range(int(keymap_size/num_layers)):
    data.append(kb.e[(keymap_addr+i, 1)]%256)
print(data.hex(' '))
