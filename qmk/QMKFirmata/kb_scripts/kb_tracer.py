tracers = DebugTracer.registry()

tracer = tracers['QMKataKeyboard']
tracer.enable('SYSEX_RESPONSE', 0)
print(tracer.zones)
