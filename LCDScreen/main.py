#!/usr/bin/env python3
"""
Description
-----------
This program is designed to work with the i2c controller interface on a
raspberry pi (using a zero for this example) connected to a 20x04 LCD
display. If your display has other characteristics then use those below.

Wiring Diagram
--------------
I am using a ribbon cable with 4 ribbons to connect the Pi to the display,
here are those connections mapped out:

                    +---------------------------+
                    | +-----------------------+ |
                    | |                       | |
LCD Display         | |          Pi Zero      | |
------------+       | |       +------------+  | |
        +-------+   | |       |        . X-^--+ |
        | GND X-^---+ | +-----^--------X . |    | 
i2c --> | VCC X-^-----+ | +---^--------X X-^----+
        | SDA X-^-------+ |   |        . . |
        | SCL X-^---------+   |        . . |  Legend
        +-------+             |        . . |  ------
            |                 |        . . |  Pin 2 (5v)      = VCC
            |                 |        . . |  Pin 3 (i2c/SDA) = SDA
            |                 |        . . |  Pin 5 (i2c/SCL) = SCL
------------+                 |        . . |  Pin 6 (GND)     = GND

Running the Program
-------------------
For now it will be a module with the capability to be run via command line.
You can call this ./main.py file directly and pass in the help flags to see
this help text and any additional context on running the program.
"""
from typing import List

from display import LCDDisplay
from splittext import text_to_words


def show_text(
    lines: List[str],
    display: LCDDisplay = None,
) -> None:
    """
    Description
    -----------
    Show a series of lines of text on the display. The lines will flow from
    the first to the last line in the list for as many lines as exist in the
    array of lines of text to show. It will repeat as many times as you like
    (0 by default)

    Params
    ------
    :lines: List[str]
    The array of lines of text to show

    :display: LCDDisplay = None
    The initialized LCD Character display
    """
    if not display:
        display = LCDDisplay()
    
    display.write_words(lines)


if __name__ == "__main__":
    import argparse
    from argparse import RawTextHelpFormatter

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=RawTextHelpFormatter,
    )

    parser.add_argument(
        "--message",
        type=str,
        help="The message to display on the LCD screen",
    )

    args = parser.parse_args()

    show_text(lines=text_to_words(args.message))
