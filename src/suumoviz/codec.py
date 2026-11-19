"""Light obfuscation for crawled data kept in the public repository.

This is **not encryption**: the key is in this file and in the web bundle. It only keeps
the crawled data from being directly readable (GitHub's file view, code search, search
engines, a quick ``grep``). Anyone can decode a file with ``suumoviz decode FILE``.

Format (``#suumoviz-obf/1``)::

    #suumoviz-obf/1
    <base64 of line 1 XOR KEY>
    <base64 of line 2 XOR KEY>
    ...

Every line of the original is encoded on its own, with the key restarting at the start
of the line, so an unchanged CSV row stays byte-identical and the daily git diff of the
``data`` branch stays as small as with plain CSV. Encoding is lossless for any bytes.

Readers detect the header and accept plain files as well, so data written before the
encoding existed can still be read (and is encoded the next time it is written).
"""

from __future__ import annotations

import base64
import binascii
import os
from pathlib import Path

MAGIC = b"#suumoviz-obf/1"
# sha256(b"suumoviz/obf/1"); the web decoder (web/src/codec.ts) uses the same bytes.
KEY = bytes.fromhex("63bc3e0e7deebf9dd10486861648bc76c358fc9f09facb0664109292fe499ace")


class DecodeError(ValueError):
    pass


def _xor(data: bytes) -> bytes:
    if not data:
        return b""
    stream = (KEY * (len(data) // len(KEY) + 1))[: len(data)]
    value = int.from_bytes(data, "big") ^ int.from_bytes(stream, "big")
    return value.to_bytes(len(data), "big")


def is_encoded(data: bytes) -> bool:
    if not data.startswith(MAGIC):
        return False
    rest = data[len(MAGIC) : len(MAGIC) + 2]
    return rest == b"" or rest[:1] == b"\n" or rest == b"\r\n"


def encode(data: bytes) -> bytes:
    lines = data.split(b"\n")
    return b"\n".join([MAGIC, *(base64.b64encode(_xor(line)) for line in lines)])


def decode(data: bytes) -> bytes:
    if not is_encoded(data):
        raise DecodeError(f"not a {MAGIC.decode()} file")
    _, _, body = data.partition(b"\n")
    try:
        # a CRLF checkout adds "\r" outside the base64; the original's own "\r" is inside
        return b"\n".join(
            _xor(base64.b64decode(line.rstrip(b"\r"), validate=True)) for line in body.split(b"\n")
        )
    except binascii.Error as exc:
        raise DecodeError(f"corrupt {MAGIC.decode()} data: {exc}") from exc


def read_bytes(path: Path) -> bytes:
    """File content, decoded when the file is encoded (plain files pass through)."""
    data = path.read_bytes()
    return decode(data) if is_encoded(data) else data


def read_text(path: Path) -> str:
    return read_bytes(path).decode("utf-8")


def write_bytes(path: Path, data: bytes) -> None:
    """Encode ``data`` and write it atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(encode(data))
    os.replace(tmp, path)


def write_text(path: Path, text: str) -> None:
    write_bytes(path, text.encode("utf-8"))


def encode_file(path: Path) -> bool:
    """Encode a file in place; False when it is already encoded."""
    data = path.read_bytes()
    if is_encoded(data):
        return False
    write_bytes(path, data)
    return True
