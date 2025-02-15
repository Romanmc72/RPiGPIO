#!/usr/bin/env python3
"""
Description
-----------
This module contains helper code for splitting text into individual words
"""
import re
from typing import List


def text_to_words(text: str) -> List[str]:
    """
    Description
    -----------
    Splits a blob of text into individual words stripping out redundant
    whitespace

    Params
    ------
    :text: str
    The text to split

    Return
    ------
    List[str]
    The list of words found
    """
    return re.split(r"\s+", text)
