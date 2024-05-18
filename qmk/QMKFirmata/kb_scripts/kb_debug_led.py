
try:
    debug_led_on_fun = kb.fn["debug_led_on"]
    fun_addr = debug_led_on_fun["address"]
except:
    fun_addr = None

# print where the fun starts
print(hex(fun_addr))

if not fun_addr:
    exit()

for i in range(100):
    kb.call(fun_addr)
    time.sleep(0.1)

    if stopped():
        print("stop received!")
        break

print("stopped!")
