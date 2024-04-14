QMK Firmata demo
================

proof of concept demo of arduino firmata support in qmk firmware

- show console output
- set debug mask (enable/matrix/keyboard/...)
- set mac/win mode
- set rgb matrix from video/gif playback, matplotlib animation, audio peak level
- set dynamically loaded user animation binary
- set default layer depending on application in focus
- websocket server to set default layer from other apps
- websocket server to set rgb matrix from other apps

supported keyboards
-------------------

* keychron q3 max
* nuphy air96 v2

install
-------

python 3.8 + packages in requirements.txt

run
---

python QMK_firmata_demo.py

websocket client examples
-------------------------

set default layer:
~~~
ws_client/layer_switch.py
~~~

screen capture and send rgb image:
~~~
screen_capture_rgb_stream.py
~~~
