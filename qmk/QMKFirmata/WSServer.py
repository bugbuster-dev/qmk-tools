from PySide6.QtCore import QThread
import asyncio, websockets

from DebugTracer import DebugTracer

class WSServer(QThread):

    def __init__(self, msg_handler, port = 8765):
        self.dbg = DebugTracer(zones={'D':1}, obj=self)

        self.port = port
        self.loop = None
        self.msg_handler = msg_handler
        super().__init__()

    def run(self):
        self.dbg.tr('D', f"ws server start on port: {self.port}")
        asyncio.run(self.ws_main())

    async def ws_main(self):
        self.loop = asyncio.get_running_loop()
        self.stop_ev = self.loop.create_future()
        async with websockets.serve(self.msg_handler, "localhost", self.port):
            await self.stop_ev
        self.dbg.tr('D', "ws server stopped")

    async def ws_close(self):
        # dummy connect to exit ws_main
        try:
            async with websockets.connect(f"ws://localhost:{self.port}") as websocket:
                await websocket.send("")
        except Exception as e:
            pass

    def stop(self):
        #self.dbg.tr('D', "ws server stop")
        if self.loop:
            self.stop_ev.set_result(None)
            asyncio.run(self.ws_close())

