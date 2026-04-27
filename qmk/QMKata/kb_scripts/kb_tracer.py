tracers = DebugTracer.registry()
#print(tracers)

tracer = tracers['QMKataKeyboard']
tracer.enable('SYSEX_RESPONSE', 0)

tracer = tracers['QMKataKeyboard']
tracer.enable('SYSEX_PUB', 1)
print(tracer.zones)

tracer = tracers['KeyMachine']
tracer.enable('D', 1)
print(tracer.zones)
