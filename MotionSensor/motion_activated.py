#!/usr/bin/env python3
"""
The class that tracks motion from a PIR sensor.

This program has been triggered on startup from `/etc/rc.local`
"""
import logging
from time import sleep
from typing import Optional

from gpiozero import MotionSensor
from gpiozero import LED

from logs import get_logger

LOGGER = get_logger("MotionActivated")

class MotionActivated:
    def __init__(self, sensor_pin: int, activator_pin: int, activation_duration: int, debug_pin: Optional[int] = None) -> None:
        """
        Description
        -----------
        This class makes it easy to capture and run input from a PIR sensor on
        one pin and control the output on another pin.

        Params
        ------
        :sensor_pin: int
        The pin that the motion sensor will be tied to for input.

        :activator_pin: int
        The pin that will receive on/off signals from the motion
        sensor that this class will process.
        
        :activation_duration: int
        How many seconds that the activator should stay on for before being
        shut off.

        :debug_pin: Optional[int] = None
        The optional debug pin that ties to something to activate whenever any
        motion is detected at all. This helps to debug while tuning the
        potentiometer.

        Wiring
        ------
        The PIR motion sensor senses motion with infrared technology.

        Here is the hookup on the breadboard for 2 simple LEDs:

        ```
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
        ======
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
        Y            = GPIO Pin 18

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

        ```

        The PIR Sensor is difficult to represent with terminal art so I will link it
        here as well!
        https://www.mpja.com/download/31227sc.pdf
        """
        self.sensor_pin = sensor_pin
        self.sensor = MotionSensor(sensor_pin)
        self.sensor.when_motion = self._sense_motion
        self.sensor.when_no_motion = self._no_motion_sensed
        if activation_duration <= 6:
            raise ValueError("Cannot specify an activation duration less than 6 seconds.")
        self.activation_duration = activation_duration
        self.activated_for = 0
        self.activator_pin = activator_pin
        self.activator = LED(activator_pin)
        self.debug_pin = debug_pin
        self.debug = LED(debug_pin) if debug_pin else None
        if self.debug:
            LOGGER.setLevel(logging.DEBUG)
        else:
            LOGGER.setLevel(logging.INFO)
        LOGGER.info(
            f"Initialized Motion Sensor to {sensor_pin=}, {activator_pin=}, " +
            f"{activation_duration=}, {debug_pin=}"
        )

    def _sense_motion(self):
        LOGGER.info(
            f"Motion detected, resetting timer from {self.activated_for} " +
            f"to {self.activation_duration}."
        )
        self.activated_for = self.activation_duration
        self.activator.on()
        if self.debug:
            self.debug.on()

    def _no_motion_sensed(self):
        if self.debug:
            LOGGER.debug("No motion detected...")
            self.debug.off()

    def run(self):
        LOGGER.info("Beginning to watch the lights...")
        try:
            while True:
                sleep(1)
                if self.activated_for <= 0:
                    self.activator.off()
                    continue
                self.activated_for -= 1
        finally:
            LOGGER.error("Sensor shutdown detected! Shutting things off.")
            self.activator.off()
            if self.debug:
                self.debug.off()
            LOGGER.debug("Done.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description=MotionActivated.__init__.__doc__,
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument("--sensor_pin", type=int)
    parser.add_argument("--activator_pin", type=int)
    parser.add_argument("--activation_duration", type=int, default=30)
    parser.add_argument("--debug_pin", required=False, default=None)

    args = parser.parse_args()

    sensor = MotionActivated(
        sensor_pin=args.sensor_pin,
        activator_pin=args.activator_pin,
        activation_duration=args.activation_duration,
        debug_pin=args.debug_pin,
    )
    sensor.run()
