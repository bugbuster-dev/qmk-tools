print("keymap:")

keymap_start = 0x29
keymap_layer_size = 17 * 6 # row x col
kc_size = 2

for i in range(keymap_layer_size):
    off = i*kc_size
    kc = kb.e[(keymap_start+off, kc_size)]
    print(hex(kc))
