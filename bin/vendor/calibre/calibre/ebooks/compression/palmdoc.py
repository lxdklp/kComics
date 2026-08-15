#!/usr/bin/env python
# License: GPLv3 Copyright: 2008, Kovid Goyal <kovid at kovidgoyal.net>

import io
from struct import pack

# NOTE: original calibre uses the compiled calibre_extensions.cPalmdoc here.
# We substitute the pure-Python implementation below.
def decompress_doc(data):
    return py_decompress_doc(data)


def compress_doc(data):
    return py_compress_doc(data) if data else b''


def py_decompress_doc(data):
    out = bytearray()
    i = 0
    n = len(data)
    while i < n:
        b = data[i]
        i += 1
        if b & 0x80:
            if b & 0x40:
                code = ((b & 0x3f) << 8) | data[i]
                i += 1
                dist = code >> 3
                length = (code & 0x7) + 3
                for _ in range(length):
                    out.append(out[-dist])
            else:
                c = ((b & 0x3f) << 8) | data[i]
                i += 1
                out.extend((c >> 8, c & 0xFF))
        elif b:
            for _ in range(b):
                out.append(data[i])
                i += 1
    return bytes(out)


def py_compress_doc(data):
    out = io.BytesIO()
    i = 0
    ldata = len(data)
    while i < ldata:
        if i > 10 and (ldata - i) > 10:
            chunk = b''
            match = -1
            for j in range(10, 2, -1):
                chunk = data[i : i + j]
                try:
                    match = data.rindex(chunk, 0, i)
                except ValueError:
                    continue
                if (i - match) <= 2047:
                    break
                match = -1
            if match >= 0:
                n = len(chunk)
                m = i - match
                code = 0x8000 + ((m << 3) & 0x3FF8) + (n - 3)
                out.write(pack('>H', code))
                i += n
                continue
        ch = data[i : i + 1]
        och = ord(ch)
        i += 1
        if ch == b' ' and (i + 1) < ldata:
            onch = ord(data[i : i + 1])
            if onch >= 0x40 and onch < 0x80:
                out.write(pack('>B', onch ^ 0x80))
                i += 1
                continue
        if och == 0 or (och > 8 and och < 0x80):
            out.write(ch)
        else:
            j = i
            binseq = [ch]
            while j < ldata and len(binseq) < 8:
                ch = data[j : j + 1]
                och = ord(ch)
                if och == 0 or (och > 8 and och < 0x80):
                    break
                binseq.append(ch)
                j += 1
            out.write(pack('>B', len(binseq)))
            out.write(b''.join(binseq))
            i += len(binseq) - 1
    return out.getvalue()


def find_tests():
    import unittest

    class Test(unittest.TestCase):
        def test_palmdoc_compression(self):
            for test in [
                b'abc\x03\x04\x05\x06ms',  # Test binary writing
                b'a b c \xfed ',  # Test encoding of spaces
                b'0123456789axyz2bxyz2cdfgfo9iuyerh',
                b'0123456789asd0123456789asd|yyzzxxffhhjjkk',
                (b'ciewacnaq eiu743 r787q 0w%  ; sa fd\xef\ffdxosac wocjp acoiecowei owaic jociowapjcivcjpoivjporeivjpoavca; p9aw8743y6r74%$^$^%8 '),
            ]:
                x = compress_doc(test)
                self.assertEqual(py_compress_doc(test), x)
                self.assertEqual(decompress_doc(x), test)

    return unittest.defaultTestLoader.loadTestsFromTestCase(Test)
