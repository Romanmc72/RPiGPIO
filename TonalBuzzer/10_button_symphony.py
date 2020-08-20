#!/usr/bin/env python2
"""
Rigged up 10 buttons and 1 buzzer. This can be used with any number of
buttons >= 1. Here is what I did on the breadboard.

Description
===========
There is one 3.3V pin supplying input power to the buttons and the GPIO pins
are set up to listen for the button to close the circuit.

.__________________________
|\ main board       \ rail \.
| +-----------------+-------+
| | [o]-.         .^v^.     |
| |   `-.         P |       |
| | [o]-.         .^v^.     |
| |   `-.         P |       |
| | [o]-.         .^v^.     |
| |   `-.         P |       |
| | [o]-.         .^v^.     |
| |   `-.         P |       |
| | [o]-.         .^v^.     |
| |   `-.         P | +     |
//////////////////////////////
repeat for 10 buttons
//////////////////////////////
| |  ___.--     -   |       |
| | ( o )           |       |
| |  ---`--     P   |       |
| |                 |       |
| |                 |       |
 \+-----------------+-------+

Legend
======
+-------------------------------------+
| P            = GPIO Pin Connection  |
+-------------------------------------+
| +            = 3.3V Pin Connection  |
+-------------------------------------+
| -            = Ground Pin Connection|
+-------------------------------------+
| .^v^.        = 1k ohm Resistor      |
+-------------------------------------+
| [o]-.        = button & anode       |
|   `-.        = button & cathnode    |
+-------------------------------------+
|  ___.--      = buzzer cathode       |
| ( o )        = buzzer               |
|  ---`--      = buzzer anode         |
+-------------------------------------+
"""
from time import sleep

from gpiozero import TonalBuzzer
from gpiozero import Button
from gpiozero.tones import Tone


def play_me(my_buzzer, my_buttons, reactivity=0.1):
    """
    Description
    -----------
    Play the buzzer with some arbitrary number of GPIO buttons all hooked up!

    Params
    ------
    :my_buzzer: gpiozero.TonalBuzzer
    The buzzer object you will be buzzing.

    :buttons: list[gpiozero.Button]
    A list of buttons that you will be using to play said buzzer. The order of
    the list will dictate where in the evaluation order that the button will
    take priority. The buttons with lower indices, if pressed, will be
    prioritized over buttons with higher indices that are also pressed. There
    can only be one tone played at a time.

    :reactivity: float = 0.1

    Return
    ------
    None
    """

    # Creates a dictionary correlating the index in the button list to a
    # dictionary key containing values representing evenly spaced intervals
    # between the minimum and maximum tone for the provided buzzer
    tones_to_listen_for = {
        k: (
            k * (
                my_buzzer.max_tone.frequency - my_buzzer.min_tone
            ) / len(my_buttons)
        ) + my_buzzer.min_tone.frequency 
        for k, v in enumerate(my_buttons)
    }

    # Infinite loop that sets the buzzer to the tone of the
    # button that is first pressed
    while True:
        for i, button in enumerate(my_buttons):
            if button.is_pressed:
                my_buzzer.play(Tone(tones_to_listen_for[i]))
                break
            else:
                my_buzzer.play(None)
        print(my_buzzer.tone)
        sleep(reactivity)


if __name__ == "__main__":
    pins = [
        14,
        15,
        18,
        23,
        24,
        25,
        8,
        7,
        1,
        12,
        16
    ]
    buzzer = TonalBuzzer(pins[0])
    buttons = [Button(pin, pull_up=False) for pin in pins[1::]]
    play_me(my_buzzer=buzzer, my_buttons=buttons)
