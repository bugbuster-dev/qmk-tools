import sys, time
import d3dshot
import cv2
import asyncio
import websockets

# todo: parse args
# --display
# --width
# --height
# --fps
rgb_w = 17
rgb_h = 6
fps = 25

d = d3dshot.create(capture_output="numpy")
d.display = d.displays[0]
# start capture
d.capture()
print("capture is running...")

async def capture_ws_send():
    uri = "ws://localhost:8787"
    async with websockets.connect(uri) as websocket:
        while True:
            try:
                frame = d.get_latest_frame()
                #print(frame.shape)
                frame = cv2.resize(frame, (rgb_w, rgb_h))
                #frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frame_bytes = bytearray()
                for y in range(0, rgb_h):
                    for x in range(0, rgb_w):
                        r,g,b = frame[y, x]
                        frame_bytes.append(r)
                        frame_bytes.append(g)
                        frame_bytes.append(b)
                #print(frame_bytes)
                data = "rgb.img:".encode('utf-8')
                data = data + frame_bytes
                await websocket.send(data)
                await asyncio.sleep(0)
            except Exception as e:
                print(e)
            time.sleep(1/fps)


try:
    asyncio.get_event_loop().run_until_complete(capture_ws_send())
except KeyboardInterrupt:
    print("exit run")

d.stop()
exit()
