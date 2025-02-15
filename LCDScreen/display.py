#!/usr/bin/env python3
"""
Description
-----------
A helper class for writing to the LCD display
"""
import logging
from datetime import datetime
from time import sleep
from typing import List

from RPLCD import i2c

from dates import DEFAULT_TIMEZONE, get_current_datetime_at_tz

logger = logging.getLogger()


class LCDDisplay(i2c.CharLCD):
    """
    Description
    -----------
    A wrapper around the i2c LCD Character Display that allows for more easily
    performing common LCD Display related tasks. Much of the code here presumes
    that you are using the same LCD Display that is 20X04 so some methods may
    not work on other displays of smaller sizes.
    """
    def __init__(
        self,
        i2c_expander: str = 'PCF8574',
        address: int = 0x27,
        port: int = 1,
        charmap: str = 'A00',
        cols: int = 20,
        rows: int = 4,
        letter_delay: float = 0.05,
        word_delay: float = 0.3,
        clear_delay: float = 1.0,
    ) -> None:
        """
        Description
        -----------
        Initializes the display. See the i2c module for info on all of the
        input params not covered here.

        Params
        ------
        :letter_delay: float = 0.05
        For certain methods that write one letter at a time, the delay between
        writing each additional letter to the display
    
        :word_delay: float = 0.3
        For certain methods that write one word at a time, the delay between
        writing each additional word to the display
    
        :clear_delay: float = 1.0
        For certain methods that write one block of the display at a time,
        the delay between clearing the display and writing again
        """
        super().__init__(
            i2c_expander=i2c_expander,
            address=address,
            port=port,
            charmap=charmap,
            cols=cols,
            rows=rows,
        )
        self.letter_delay = letter_delay
        self.word_delay = word_delay
        self.clear_delay = clear_delay

    def write_words(self, words: List[str], repeat: int = 0) -> None:
        """
        Description
        -----------
        Write a series of lines to the display one letter at a time with a
        brief pause between each word and an even briefer pause between each
        letter

        Params
        ------
        :words: List[str]
        The list of words to write to the screen

        :repeat: int = 0
        How many times to repeat (in addition to the first time the words are written)
        Example: repeat = 2 will be a total of 3 times
        """
        try:
            self.clear()
            for word in words:
                word_len = len(word) + 1
                end_of_line = self.cursor_pos[1] + word_len > self.lcd.cols
                end_of_display = self.cursor_pos[0] == self.lcd.rows - 1
                big_word = word_len > self.lcd.cols
                if (
                    (end_of_display and end_of_line)
                    or self.cursor_pos == (0, 0)
                ):
                        sleep(self.clear_delay)
                        self.clear()
                        end_of_display = False
                elif end_of_line and not big_word:
                        self.cursor_pos = (self.cursor_pos[0] + 1, 0)
                for letter in word:
                        self.write_string(letter)
                        sleep(self.letter_delay)
                self.write_string(" ")
                sleep(self.word_delay)
            repeat_count = repeat - 1
            if repeat < 0:
                logger.warning("Infinitely repeating these lines!")
                self.write_words(words, repeat=repeat_count)
            elif repeat > 0:
                logger.info(f"Repeating {repeat_count} more times")
                self.write_words(words, repeat=repeat_count)
            else:
                logger.info("Finished writing lines")
        except KeyboardInterrupt:
            self.clear()

    def _get_blank_display_array(self) -> None:
        return [" " for _ in range(self.lcd.rows * self.lcd.cols)]

    def flow_text(self, text: str) -> None:
        """
        Description
        -----------
        Flow a long string of text through the display starting at the bottom
        left and incrementing one character at a time until the entire message
        has flowed

        Params
        ------
        :text: str
        The body of text to flow across the screen

        Return
        ------
        None
        """
        current_display = self._get_blank_display_array()
        self.clear()
        for letter in text:
            current_display.append(letter)
            current_display.pop(0)
            self.clear()
            self.write_string("".join(current_display))
            sleep(self.letter_delay)
        for blank_space in self._get_blank_display_array():
            current_display.append(blank_space)
            current_display.pop(0)
            self.clear()
            self.write_string("".join(current_display))
            sleep(self.letter_delay)
        self.clear()

    def write_line(self, text: str, line_no: int) -> None:
        """
        Description
        -----------
        Writes text to a particular line, overwriting what was previously on
        that line

        Params
        ------
        :text: str
        The text to write onto the line

        :line_no: int
        The line number (zero based index) to write the text to
        """
        if 0 > line_no >= self.lcd.rows:
            raise IndexError(
                f"line_no {line_no} out of range for LCDDisplay.write_line()"
            )
        text_size = len(text)
        if text_size > self.lcd.cols:
            raise OverflowError(
                f"text size {text_size} provided is greater than max line "
                + "size for display"
            )
        self.cursor_pos = (line_no, 0)
        self.write_string(text + (" " * (self.lcd.cols - text_size)))

    def show_time(self, dt: datetime) -> None:
        """
        Description
        -----------
        Given a datetime object, will write out the components of the datetime
        as strings to the LCD Display.

        Params
        ------
        :dt: datetime
        The datetime to display
        """
        weekday = dt.strftime("%A")
        full_date = dt.strftime("%B %d, %Y")
        time_part = dt.strftime("%I:%M:%S %p %Z")
        self.write_line(weekday, 0)
        self.write_line(full_date, 1)
        self.write_line(time_part, 2)

    def show_current_time(self, tzname: str = DEFAULT_TIMEZONE) -> None:
        """
        Description
        -----------
        Show the current time using the input timezone name

        Params
        ------
        :tzname: str = DEFAULT_TIMEZONE (see dates module)
        The unique name of the timezone to display current time for
        """
        self.show_time(get_current_datetime_at_tz(tzname))
