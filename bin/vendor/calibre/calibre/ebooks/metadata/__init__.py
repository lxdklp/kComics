# calibre.ebooks.metadata shim (minimal).
from collections.abc import MutableMapping


class MetaInformation(MutableMapping):
    """Minimal stand-in for calibre's MetaInformation. A dict of lists with
    attribute access, sufficient for the writer8 EXTH/header path."""

    def __init__(self, title=None, authors=(), comments=None, tags=None, language=None, identifiers=None):
        self._data = {}
        if title:
            self._data['title'] = [title]
        if authors:
            self._data['creator'] = list(authors)
        if language:
            self._data['language'] = [language]
        self.set_identifier('uuid', 'uuid-gen-by-kcomics')

    # mapping interface
    def __getitem__(self, key):
        return self._data[key]

    def __setitem__(self, key, val):
        self._data[key] = val

    def __delitem__(self, key):
        del self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def __contains__(self, key):
        return key in self._data

    # attribute access to common fields
    def _list(self, name):
        return self._data.get(name, [])

    @property
    def title(self):
        return self._list('title')

    @property
    def creators(self):
        return self._list('creator')

    @property
    def language(self):
        return self._list('language')

    @property
    def rights(self):
        return self._list('rights')

    @property
    def cover(self):
        return self._list('cover')

    def set_identifier(self, scheme, val):
        self._data.setdefault('identifier', []).append(Identifier(scheme, val))


class Identifier:
    def __init__(self, scheme, value):
        self.scheme = scheme
        self.value = value

    def __str__(self):
        return self.value

    def get(self, key, default=None):
        return self.scheme if key.rpartition('}')[-1] == 'scheme' else default


def authors_to_sort_string(authors):
    """Given a list of author name strings, return a single sort string."""
    ans = []
    for a in authors:
        a = str(a).strip()
        if not a:
            continue
        if ',' in a:
            ans.append(a)
        else:
            parts = a.split()
            ans.append(' '.join(reversed(parts)) if len(parts) > 1 else a)
    return ' & '.join(ans)


def check_isbn(x):
    return x
