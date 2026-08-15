# calibre.utils.xml_parse shim.
from lxml import etree


def parse_xml(raw, *args, **kwargs):
    return etree.fromstring(raw)


def safe_xml_fromstring(raw, *args, **kwargs):
    return etree.fromstring(raw)


def xml_to_unicode(raw):
    if isinstance(raw, str):
        return raw
    return raw.decode('utf-8', 'replace')
