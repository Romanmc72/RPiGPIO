#!/usr/bin/env python3
"""
This application is to be used on a RaspberryPi that has the camera installed
and turned on as well as the `raspistill' cli tool for taking pictures.

Essentially this will take the picture and stream the image to stdout in
base64. The client that picks up this bas64 encoded string can then
decode it, save it to disk and display it themselves.
"""
import sys
import base64
import subprocess

from logs import get_logger

LOGGER = get_logger()


def take_picture() -> bytes:
    """Takes the picture and streams the data to bytes"""
    # Not useing the check=True flag because if this fails I want to
    # pass that further downstream to the client application.
    output = subprocess.run(
        ['raspistill', '-o', '-', '-t', '1'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    if output.stderr:
        LOGGER.error('Encountered an error!')
        LOGGER.error(output.stderr.decode('utf-8'))
        return output.stderr.decode('utf-8')
    else:
        return base64.standard_b64encode(output.stdout)


if __name__ == "__main__":
    picture = take_picture()
    sys.stdout.write(picture.decode('utf-8'))
