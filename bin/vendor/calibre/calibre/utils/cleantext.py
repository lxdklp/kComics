# calibre.utils.cleantext shim.
import html
import re


def clean_ascii_chars(x, replace_with=''):
    return x


def clean_xml_chars(x, replace_with=''):
    if x is None:
        return x
    return x.replace('\x00', '')


def remove_control_characters(x):
    return ''.join(c for c in str(x) if c >= ' ' or c in '\t\n\r')
