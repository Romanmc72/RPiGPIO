#!/usr/bin/env python2
"""
Storing the logger object here.
"""
import sys
import logging


def get_logger(name = "raspberry_pi"):
    logging.basicConfig(
        format="%(asctime)s||%(pathname)s||%(name)s||%(levelname)s||%(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        level=logging.DEBUG,
        stream=sys.stdout
    )
    return logging.getLogger(name)


if __name__ == "__main__":
    logger = get_logger(name="test_logging")
    logger.info("Info Test")
    logger.warn("Warning Test")
    logger.error("Error Test")
    logger.critical("Critical Test")
