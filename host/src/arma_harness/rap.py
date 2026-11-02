"""raP (binarized config / mission.sqm) -> text config. Stdlib only.

Usage: python derapify.py <in.sqm> <out.sqm>
"""
import struct
import sys
from pathlib import Path


class Reader:
    def __init__(self, data: bytes):
        self.d = data

    def asciiz(self, i):
        j = self.d.index(b"\0", i)
        return self.d[i:j].decode("utf-8"), j + 1

    def cint(self, i):
        """7-bit little-endian varint."""
        val, shift = 0, 0
        while True:
            b = self.d[i]
            i += 1
            val |= (b & 0x7F) << shift
            if not b & 0x80:
                return val, i
            shift += 7

    def u32(self, i):
        return struct.unpack_from("<I", self.d, i)[0], i + 4

    def f32(self, i):
        return struct.unpack_from("<f", self.d, i)[0], i + 4

    def i32(self, i):
        return struct.unpack_from("<i", self.d, i)[0], i + 4

    def i64(self, i):
        return struct.unpack_from("<q", self.d, i)[0], i + 8


def fmt_float(x: float) -> str:
    bits = struct.pack("<f", x)
    if x == int(x) and abs(x) < 1e7:
        return str(int(x))
    for p in range(1, 10):
        s = f"{x:.{p}g}"
        if struct.pack("<f", float(s)) == bits:
            return s
    return repr(x)


def fmt_str(s: str) -> str:
    s = s.replace('"', '""')
    # Config syntax for embedded newlines: "a" \n "b"
    s = s.replace("\r\n", "\n").replace("\n", '" \\n "')
    return f'"{s}"'


def read_array(r: Reader, i):
    n, i = r.cint(i)
    out = []
    for _ in range(n):
        t = r.d[i]
        i += 1
        if t in (0, 4):
            s, i = r.asciiz(i)
            out.append(fmt_str(s) if t == 0 else s)
        elif t == 1:
            v, i = r.f32(i)
            out.append(fmt_float(v))
        elif t == 2:
            v, i = r.i32(i)
            out.append(str(v))
        elif t == 3:
            sub, i = read_array(r, i)
            out.append(sub)
        elif t == 6:
            v, i = r.i64(i)
            out.append(str(v))
        else:
            raise ValueError(f"array element type {t} at {i - 1}")
    return out, i


def fmt_array(a, indent):
    if not any(isinstance(x, list) for x in a) and sum(len(x) for x in a) < 80:
        return "{" + ",".join(a) + "}"
    pad = "\t" * (indent + 1)
    parts = [pad + (fmt_array(x, indent + 1) if isinstance(x, list) else x) for x in a]
    return "\n" + "\t" * indent + "{\n" + ",\n".join(parts) + "\n" + "\t" * indent + "}"


def write_class_body(r: Reader, i, indent, out):
    _parent, i = r.asciiz(i)
    n, i = r.cint(i)
    pad = "\t" * indent
    for _ in range(n):
        t = r.d[i]
        i += 1
        if t == 0:
            name, i = r.asciiz(i)
            off, i = r.u32(i)
            parent, _ = r.asciiz(off)
            head = f"class {name}" + (f": {parent}" if parent else "")
            out.append(f"{pad}{head}\n{pad}{{")
            write_class_body(r, off, indent + 1, out)
            out.append(f"{pad}}};")
        elif t == 1:
            sub = r.d[i]
            i += 1
            name, i = r.asciiz(i)
            if sub == 0:
                v, i = r.asciiz(i)
                v = fmt_str(v)
            elif sub == 1:
                f, i = r.f32(i)
                v = fmt_float(f)
            elif sub == 2:
                n2, i = r.i32(i)
                v = str(n2)
            elif sub == 6:
                n2, i = r.i64(i)
                v = str(n2)
            else:
                raise ValueError(f"value subtype {sub}")
            out.append(f"{pad}{name}={v};")
        elif t in (2, 5):
            op = "="
            if t == 5:
                flag, i = r.u32(i)
                op = "+=" if flag == 1 else "="
            name, i = r.asciiz(i)
            arr, i = read_array(r, i)
            out.append(f"{pad}{name}[]{op}{fmt_array(arr, indent)};")
        elif t == 3:
            name, i = r.asciiz(i)
            out.append(f"{pad}class {name};")
        elif t == 4:
            name, i = r.asciiz(i)
            out.append(f"{pad}delete {name};")
        else:
            raise ValueError(f"entry type {t} at {i - 1}")
    return i


def derapify(data: bytes) -> str:
    assert data[:4] == b"\0raP", "not a raP file"
    r = Reader(data)
    out = []
    write_class_body(r, 16, 0, out)
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    text = derapify(src.read_bytes())
    dst.write_text(text, encoding="utf-8", newline="\n")
    print(f"{len(text.splitlines())} lines -> {dst}")
