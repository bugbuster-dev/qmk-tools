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
        attributes = ["zones", "obj"]
        for attr in attributes:
            setattr(self, attr, None)
            if attr == "zones":
                setattr(self, attr, {"E":1,"W":1,"I":0,"D":0}) # error, warning, info, debug
        for attr, value in kwargs.items():
            if attr in attributes:
                setattr(self, attr, value)
                if attr == "obj":
                    if value:
                        try:
                            DebugTracerRegistry.register_tracer(value.__class__.__name__, self)
                        except:
                            try:
                                DebugTracerRegistry.register_tracer(value, self)
                            except:
                                pass

    def tr(self, zone, string):
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
        try:
            self.zones[attr] = flag
        except:
            pass

    def enabled(self, attr):
        try:
            return self.zones[attr]
        except:
            return False
