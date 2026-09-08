#!/usr/bin/env python3
import struct
import sys
import zipfile
from pathlib import Path

src, patched_so, dst = sys.argv[1:4]
patched = Path(patched_so).read_bytes()
sig_suffixes = ('.RSA', '.DSA', '.EC', '.SF', '.MF')


def pad_extra_for_alignment(header_offset: int, filename_bytes: bytes, extra: bytes, alignment: int = 4) -> bytes:
    """给 ZIP local header 追加合法 extra field，使 entry data 按 alignment 对齐。"""
    base = header_offset + 30 + len(filename_bytes) + len(extra)
    need = (-base) % alignment
    if need == 0:
        return extra
    # extra field: uint16 id + uint16 data_size + data
    # 总长度 4+need，模 4 与 need 相同。
    return extra + struct.pack('<HH', 0xCAFE, need) + (b'\0' * need)


with zipfile.ZipFile(src, 'r') as zin, zipfile.ZipFile(dst, 'w', allowZip64=True) as zout:
    for info in zin.infolist():
        name = info.filename
        upper = name.upper()
        if upper.startswith('META-INF/') and upper.endswith(sig_suffixes):
            continue

        data = patched if name == 'lib/arm64-v8a/libil2cpp.so' else zin.read(name)
        ni = zipfile.ZipInfo(filename=name, date_time=info.date_time)
        ni.compress_type = info.compress_type
        ni.comment = info.comment
        ni.extra = info.extra
        ni.internal_attr = info.internal_attr
        ni.external_attr = info.external_attr
        ni.create_system = info.create_system
        ni.flag_bits = info.flag_bits & ~0x08
        ni.extract_version = info.extract_version
        ni.create_version = info.create_version

        # targetSdk 35：resources.arsc 保持不压缩并保证 4-byte alignment。
        if name == 'resources.arsc':
            filename_bytes, _ = ni._encodeFilenameFlags()
            ni.extra = pad_extra_for_alignment(zout.fp.tell(), filename_bytes, ni.extra, 4)

        zout.writestr(ni, data)

print(dst)
