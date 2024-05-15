
max_led_index = 87
delay = 0.1
i = 0
while not stopped():
    if i >= max_led_index:
        i = 0

    if i % 3 == 0:
        r,g,b = 0xff, 0x0, 0x0
    if i % 3 == 1:
        r,g,b = 0x0, 0xff, 0x0
    if i % 3 == 2:
        r,g,b = 0x0, 0x0, 0xff
    kb.rgb[0] = [r,g,b]        
    time.sleep(delay)
    
    kb.rgb[(i+1,i+2,i+3)] = [[r,g,b],[g,b,r],[b,r,g]]
    i = i + 1        
    time.sleep(delay)

print("stopped")

#todo: set pixel duration, rgb image
#kb.rgb.duration = 100
#kb.rgb['img'] = [ pixel*W*H ]
