

class DebugTracer:
    def __init__(self, *args, **kwargs):
        self.print = None
        attributes = ["print", "trace", "obj"]
        # Assigning keyword arguments directly
        for key, value in kwargs.items():
            if key in attributes:
                setattr(self, key, value)

    def tr(self, *args, **kwargs):
        if self.print:
            objstr = ""
            if hasattr(self, "obj") and self.obj:
                try:
                    objstr = f"[{self.obj.__class__.__name__}]:"
                except Exception as e:
                    pass

            msg = objstr + " ".join(str(arg) for arg in args)
            print(msg)
        if self.trace:
            # todo: put in trace buffer to do post run diagnostics
            pass
