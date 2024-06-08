
rgb_matrix_host_buf_var = kb.var["g_rgb_matrix_host_buf"]
rgb_matrix_host_buf = rgb_matrix_host_buf_var['address']
print(hex(rgb_matrix_host_buf))

num_rgb_leds = 87
pixel_size = 4

kb.m[(rgb_matrix_host_buf, 1)] = 0xff
kb.m[(rgb_matrix_host_buf+1, 1)] = 0xff
kb.m[(rgb_matrix_host_buf+2, 1)] = 0
kb.m[(rgb_matrix_host_buf+3, 1)] = 0

kb.m[(rgb_matrix_host_buf+num_rgb_leds*pixel_size, 1)]= 0x1

