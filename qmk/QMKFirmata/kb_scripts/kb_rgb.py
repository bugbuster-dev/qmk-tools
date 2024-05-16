
max_led_index = 87
delay = 0.1
i = 0
while not stopped():
    if i >= max_led_index:
        i = 0

    if i % 3 == 0:
        rgb = [0xff, 0x0, 0x0]
    if i % 3 == 1:
        rgb = [0x0, 0xff, 0x0]
    if i % 3 == 2:
        rgb = [0x0, 0x0, 0xff]
    kb.rgb[0] = rgb
    time.sleep(delay)
    
    brg = [rgb[-1]] + rgb[:-1]
    gbr = [brg[-1]] + brg[:-1]
    kb.rgb[(i+1,i+2,i+3)] = [rgb,gbr,brg]
    i = i + 1        
    time.sleep(delay)

print("stopped")

#todo: set pixel duration, rgb image
#kb.rgb.duration = 100
#kb.rgb['img'] = [ pixel*W*H ]
