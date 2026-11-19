from pathlib import Path

import pytest
from helpers import FIXTURES

from suumoviz.cli import main


def test_offline_dry_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "crawl",
            "--dry-run",
            "--city-html",
            str(FIXTURES),
            "--date",
            "2026-11-07",
            "--data-dir",
            str(tmp_path / "data"),
            "--work-dir",
            str(tmp_path / "work"),
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "slot 5 of 7" in out
    assert "https://suumo.jp/" in out


def test_interval_cannot_go_below_five_seconds() -> None:
    with pytest.raises(SystemExit):
        main(["crawl", "--dry-run", "--interval", "2"])


def test_unknown_category_rejected() -> None:
    with pytest.raises(SystemExit):
        main(["crawl", "--dry-run", "--categories", "rent"])
