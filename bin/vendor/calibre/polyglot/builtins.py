# polyglot.builtins shim.
unicode_type = str


def as_bytes(x):
    if isinstance(x, str):
        return x.encode('utf-8')
    if isinstance(x, bytes):
        return x
    return str(x).encode('utf-8')


def as_unicode(x, enc='utf-8', errors='strict'):
    if isinstance(x, str):
        return x
    if isinstance(x, bytes):
        return x.decode(enc, errors)
    return str(x)


def string_types():
    return (str,)


def unicode_has_break_opportunities(x):
    return True
