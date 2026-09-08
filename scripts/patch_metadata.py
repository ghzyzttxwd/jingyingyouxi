#!/usr/bin/env python3
import sys
from pathlib import Path

src, dst = sys.argv[1:3]
data = bytearray(Path(src).read_bytes())
old = b"2.0X"
new = b"8.0X"
offset = data.find(old)
if offset != 0x212C4 or data.count(old) != 1:
    raise RuntimeError(f"unexpected 2.0X literal location/count: offset={offset:#x}, count={data.count(old)}")
data[offset:offset + len(old)] = new
Path(dst).write_bytes(data)
print(f"[ok] speed label: {old!r} -> {new!r} at metadata offset 0x{offset:X}")
print(dst)
