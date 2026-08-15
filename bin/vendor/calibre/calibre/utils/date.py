# calibre.utils.date shim.
from datetime import datetime


def parse_date(val, as_utc=True):
    try:
        return datetime.fromisoformat(str(val).replace('Z', '+00:00'))
    except Exception:
        return datetime.now()
