import hashlib
from pathlib import Path

import pytest
from helpers import FIXTURES

from suumoviz import codec
from suumoviz.cli import main
from suumoviz.store import read_rows, write_rows

SAMPLES = [
    b"",
    b"\n",
    b"listing_id,name\n100,\xe4\xb8\x96\xe7\x94\xb0\xe8\xb0\xb7\n",  # 世田谷
    b"no trailing newline",
    b"crlf line\r\nnext\r\n",
    bytes(range(256)),
    b"x" * 1000 + b"\n\n\n",
]


@pytest.mark.parametrize("data", SAMPLES)
def test_round_trip(data: bytes) -> None:
    encoded = codec.encode(data)
    assert codec.is_encoded(encoded)
    assert codec.decode(encoded) == data


def test_key_is_documented_derivation() -> None:
    assert hashlib.sha256(b"suumoviz/obf/1").digest() == codec.KEY


def test_text_is_not_readable() -> None:
    plain = "13112,世田谷区,成城8,89500000\n".encode()
    encoded = codec.encode(plain)
    assert encoded.startswith(codec.MAGIC + b"\n")
    for word in (b"13112", "世田谷".encode(), b"89500000"):
        assert word not in encoded


def test_unchanged_lines_stay_identical() -> None:
    before = codec.encode(b"header\nrow 1\nrow 2\nrow 3\n").split(b"\n")
    after = codec.encode(b"header\nrow 1\nrow two\nrow 3\n").split(b"\n")
    assert [i for i, (a, b) in enumerate(zip(before, after, strict=True)) if a != b] == [3]


def test_crlf_checkout_still_decodes() -> None:
    encoded = codec.encode(b"a\nb\n").replace(b"\n", b"\r\n")
    assert codec.decode(encoded) == b"a\nb\n"


def test_decode_rejects_plain_and_corrupt_data() -> None:
    with pytest.raises(codec.DecodeError, match="not a"):
        codec.decode(b"date,count\n")
    with pytest.raises(codec.DecodeError, match="corrupt"):
        codec.decode(codec.MAGIC + b"\nnot base64!\n")


def test_read_passes_plain_files_through(tmp_path: Path) -> None:
    plain = tmp_path / "plain.csv"
    plain.write_bytes(b"a,b\n1,2\n")
    assert codec.read_bytes(plain) == b"a,b\n1,2\n"
    assert codec.encode_file(plain) is True
    assert codec.is_encoded(plain.read_bytes())
    assert codec.encode_file(plain) is False  # already encoded: unchanged
    assert codec.read_bytes(plain) == b"a,b\n1,2\n"


def test_tables_are_written_encoded_and_plain_tables_still_read(tmp_path: Path) -> None:
    table = tmp_path / "t.csv"
    write_rows(table, ["date", "name"], [{"date": "2026-11-07", "name": "成城"}])
    assert codec.is_encoded(table.read_bytes())
    assert read_rows(table) == [{"date": "2026-11-07", "name": "成城"}]

    legacy = tmp_path / "legacy.csv"
    legacy.write_text("date,name\n2026-11-07,成城\n", encoding="utf-8")
    assert read_rows(legacy) == [{"date": "2026-11-07", "name": "成城"}]


def test_fixtures_are_committed_encoded() -> None:
    files = [p for p in FIXTURES.iterdir() if p.is_file()]
    assert files
    for path in files:
        assert codec.is_encoded(path.read_bytes()), f"{path.name}: run `suumoviz encode` on it"


def test_cli_encode_and_decode(tmp_path: Path, capsysbinary: pytest.CaptureFixture[bytes]) -> None:
    data = tmp_path / "data"
    (data / "listings").mkdir(parents=True)
    (data / "listings" / "used_condo.csv").write_bytes(b"id\n1\n")
    (data / "state.json").write_text("{}", encoding="utf-8")  # not a table: left alone
    assert main(["encode", str(data)]) == 0
    assert codec.is_encoded((data / "listings" / "used_condo.csv").read_bytes())
    assert (data / "state.json").read_text(encoding="utf-8") == "{}"
    capsysbinary.readouterr()

    assert main(["decode", str(data / "listings" / "used_condo.csv")]) == 0
    assert capsysbinary.readouterr().out == b"id\n1\n"
    assert main(["decode", str(tmp_path / "missing.csv")]) == 1
    assert main(["encode", str(tmp_path / "missing.csv")]) == 1
