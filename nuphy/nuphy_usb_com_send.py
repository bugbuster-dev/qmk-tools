import serial
import time
import sys, traceback

import pyaudio
import numpy as np
import threading
import queue

from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume, IAudioMeterInformation
from time import sleep


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




def audio_capture_thread(peak_levels_queue, stop_event):
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 44100
    CHUNK = 1024

    audio = pyaudio.PyAudio()

    def callback(in_data, frame_count, time_info, status):
        audio_data = np.frombuffer(in_data, dtype=np.int16)
        peak_level = np.max(np.abs(audio_data))
        peak_levels_queue.put(peak_level)
        return (in_data, pyaudio.paContinue)

    stream = audio.open(format=FORMAT, channels=CHANNELS,
                        rate=RATE, input=True,
                        frames_per_buffer=CHUNK,
                        stream_callback=callback)

    stream.start_stream()

    try:
        while not stop_event.is_set() and stream.is_active():
            threading.Event().wait(0.1) 
    finally:
        stream.stop_stream()
        stream.close()
        audio.terminate()



def main_thread(peak_levels_queue, stop_event):
    while not stop_event.is_set():
        peak_level = peak_levels_queue.get()
        # Process the peak level here
        print("Peak Level:", peak_level)


if __name__ == "__main__":
    peak_levels_queue = queue.Queue()
    stop_event = threading.Event()

    audio_thread = threading.Thread(target=audio_capture_thread, args=(peak_levels_queue, stop_event))
    main_thread = threading.Thread(target=main_thread, args=(peak_levels_queue, stop_event))

    audio_thread.start()
    main_thread.start()

    try:
        while True:
            # For example, stop on a keyboard interrupt (Ctrl+C)
            pass
    except KeyboardInterrupt:
        print("Stopping...")
        stop_event.set()
        
    audio_thread.join()
    main_thread.join()



port = 'COM9'
baudrate = 115200 


def monitor_audio_output_level():
    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(
        IAudioMeterInformation._iid_, CLSCTX_ALL, None)
    if interface:
        audio_meter = cast(interface, POINTER(IAudioMeterInformation))
        if audio_meter:
            peak_value = audio_meter.GetPeakValue()
            print(f"Current audio output level: {peak_value:.2f}")
            return peak_value
    

try:
    # Open the serial port
    ser = serial.Serial(port, baudrate, timeout=1)
    print(f"{port} opened successfully.")

#------------
# 0..18
# 19..36
# 37..54
# 55..70
# 71..87
# 88..99
#------------
     
    num_level_leds = 15
    led_index = [[ 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14 ],
                 [ 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33 ],
                 [ 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51 ],
                 [ 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69 ],
                 [ 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85 ], 
                 [ 88, 89, 90, 91, 92, 93, 94, 95, 96, 255, 255, 255, 255, 255, 255, 255 ] 
                 ]
    
    led_color = [ [0,30,70],[0,60,90],[0,70,100],[30,70,100],[50,80,120],
                  [80,30,50],[100,30,50],[150,50,50],[200,10,10],[220,5,5],
                  [225,5,5], [245,0,0], [250,0,0], [255,0,0], [255,0,0]
                  ]


    #for i in range(2000):
    while True:
        #vol_lvl = get_current_volume()
        out_lvl = monitor_audio_output_level()
        out_levels = []
        out_levels.append(out_lvl*2.5)
        out_levels.append(out_lvl*2.2)
        out_levels.append(out_lvl*2.2)
        out_levels.append(out_lvl*2.2)
        out_levels.append(out_lvl*2.0)
        out_levels.append(out_lvl*2.0)
        
        data = bytearray()
        data.extend([0xef, 0xfe])
        
        for row in range(0, 5):
            for i in range(0,num_level_leds):
                if out_levels[row] > (i*1.0)/num_level_leds:
                    data.extend([led_index[row][i], 100, led_color[i][0], led_color[i][1], led_color[i][2]])
            
        send_buf_size = 512 + 2
        assert(len(data) <= send_buf_size)            
        data = grow_bytearray(data, send_buf_size, b'\xff')

        # Write data (send data to the COM port)
        ser.write(data)  # (b'H')  # Send the string "Hello" as bytes
        print_buffer(data)
        print("Data sent.")

        # Wait for a response
        time.sleep(0.1)  # Adjust the sleep time as needed

        # Read data (receive data from the COM port)
        incoming_data = ser.read(ser.in_waiting)  # Read all available data
        if incoming_data:
            print(f"Received data: {incoming_data.decode('utf-8')}")
        else:
            print("No data received.")

except serial.SerialException as e:
    print(f"Error opening serial port {port}: {e}")
except Exception as err:    
    try:
        exc_info = sys.exc_info()
    finally:
        # Display the *original* exception
        traceback.print_exception(*exc_info)
        del exc_info
finally:
    # Always close the serial port
    if 'ser' in locals() and ser.is_open:
        ser.close()
        print(f"{port} closed.")
