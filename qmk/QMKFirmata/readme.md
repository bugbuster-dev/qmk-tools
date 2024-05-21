QMK Firmata demo
================

proof of concept demo (windows) of arduino firmata support in qmk firmware

- set rgb matrix from video/gif playback, matplotlib animation, audio peak level
- set default layer depending on application in focus
- set mac/win mode
- set debug config, rgb mode/hsv/speed, keymap flags, debounce, ...
- set dynamically loaded user animation binary
- "keyboard scripting" ("development build" only), access keyboard mcu memory/eeprom and compile/execute c function from host python.
- show console output
- websocket server to set default layer from other apps
- websocket server to set rgb matrix from other apps

**WARNING: depending on audio/video content the lights may flash frequently, which can trigger a seizure!**
**do not use it when you are photosensitive!**

supported keyboards
-------------------

* keychron q3 max (https://github.com/bugbuster-dev/keychron_qmk_firmware)
* todo: nuphy air96 v2 (https://github.com/bugbuster-dev/qmk_firmware/tree/air96v2_virtser)

install
-------

* python 3.11
* install packages in requirements.txt:
~~~
pip install -r requirements.txt
~~~

run
---

~~~
python QMK_firmata.py
~~~

websocket client examples
-------------------------

in ws_client/

set default layer:
~~~
python layer_switch.py <layer>
~~~

screen capture and send rgb image:
~~~
python screen_capture_rgb_stream.py --display 0 --fps 25 --width 17 --height 6 --port 8787
~~~

demo videos
-----------

rgb from video/gif playback, screen capture:
* https://www.dropbox.com/scl/fi/o1hf8g2pgcmz6pnmi4lf0/qmk_firmata_demo_video_playback.mp4?rlkey=109kbajetq0ow28s3isaid5ih&st=hl9uuwiq&dl=0
* https://www.dropbox.com/scl/fi/7iep6tmbkys5mlwfh9xo6/keychron-q3-max-cat-gif.mp4?rlkey=koq4ncl3ntxfqfz0uvkm0rvap&dl=0
* https://www.dropbox.com/scl/fi/lmipvwwoth5pdwywp1cyd/qmk_firmata_demo_disco.mp4?rlkey=ogiihll52lg1xm7t6kvqmmls8&st=z7cbqsnn&dl=0
* https://www.dropbox.com/scl/fi/vo263yf3ihkgcrgsrq34t/qmk_firmata_demo_screen_capture.mp4?rlkey=0i9iiv63berpbxkypu1eti3xd&st=zovba14p&dl=0

rgb light speaker:
* https://www.dropbox.com/scl/fi/ql8ucdq006b8wl9upkfih/keychron-q3-max-audio-rgb-kraftwerk.mp4?rlkey=60k17649zv307izt2ocnprojd&st=tin9p5z0&dl=0
* https://www.dropbox.com/scl/fi/zkvbqu0e8nxutxmxazdgd/keychron-q3-max-audio-rgb-sail.mp4?rlkey=6rnj8elf144y1s5nu6q5nomfm&st=zbconab1&dl=0
* https://www.dropbox.com/scl/fi/7liw11vouhzc31s6g354j/keychron-q3-max-audio-rgb-justin-johson-slide-guitar.mp4?rlkey=hsv2zx0cv9hj6p5ekw7cpajg5&st=az04r0my&dl=0
* https://www.dropbox.com/scl/fi/45fuu7pm1zjgli6ow79qy/keychron-q3-max-audio-rgb-fear-factory.mp4?rlkey=tq9qeqh7kq9yh9khkbqmx22yk&st=dieme07j&dl=0
* https://www.dropbox.com/scl/fi/pba2bdu83l31b361na0i0/keychron-q3-max-audio-rgb-der-holle-rache.mp4?rlkey=moxiyt05vv2za2sjsvqorgr0m&st=1k6i3aeg&dl=0
