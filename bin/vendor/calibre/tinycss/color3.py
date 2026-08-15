# tinycss.color3 shim: parse_color_string used by calibre.ebooks.mobi.utils
# convert_color_for_font_tag. Returns an (r,g,b,a) tuple or None.
import re


def parse_color_string(value, default_color=None):
    if value is None:
        return None
    value = str(value).strip().lower()
    if value == 'transparent':
        return (0, 0, 0, 0)
    if value.startswith('#'):
        v = value[1:]
        if len(v) == 3:
            v = ''.join(c * 2 for c in v)
        if len(v) == 6:
            try:
                return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16), 1.0)
            except ValueError:
                return None
        return None
    m = re.match(r'rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)', value)
    if m:
        g = m.groups()
        try:
            r, gr, b = (float(g[0]), float(g[1]), float(g[2]))
            a = float(g[3]) if g[3] else 1.0
            return (r / 255.0 if r > 1 else r, gr / 255.0 if gr > 1 else gr,
                    b / 255.0 if b > 1 else b, a)
        except ValueError:
            return None
    named = {
        'red': (1, 0, 0), 'green': (0, 1, 0), 'blue': (0, 0, 1),
        'black': (0, 0, 0), 'white': (1, 1, 1), 'gray': (0.5, 0.5, 0.5),
        'grey': (0.5, 0.5, 0.5), 'yellow': (1, 1, 0), 'cyan': (0, 1, 1),
        'magenta': (1, 0, 1), 'silver': (0.75, 0.75, 0.75), 'maroon': (0.5, 0, 0),
        'olive': (0.5, 0.5, 0), 'lime': (0, 1, 0), 'teal': (0, 0.5, 0.5),
        'aqua': (0, 1, 1), 'navy': (0, 0, 0.5), 'fuchsia': (1, 0, 1),
        'purple': (0.5, 0, 0.5), 'orange': (1, 0.65, 0), 'pink': (1, 0.75, 0.8),
    }
    return named.get(value)
