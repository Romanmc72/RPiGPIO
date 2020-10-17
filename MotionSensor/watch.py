#!/usr/bin/env python3
"""
Got a new toy!!! The PIR motion sensor senses motion with infrared technology.
Pretty cool.

Here is the hookup on the breadboard:

.__________________________
|\ main board       \ rail \.
| +-----------------+-------+
| | (LED)----.    .^v^.     |
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

pin side (front)
     __--^--__
    /XXXXXXXXX\.
.__/XXXXXXXXXXX\___.
|__________________|
       | | |
       N o P

potentiometer side (reverse)
     __--^--__
    /XXXXXXXXX\.
.__/XXXXXXXXXXX\___.
|__________________|
     |+|  |+|
     A    B
A) Output Duration
B) Sensitivity

The PIR Sensor is difficult to represent with terminal art so I will link it
here as well!
[http://www.diymalls.com/HC-SR501-PIR-Infared-Sensor?search=PIR%20Sens]
"""
from time import sleep

from gpiozero import MotionSensor
from gpiozero import LED

sensor = MotionSensor(14)
light = LED(15)


def turn_on_and_recharge(led: object = light, recharge_time: int = 5):
    """
    Description
    -----------
    Turns on the LED then allows the motion sensor to sleep however long it
    needs to recharge. This should give the illusion of constant motion
    detection at whatever the interval is.

    Params
    ------
    :led: object = light
    the LED you are triggering

    :recharge_time: int = 5
    how many seconds to sleep before proceeding to read the signal again.
    """
    led.on()
    sleep(recharge_time)

# Set this and then just run in an infinite loop until keyboard interrupt. You
# will notice that the sensor gets a singal for activation, then regardless of
# whether or not activity is still happening it shuts off the signal then
# checks again. Despite whatever you set the timing to, the sensor takes a few
# seconds to recharge before it can sense new motion. So it effectively senses
# motion and immediately does the action. The signal to do the action lasts as
# long as you set it for then after the output duration has ended it stops
# regardless of whether or not there is still motion. It then recharges its
# energy bank for the next motion detection, once detected again after
# recharge it will send a new signal. The real world motion cna be non stop
# but the sensor can only send signal in little intervals.
sensor.when_activated =  turn_on_and_recharge
sensor.when_deactivated = light.off

if __name__ == "__main__":
    while True:
        try:
            pass
        except KeyboardInterrupt:
            sensor.close()
            light.close()
