# todo: get debug_led_on address from map file

for i in range(200):
    kb.call(0x0800f564)
    time.sleep(0.1)

    if stopped():
        print("stop received!")
        break

print("stopped!")
