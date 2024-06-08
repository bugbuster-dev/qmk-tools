
flash_dump_size = 0x1bd80
flash_data = bytearray()

i = 0
while i < flash_dump_size:
    val = kb.m[0x08000000 + i, 32]
    flash_data.extend(val)
    i += 32

with open("flash_dump.bin", "wb") as f:
    f.write(flash_data)

print("flash dumped")

