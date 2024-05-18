'''
tracers = DebugTracer.registry()
tracer = tracers["FirmataKeyboard"]
tracer.zones['SYSEX_COMMAND'] = 0
print(tracer.zones)
'''

class DebugTracerRegistry:
    _registry = {}

    @classmethod
    def register_tracer(cls, name, tracer):
        cls._registry[name] = tracer

    @classmethod
    def registry(cls):
        return cls._registry

class DebugTracer:

    @staticmethod
    def registry():
        return DebugTracerRegistry.registry()

    def __init__(self, *args, **kwargs):
        # set flags to print, trace, ...
        attributes = ["zones", "print", "trace", "obj"]
        for attr in attributes:
            setattr(self, attr, None)
        for attr, value in kwargs.items():
            if attr in attributes:
                setattr(self, attr, value)
                if attr == "obj":
                    if value:
                        DebugTracerRegistry.register_tracer(value.__class__.__name__, self)

    #def tr(self, *args, **kwargs):
    def tr(self, zone, string):
        if self.print:
            print("DebugTracer: remove")

        try:
            if self.zones[zone]:
                objstr = ""
                if hasattr(self, "obj") and self.obj:
                    try:
                        objstr = f"[{self.obj.__class__.__name__}]"
                    except Exception as e:
                        pass

                msg = objstr + f"[{zone}]" + string
                print(msg)
        except:
            pass

    def enable(self, attr, flag=True):
        setattr(self, attr, flag)

    def enabled(self, attr):
        try:
            return getattr(self, attr)
        except:
            return False
