# calibre.utils.localization shim.
# Minimal gettext no-op and language helpers for the copied writer8 pipeline.

_lang_map = {
    'chinese': 'zh', 'english': 'en', 'french': 'fr', 'german': 'de',
    'japanese': 'ja', 'korean': 'ko', 'spanish': 'es', 'italian': 'it',
    'portuguese': 'pt', 'russian': 'ru', 'dutch': 'nl', 'polish': 'pl',
    'turkish': 'tr', 'arabic': 'ar', 'hebrew': 'he', 'hindi': 'hi',
    'thai': 'th', 'vietnamese': 'vi', 'zh': 'zh', 'en': 'en',
    'zh-cn': 'zh', 'zh-tw': 'zh', 'en-us': 'en', 'en-gb': 'en',
}


def _(text):
    return text


def __(text):
    return text


def ngettext(single, plural, n):
    return single if n == 1 else plural


def canonicalize_lang(lang):
    if not lang:
        return None
    lang = str(lang).lower()
    return _lang_map.get(lang, lang[:2] if len(lang) > 2 else lang)


def lang_as_iso639_1(lang):
    if not lang:
        return None
    lang = str(lang).lower()
    if lang in _lang_map:
        return _lang_map[lang]
    if '-' in lang:
        return lang.split('-')[0]
    return lang if len(lang) == 2 else None
