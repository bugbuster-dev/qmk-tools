'''
tracers = DebugTracer.registry()
tracer = tracers["FirmataKeyboard"]
tracer.zones['SYSEX_COMMAND'] = 0
print(tracer.zones)
'''

import time, threading

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
        for attr, value in kwargs.items():
            if attr in attributes:
                setattr(self, attr, value)
                if attr == "zones":
                    self.zones.update({"E":1,"W":1})
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

                curr_time = f"{time.time():.3f}:"
                tid = threading.get_ident()
                msg = curr_time + objstr + f"[{zone}]" + f":{tid}:" + string
                print(msg)
        except:
            pass

    def enable(self, attr, flag=True):
        self.zones[attr] = flag

    def enabled(self, attr):
        try:
            return self.zones[attr]
        except:
            return False
