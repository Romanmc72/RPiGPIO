#!/usr/bin/env python3
"""
Got a new toy!!! The PIR motion sensor senses motion with infrared technology.
Pretty cool.

Here is the hookup on the breadboard:

.__________________________
|\ main board       \ rail \.
| +-----------------+-------+
| | (L1 )----.    .^v^.     |
| |     `----.    X |       |
| |                 |       |
| |  o            O | N   P |
| |                 |       |
| | (L2 )----.    .^v^.     |
| |     `----.    Y |       |
| |                 |       |
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
(L#  )-----. = LED Cathode
     `-----. = LED Anode
X            = GPIO Pin 15
X            = GPIO Pin 18

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
                     detection_led: object,
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
    :light: object
    The sensor you are using to sense for motion.

    :led: object
    The LED you are triggering.

    :detection_led: object
    The LED which will correspond directly with the motion sensor's signals.

    :shutdown_after_seconds: int
    How many seconds to sleep before proceeding to read the signal again.

    :rescan_after_seconds: int
    The number of seconds to wait before scanning again.

    Return
    ------
    None
    """

    # This will add a light that shows when the motion sensor is actually
    # reading motion and sending a signal. This was necessary to tune the
    # potentiometer in order to see what the best trigger duration is. The
    # sensor appears to only be able to send a signal every ~5 seconds, but
    # can have a signal sent which lasts for well over a minute. The
    # potentiometer was very tricky to tune, but as long as your rescan
    # interval and potentiometer are roughly the same interval then you should
    # have no trouble using this. If anything it is better that the
    # potentiometer be tuned to slightly longer.
    sensor.when_motion = detection_led.on
    sensor.when_no_motion = detection_led.off

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
        help="The GPIO pin sending the signal to run the LED on or off. (default: 15)"
    )
    parser.add_argument(
        '--detection_led_pin',
        required=False,
        default=18,
        help="The GPIO pin sending the signal to run the LED detection pin. This pin just follows the sensor's output. (default: 18)"
    )
    parser.add_argument(
        '--shutdown_after_seconds',
        required=False,
        default=5 * 60,
        help="In seconds, how long to wait after no motion is detected to shut down the LED. (default: 5 * 60)"
    )
    parser.add_argument(
        '--rescan_after_seconds',
        required=False,
        default=1,
        help="In seconds, how long to wait between motion checks. (default: 1)"
    )
    args = parser.parse_args()
    sensor = MotionSensor(args.sensor_pin)
    led = LED(args.led_pin)
    detection_led = LED(args.detection_led_pin)
    while True:
        try:
            turn_on_and_wait(
                sensor=sensor,
                led=led,
                detection_led=detection_led,
                shutdown_after_seconds=int(args.shutdown_after_seconds),
                rescan_after_seconds=int(args.rescan_after_seconds)
            )
        except KeyboardInterrupt:
            print("Ending the program.")
            sensor.close()
            led.close()
            detection_led.close()
            break
