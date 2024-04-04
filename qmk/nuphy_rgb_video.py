import argparse
import serial
import time
import cv2
from PIL import Image
import numpy as np

port = 'COM9'
baudrate = 115200 

print_maxtrix_frame = False

#--------------------------------

def print_buffer(data):
    # Print 16 byte values per line
    for i, byte in enumerate(data):
        # Print byte value with a space, end parameter prevents new line
        print(f'{byte:02x}', end=' ')
        # After every 16th byte, print a new line
        if (i + 1) % 16 == 0:
            print()  # This causes the line break

    # Handle the case where the data length is not a multiple of 16
    # This ensures we move to a new line after printing the last line, if necessary
    if len(data) % 16 != 0:
        print()  # Ensure there's a newline at the end if the data didn't end on a 16th byte


def grow_bytearray(ba, target_size, padding_byte=b'\x00'):
    """
    Grow a bytearray to a target size.

    Parameters:
    - ba: The bytearray to grow.
    - target_size: The desired size of the bytearray.
    - padding_byte: The byte value to use for padding. Default is null byte.

    Returns:
    The bytearray grown to the target size, if needed. If the bytearray is
    already larger than the target size, it is returned unchanged.
    """
    current_size = len(ba)
    if current_size < target_size:
        # Calculate how many bytes to add
        padding_size = target_size - current_size
        # Grow the bytearray
        ba += padding_byte * padding_size
    return ba

# ASCII characters used to build the output
ASCII_CHARS = "@%#*+=-:. "

# Convert a pixel value to an ASCII character
def pixel_to_ascii(pixel):
    return ASCII_CHARS[pixel * len(ASCII_CHARS) // 256]

# Convert an image to ASCII
def image_to_ascii(image, width=80):
    image = image.resize((width, int(width * image.height / image.width / 2)))
    image = image.convert("L")  # convert to grayscale
    pixels = np.array(image)
    ascii_image = "\n".join("".join(pixel_to_ascii(pixel) for pixel in row) for row in pixels)
    return ascii_image

def pixel_to_rgb_duration_index(pixel, index, duration, brightness):
    data = bytearray()
    #print(brightness)
    data.append(index)
    data.append(duration)
    data.append(min(int(pixel[0]*brightness[0]), 255))
    data.append(min(int(pixel[1]*brightness[1]), 255))
    data.append(min(int(pixel[2]*brightness[2]), 255))
    return data

#(0,0)..(18,0)   ->      0..18
#(0,1)..(18,1)   ->      19..36
#(0,2)..(18,2)   ->      37..54
#(0,3)..(18,3)   ->      55..70
#(0,4)..(18,4)   ->      71..87
#(0,5)..(18,5)   ->      88..99
def xy_to_rgb_index(x, y):
    if y == 0:
        return min(x,18)
    if y == 1:
        if x >= 14:
            x = x - 1
        return min(x+19,36)
    if y == 2:
        if x < 2:
            x = 0
        return min(x+37,54)
    if y == 3:
        if x < 2:
            x = 0
        elif x == 18:
            return 54
        elif x <= 13:
            x = x - 1
        else:
            x = x - 2
        return min(x+55,70)
    if y == 4:
        if x < 2:
            x = 0
        elif x <= 12:
            x = x - 1
        else:
            x = x - 2
        return min(x+71,87)
    if y == 5:
        if x >= 4 and x <= 9:
            x = 4
        elif x == 18:
            return 87
        else:
            x = x - 5
        return min(x+88,99)

    return 0

def image_to_rgb_index_duration(image, duration=100, width=80, offset=(0,0), brightness=(1.0,1.0,1.0)):
    image = image.resize((width, int(width * image.height / image.width / 2)))
    if offset != None:
        w, h = image.size
        crop_box = (offset[0], offset[1], w, h)
        image = image.crop(crop_box)
    pixels = np.array(image)
    #print(pixels)
    
    data = bytearray()
    data.extend([0xef, 0xfe])
    for y, row in enumerate(pixels):
        if y > 5:
            break
        for x, pixel in enumerate(row):
            data.extend(pixel_to_rgb_duration_index(pixel, xy_to_rgb_index(x, y), duration, brightness))

    return data

fps = 25
frame_delay = 1000/fps

# Play video and output as ASCII art or to com port
def play_video(path, width, offset, brightness=(1.0,1.0,1.0)):
    # open serial port
    ser = serial.Serial(port, baudrate, timeout=1)
    print(f"{port} opened successfully.")
    
    last_tick = 0
    if width == None:
        width = 80
    cap = cv2.VideoCapture(path)
    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            # Convert the frame to PIL Image to use the above function
            frame = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            frame = image_to_rgb_index_duration(frame, 100, width, offset, brightness)
            
            if print_maxtrix_frame:
                print("-----------------------------------------------")
                print_buffer(frame)
            
            send_buf_size = 768 + 2
            assert(len(frame) <= send_buf_size)            
            frame = grow_bytearray(frame, send_buf_size, b'\xff')
            # send data to the COM port
            ser.write(frame)
            #break

            tick = time.monotonic() * 1000
            wait_delay = frame_delay - 5
            if tick - last_tick < wait_delay:
                cv2.waitKey(wait_delay - 5 - (tick - last_tick))  # Adjust this to change the playback speed
    finally:
        cap.release()

#----------------------------------------------------------------

def parse_brightness(floats_str):
    # Convert the comma-separated string to a tuple of floats
    br = tuple(map(float, floats_str.split(',')))
    if len(br) == 1:
        return (br[0],br[0],br[0])
    if len(br) != 3:
        raise ValueError("brightness correction values needed for r,g,b")
    return br 

parser = argparse.ArgumentParser(description='')
parser.add_argument('file', type=str,
                    help='video file')

parser.add_argument('-w', '--width', type=int,
                    help='width')

parser.add_argument('-xo', '--x_offset', type=int,
                    help='x offset', default=0)

parser.add_argument('-yo', '--y_offset', type=int,
                    help='y offset', default=0)

parser.add_argument('-br', '--brightness', type=parse_brightness,
                    help='brightness correction for r,g,b', default=(1.0,1.0,1.0))

args = parser.parse_args()

# play video on keyboard matrix...
play_video(args.file, args.width, (args.x_offset, args.y_offset), args.brightness)
