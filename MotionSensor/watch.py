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
from time import time

from gpiozero import MotionSensor
from gpiozero import LED


def turn_on_and_wait(sensor: object,
                     led: object,
                     shutdown_after_seconds: int,
                     rescan_after_seconds: int) -> None:
    """
    Description
    -----------
    Turns on the LED if motion is detected and lets it stay on at least as
    long as the :shutdown_after_seconds: variable. It will count by the intervals
    specified in the :rescan_after_seconds:. After that many seconds it will
    wait for addition al motion, if motion is detected it will reset the timer
    until it detects no motion for long enough to shut down.

    Params
    ------
    :light: object = SENSOR
    The sensor you are using to sense for motion.

    :led: object = LIGHT
    The LED you are triggering.

    :shutdown_after_seconds: int = SHUTDOWN_AFTER
    How many seconds to sleep before proceeding to read the signal again.

    :rescan_after_seconds: int = SCAN_INTERVAL
    The number of seconds to wait before scanning again.

    Return
    ------
    None
    """
    started_waiting_time = time()
    while True:
        current_time = time()
        if sensor.motion_detected:
            started_waiting_time = current_time
            print("Motion detected.")
            print(f"{'Keeping' if led.is_lit else 'Turning'} the light on.")
            print("Resetting timer to 0.")
            led.on()
        else:
            print(f"No motion detected for {current_time - started_waiting_time}")
            if current_time - started_waiting_time >= shutdown_after_seconds:
                print(f"No motion detected for greater than {shutdown_after_seconds}. Shutting Down.")
                led.off()
                break
        print(f"Is the light lit?: `{led.is_lit}`")
        sleep(rescan_after_seconds)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser("The program for running the motions sensor and an LED.")
    parser.add_argument(
        '--sensor_pin',
        required=False,
        default=14,
        help="The GPIO pin receiving the sensor output. (default: 14)"
    )
    parser.add_argument(
        '--led_pin',
        required=False,
        default=15,
        help="The GPIO pin sending the signal to trun the LED on or off. (default: 15)"
    )
    parser.add_argument(
        '--shutdown_after_seconds',
        required=False,
        default=5 * 60,
        help="In seconds, how long to wait after no motion is detected to " +
             "shut down the LED. (default: 5 * 60)"
    )
    parser.add_argument(
        '--rescan_after_seconds',
        required=False,
        default=1,
        help="In seconds, how long to wait between motion checks. (default: 1)"
    )
    args = parser.parse_args()
    while True:
        try:
            turn_on_and_wait(
                sensor=MotionSensor(args.sensor_pin),
                led=LED(args.led_pin),
                shutdown_after_seconds=args.shutdown_after_seconds,
                rescan_after_seconds=args.rescan_after_seconds
            )
        except KeyboardInterrupt:
            print("Ending the program.")
            sensor.close()
            light.close()
            break
