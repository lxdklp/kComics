# calibre.utils.icu shim: pure-Python Unicode helpers (original uses compiled ICU).
import unicodedata


def normalize_str(x, mode):
    return unicodedata.normalize(mode, str(x))


def uppercase(x):
    return str(x).upper()


def lowercase(x):
    return str(x).lower()


def titlecase(x):
    return str(x).title()


def strip_accents(x):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(x)) if not unicodedata.combining(c))


def collation_sort_key(x):
    return str(x).lower()


def strcmp(a, b):
    return (a > b) - (a < b)


def sort_key_for(x):
    return str(x).lower()


def primary_sort_key(x):
    return str(x).lower()


def secondary_sort_key(x):
    return str(x)


def default_unicode_category(x):
    return unicodedata.category(x)


def char_name(x):
    return unicodedata.name(x, '')
