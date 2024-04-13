import sys, time, argparse
import d3dshot
import cv2
import asyncio
import websockets

def parse_args():
    parser = argparse.ArgumentParser(description="capture screen and stream as rgb image over websocket")
    parser.add_argument("--display", type=int, default=0, help="display index to capture")
    parser.add_argument("--width", type=int, default=17, help="rgb matrix width")
    parser.add_argument("--height", type=int, default=6, help="rgb matrix height")
    parser.add_argument("--fps", type=int, default=25, help="frame rate of the capture")
    parser.add_argument("--port", type=int, default=8787, help="websocket server port")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()

    display_index = args.display
    rgb_w = args.width
    rgb_h = args.height
    fps = args.fps
    port = args.port

    d = d3dshot.create(capture_output="numpy")
    d.display = d.displays[display_index]
    # start capture
    d.capture()
    print("capture is running...")

    async def capture_ws_send():
        uri = f"ws://localhost:{port}"
        try:
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
        except Exception as e:
            print("websocket error: ", e)

    try:
        asyncio.get_event_loop().run_until_complete(capture_ws_send())
    except KeyboardInterrupt:
        print("exit run")

    d.stop()
