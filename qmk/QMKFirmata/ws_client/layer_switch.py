import sys
import asyncio
import websockets

try:
    layer = int(sys.argv[1])
except:
    layer = 2

async def layer_switch():
    uri = "ws://localhost:8765"
    async with websockets.connect(uri) as websocket:
        await websocket.send(f"layer:{layer}")

asyncio.get_event_loop().run_until_complete(layer_switch())