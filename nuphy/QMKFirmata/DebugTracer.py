

class DebugTracer:
    def __init__(self, *args, **kwargs):
        self.print = None
        for arg in kwargs:
            if arg == "print":
                self.print = kwargs[arg]
            if arg == "trace":
                self.trace = kwargs[arg]

    def pr(self, *args, **kwargs):
        if self.print:
            msg = " ".join(str(arg) for arg in args)
            print(msg)
        if self.trace:
            # todo: put in trace buffer
            pass


