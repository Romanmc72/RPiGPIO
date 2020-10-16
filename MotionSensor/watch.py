#!/usr/bin/env python3
"""
Got a new toy!!! The PIR motion sensor senses motion with infrared technology.
Pretty cool.

Here is the hookup on the breadboard:

.__________________________
|\ main board       \ rail \.
| +-----------------+-------+
| | (led)----.    .^v^.     |
| |     `----.    X |       |
| |                 |       |
| |  o            O | N   P |
| |                 | -   + |
 \+-----------------+-------+

Legend
------
+            = 5V RPi pin
-            = Ground Pin Connection
o            = Output from PIR Sensor
O            = GPIO Pin 14
N            = Cathode Pin on PIR Sensor
P            = Anode Pin on PIR Sensor
.^v^.        = 1k ohm Resistor
(LED )-----. = LED Cathode
     `-----. = LED Anode
X            = GPIO Pin 15

The PIR Sensor is difficult to represent with terminal art so I will link it
here instead!
[http://www.diymalls.com/HC-SR501-PIR-Infared-Sensor?search=PIR%20Sens]
"""
from gpiozero import MotionSensor
from gpiozero import LED

sensor = MotionSensor(14)
light = LED(15)

# Set this and then just run in an infinite loop until keyboard interrupt. You
# will notice that the sensor gets a singal for activation, then regardless of
# whether or not activity is still happening it shuts off the signal then
# checks again. Mess with the sensitivity and output timing for the sensor to
# see what happens there, but generally speaking that is what happes.
sensor.when_activated =  light.on
sensor.when_deactivated = light.off

if __name__ == "__main__":
    while True:
        try:
            pass
        except KeyboardInterrupt:
            sensor.close()
            light.close()
