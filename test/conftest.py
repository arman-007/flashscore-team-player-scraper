from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

ARSENAL = "/team/arsenal/hA1Zm19f/"
LAKERS = "/team/los-angeles-lakers/ngegZ8bg/"
RAPPERSWIL = "/team/rapperswil-jona/dxdryEVs/"
ENGLAND = "/team/england/j9N9ZNFA/"
SAKA = "/player/saka-bukayo/08NLEo06/"
RAYA = "/player/raya-david/nkVV0IXb/"
LEBRON = "/player/james-lebron/nuIVxFJk/"
ARTETA = "/player/arteta-mikel/lAbHYaQM/"
NYFFELER = "/player/nyffeler-melvin/IaUsdlgt/"
TAA = "/player/alexander-arnold-trent/CEVJy6Bc/"
DJOKOVIC = "/player/djokovic-novak/AZg49Et9/"

# Captured 2026-09-30.
PAGES = {
    ARSENAL: "team_arsenal.html.gz",
    LAKERS: "team_lakers.html.gz",
    RAPPERSWIL: "team_rapperswil.html.gz",
    ENGLAND: "team_england.html.gz",
    SAKA: "player_saka.html.gz",
    RAYA: "player_raya.html.gz",
    LEBRON: "player_lebron.html.gz",
    ARTETA: "player_arteta.html.gz",
    NYFFELER: "player_nyffeler.html.gz",
    TAA: "player_taa.html.gz",
    DJOKOVIC: "player_djokovic.html.gz",
}


def read(name: str) -> str:
    path = FIXTURES / name
    if path.suffix == ".gz":
        return gzip.decompress(path.read_bytes()).decode("utf-8")
    return path.read_text(encoding="utf-8")


def read_json(name: str):
    return json.loads(read(name))


_cache: dict[str, str] = {}


def page(path: str) -> str:
    if path not in _cache:
        _cache[path] = read(PAGES[path])
    return _cache[path]


@pytest.fixture(scope="session")
def pages() -> dict[str, str]:
    return {path: page(path) for path in PAGES}
