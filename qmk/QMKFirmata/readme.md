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

* keychron q3 max (https://github.com/bugbuster-dev/keychron_qmk_firmware)
* nuphy air96 v2 (https://github.com/bugbuster-dev/qmk_firmware/tree/air96v2_virtser)

install
-------

python 3.8 + packages in requirements.txt

run
---

~~~
python QMK_firmata_demo.py
~~~

websocket client examples
-------------------------

in ws_client/

set default layer:
~~~
layer_switch.py
~~~

screen capture and send rgb image:
~~~
screen_capture_rgb_stream.py
~~~

demo videos
-----------

* https://drive.google.com/file/d/12ySYJkP7ocTn34E90FT40A-Zuc35bw2c/view?usp=drive_link
* https://drive.google.com/file/d/1v-YTx9ZsSe5XqfsBNemll0-R-acI87sh/view?usp=sharing
* https://drive.google.com/file/d/1F28Q8gsV9EzsmYWpxNxw247_gnC2F9l2/view?usp=drive_link
  
