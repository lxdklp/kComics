# calibre.utils.short_uuid shim.
import uuid


def uuid4():
    return uuid.uuid4()


def uuid4_hex():
    return uuid.uuid4().hex
