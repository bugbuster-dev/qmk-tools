

class DebugTracer:
    def __init__(self, *args, **kwargs):
        # set flags to print, trace, ...
        attributes = ["print", "trace", "obj"]
        for attr in attributes:
            setattr(self, attr, None)
        for attr, value in kwargs.items():
            if attr in attributes:
                setattr(self, attr, value)

    def tr(self, *args, **kwargs):
        if self.print:
            objstr = ""
            if hasattr(self, "obj") and self.obj:
                try:
                    objstr = f"[{self.obj.__class__.__name__}] "
                except Exception as e:
                    pass

            msg = objstr + " ".join(str(arg) for arg in args)
            print(msg)
        if self.trace:
            # todo: put in trace buffer to do post run diagnostics
            pass
