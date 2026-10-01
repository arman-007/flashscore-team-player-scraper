"""Flashscore team and player URLs -> references. Pure functions.

Every Flashscore edition (`flashscore.com`, `.co.uk`, `.com.au` ...) uses the
same `/team/{slug}/{id}/` and `/player/{slug}/{id}/` paths, and the id is the
same everywhere, so any of them is accepted and fetched from
`www.flashscore.com`. The slug is not decorative: a page with the right id
and a wrong slug is a 404.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SITE_URL = "https://www.flashscore.com"

_REF_RE = re.compile(r"(?:^|/)(team|player)/([a-z0-9][a-z0-9-]*)/([A-Za-z0-9]{8})(?=/|$|[?#])", re.I)


@dataclass(frozen=True)
class Ref:
    kind: str  # "team" | "player"
    slug: str
    id: str

    @property
    def path(self) -> str:
        return f"/{self.kind}/{self.slug}/{self.id}/"

    @property
    def url(self) -> str:
        return SITE_URL + self.path


def parse_ref(text: str) -> Ref | None:
    """`https://www.flashscore.co.uk/team/arsenal/hA1Zm19f/squad/` -> team `arsenal`/`hA1Zm19f`."""
    m = _REF_RE.search((text or "").strip())
    if not m:
        return None
    return Ref(kind=m.group(1).lower(), slug=m.group(2).lower(), id=m.group(3))


def ref_from_path(path: str | None) -> Ref | None:
    """A site-relative link found inside a page (`/team/brentford/xYe7DwID/`)."""
    return parse_ref(path) if path else None


def absolute(path: str | None) -> str | None:
    if not path:
        return None
    return path if path.startswith("http") else SITE_URL + path


def player_url_from_transfer(purl: str | None) -> str | None:
    """Team transfer rows link players as `/team/{slug}/{id}/`; the page lives under `/player/`."""
    ref = ref_from_path(purl)
    return Ref("player", ref.slug, ref.id).url if ref else None
