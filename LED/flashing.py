#!/usr/bin/env python2
"""
For this particular script, I had one ground wire going to the Pi's Ground pin
(6). There were 5 lights hooked up, each one was next to the other.

They were in the breadboard in the order specified below with each of those
pins hooked up to the same row as the lights displayed below. and there was a
1k ohm resistor coming out of the cathode end to the ground rail.

It looked kinda like this on the breadboard:
.__________________________
|\ main board       \ rail \.
| +-----------------+-------+
| | (blu)----.    .^v^.     |
| |     `----.    + |       |
| | (red)----.    .^v^.     |
| |     `----.    + |       |
| | (grn)----.    .^v^.     |
| |     `----.    + |       |
| | (ylw)----.    .^v^.     |
| |     `----.    + |       |
| | (wht)----.    .^v^.     |
| |     `----.    + | -     |
 \+-----------------+-------+

Legend
------
+            = GPIO Pin Connection
-            = Ground Pin Connection
.^v^.        = 1k ohm Resistor
(LED )-----. = cathode
     `-----. = anode
"""
from time import sleep

from gpiozero import LED

blue = LED(14)
red = LED(15)
green = LED(18)
yellow = LED(2)
white = LED(3)

all_lights = [
    blue,
    red,
    green,
    yellow,
    white
]

while True:
    for light in all_lights:
        light.toggle()
        sleep(0.1)
