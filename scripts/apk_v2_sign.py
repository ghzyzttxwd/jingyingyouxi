#!/usr/bin/env python3
"""最小 APK Signature Scheme v2 签名/自检工具。

当前工程 minSdk=24，因此测试包只需要 v2 即覆盖最低支持系统。
依赖：cryptography
"""
import hashlib
import struct
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID

V2_ID = 0x7109871A
ALG_RSA_PKCS1_SHA256 = 0x0103
MAGIC = b'APK Sig Block 42'
CHUNK = 1024 * 1024


def u32(n):
    return struct.pack('<I', n)


def u64(n):
    return struct.pack('<Q', n)


def lp(b):
    return u32(len(b)) + b


def find_eocd(data: bytes):
    start = max(0, len(data) - (22 + 65535))
    pos = data.rfind(b'PK\x05\x06', start)
    if pos < 0:
        raise ValueError('EOCD not found')
    if pos + 22 > len(data):
        raise ValueError('truncated EOCD')
    comment_len = struct.unpack_from('<H', data, pos + 20)[0]
    if pos + 22 + comment_len != len(data):
        raise ValueError('EOCD not at end / trailing data unsupported')
    disk_no, cd_disk, disk_entries, total_entries, cd_size, cd_off = struct.unpack_from('<HHHHII', data, pos + 4)
    if disk_no or cd_disk or disk_entries != total_entries:
        raise ValueError('multi-disk ZIP unsupported')
    if cd_off == 0xFFFFFFFF or cd_size == 0xFFFFFFFF or total_entries == 0xFFFF:
        raise ValueError('ZIP64 unsupported')
    if cd_off + cd_size != pos:
        raise ValueError('unexpected central-directory layout')
    return pos, cd_off, cd_size


def chunked_digest(sections):
    chunk_digests = []
    for sec in sections:
        mv = memoryview(sec)
        for i in range(0, len(sec), CHUNK):
            c = mv[i:i + CHUNK]
            h = hashlib.sha256()
            h.update(b'\xA5')
            h.update(u32(len(c)))
            h.update(c)
            chunk_digests.append(h.digest())
    h = hashlib.sha256()
    h.update(b'\x5A')
    h.update(u32(len(chunk_digests)))
    for d in chunk_digests:
        h.update(d)
    return h.digest()


def make_key_cert():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, 'jingyingyouxi mod'),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Local Mod Build'),
    ])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    return key, cert


def build_v2_value(content_digest: bytes, key, cert):
    cert_der = cert.public_bytes(serialization.Encoding.DER)
    pub_der = key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    digest_record = u32(ALG_RSA_PKCS1_SHA256) + lp(content_digest)
    digests_seq = lp(digest_record)
    certs_seq = lp(cert_der)
    attrs_seq = b''
    signed_data = lp(digests_seq) + lp(certs_seq) + lp(attrs_seq)

    signature = key.sign(signed_data, padding.PKCS1v15(), hashes.SHA256())
    sig_record = u32(ALG_RSA_PKCS1_SHA256) + lp(signature)
    signatures_seq = lp(sig_record)

    signer = lp(signed_data) + lp(signatures_seq) + lp(pub_der)
    # v2 value 本身是“length-prefixed signer sequence”，而 sequence 内的
    # 每一个 signer 又是 length-prefixed。V0.1 漏掉了最外层这一层。
    signers_seq = lp(signer)
    v2_value = lp(signers_seq)
    return v2_value, signed_data, signature, cert_der, pub_der


def make_signing_block(v2_value: bytes):
    pair = u64(4 + len(v2_value)) + u32(V2_ID) + v2_value
    size = len(pair) + 8 + 16
    return u64(size) + pair + u64(size) + MAGIC


def sign_apk(src, dst, key_out=None, cert_out=None):
    data = Path(src).read_bytes()
    eocd_pos, cd_off, _ = find_eocd(data)

    section1 = data[:cd_off]
    section3 = data[cd_off:eocd_pos]
    eocd_for_digest = bytearray(data[eocd_pos:])
    struct.pack_into('<I', eocd_for_digest, 16, cd_off)
    digest = chunked_digest([section1, section3, bytes(eocd_for_digest)])

    key, cert = make_key_cert()
    v2_value, signed_data, signature, cert_der, pub_der = build_v2_value(digest, key, cert)
    block = make_signing_block(v2_value)

    key.public_key().verify(signature, signed_data, padding.PKCS1v15(), hashes.SHA256())
    cert_pub = cert.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    if cert_pub != pub_der:
        raise RuntimeError('certificate/public key mismatch')

    new_cd_off = cd_off + len(block)
    eocd_out = bytearray(data[eocd_pos:])
    struct.pack_into('<I', eocd_out, 16, new_cd_off)
    Path(dst).write_bytes(section1 + block + section3 + bytes(eocd_out))

    if key_out:
        Path(key_out).write_bytes(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
    if cert_out:
        Path(cert_out).write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    print('digest', digest.hex())
    print('signing_block_bytes', len(block))
    print('cert_sha256', hashlib.sha256(cert_der).hexdigest())
    print(dst)


def parse_and_verify(apk):
    data = Path(apk).read_bytes()
    eocd_pos, cd_off, _ = find_eocd(data)
    if data[cd_off - 16:cd_off] != MAGIC:
        raise ValueError('APK Sig Block magic missing')

    size2 = struct.unpack_from('<Q', data, cd_off - 24)[0]
    block_start = cd_off - (size2 + 8)
    size1 = struct.unpack_from('<Q', data, block_start)[0]
    if size1 != size2:
        raise ValueError('signing block size mismatch')

    p = block_start + 8
    pairs_end = cd_off - 24
    v2 = None
    while p < pairs_end:
        plen = struct.unpack_from('<Q', data, p)[0]
        p += 8
        pid = struct.unpack_from('<I', data, p)[0]
        p += 4
        val = data[p:p + plen - 4]
        p += plen - 4
        if pid == V2_ID:
            v2 = val
    if p != pairs_end or v2 is None:
        raise ValueError('v2 pair not found/malformed')

    def read_lp(buf, off):
        n = struct.unpack_from('<I', buf, off)[0]
        off += 4
        return buf[off:off + n], off + n

    signers_seq, off = read_lp(v2, 0)
    if off != len(v2):
        raise ValueError('extra data after signer sequence')

    signer, soff = read_lp(signers_seq, 0)
    if soff != len(signers_seq):
        raise ValueError('multiple/unparsed signers')

    signed_data, o = read_lp(signer, 0)
    sigs_seq, o = read_lp(signer, o)
    pub_der, o = read_lp(signer, o)
    if o != len(signer):
        raise ValueError('bad signer')

    digests_seq, o2 = read_lp(signed_data, 0)
    certs_seq, o2 = read_lp(signed_data, o2)
    attrs_seq, o2 = read_lp(signed_data, o2)
    if o2 != len(signed_data) or attrs_seq:
        raise ValueError('bad signed data')

    digest_rec, oo = read_lp(digests_seq, 0)
    if oo != len(digests_seq):
        raise ValueError('unparsed digest records')
    alg = struct.unpack_from('<I', digest_rec, 0)[0]
    stored_digest, q = read_lp(digest_rec, 4)
    if q != len(digest_rec):
        raise ValueError('bad digest record')

    cert_der, oo = read_lp(certs_seq, 0)
    if oo != len(certs_seq):
        raise ValueError('bad certificate sequence')

    sig_rec, oo = read_lp(sigs_seq, 0)
    if oo != len(sigs_seq):
        raise ValueError('bad signature sequence')
    salg = struct.unpack_from('<I', sig_rec, 0)[0]
    signature, q = read_lp(sig_rec, 4)
    if q != len(sig_rec) or salg != alg or alg != ALG_RSA_PKCS1_SHA256:
        raise ValueError('algorithm mismatch')

    cert = x509.load_der_x509_certificate(cert_der)
    cert_pub = cert.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    if cert_pub != pub_der:
        raise ValueError('public key mismatch')
    cert.public_key().verify(signature, signed_data, padding.PKCS1v15(), hashes.SHA256())

    section1 = data[:block_start]
    section3 = data[cd_off:eocd_pos]
    eocd_for_digest = bytearray(data[eocd_pos:])
    struct.pack_into('<I', eocd_for_digest, 16, block_start)
    actual_digest = chunked_digest([section1, section3, bytes(eocd_for_digest)])
    if actual_digest != stored_digest:
        raise ValueError('content digest mismatch')

    print('v2 self-verify OK')
    print('content_digest', actual_digest.hex())
    print('cert_sha256', hashlib.sha256(cert_der).hexdigest())


if __name__ == '__main__':
    if len(sys.argv) < 2:
        raise SystemExit('sign: apk_v2_sign.py sign in.apk out.apk [key.pem cert.pem]\nverify: apk_v2_sign.py verify app.apk')
    if sys.argv[1] == 'sign':
        _, _, src, dst, *rest = sys.argv
        sign_apk(src, dst, *(rest + [None, None])[:2])
    elif sys.argv[1] == 'verify':
        parse_and_verify(sys.argv[2])
    else:
        raise SystemExit('unknown command')
