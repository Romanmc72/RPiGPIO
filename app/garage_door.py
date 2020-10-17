#!usr/bin/env python2
"""
This application is intended to open and close the garage door to my house
using existing gpio abstractions for LEDs. The garage door operates on a 5V
relay hooked up to the Raspberry Pi. The Raspberry Pi operates the relay
switch via GPIO and the garage door's circuit is hooked up to the relay's NO
(Normally Open) connection. Once the GPIO pin is triggered, it closes the NO
and completes the circuit sending a charge through the garage door and changes
it from open to closed or vice versa.

This program is ignorant of the state of the garage door. That will be left to
another program to decipher.
"""
import os
from time import sleep
import argparse
from logs import get_logger

from gpiozero import LED


if __name__ == "__main__":
    logger = get_logger()
    logger.info("Beginning garage door app.")
    parser = argparse.ArgumentParser("Open/close the garage door.")
    parser.add_argument(
        '--pin',
        default=os.getenv('GARAGE_DOOR_PIN', 14),
        required=False,
        type=int,
        help="The GPIO pin for the garage door on the Pi."
    )
    args = parser.parse_args()
    logger.info("Connecting garage door opener to pin ({pin})".format(pin=args.pin))
    try:
        garage_door = LED(args.pin, active_high=False)
        logger.info("Triggering garage door.")
        garage_door.toggle()
        sleep(0.5)
        garage_door.toggle()
        logger.info("Garage door has changed its state.")
    finally:
        # This closes the pin connection to the program so that the pin can be
        # readily used again by the next caller even if the above fails for
        # whatever reason.
        garage_door.close()
    logger.info("Ending garage door app.")