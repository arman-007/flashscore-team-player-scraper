"""A Flashscore team page -> profile, squad and embedded match lists. Pure functions.

One request to `/team/{slug}/{id}/` carries everything but the deep history:

* **Ids** -- inline `country_id = "198"; participant_id = "hA1Zm19f"`, and the
  sport as the breadcrumb's first link (`/football/`). The national-team page
  has no `window.environment`, so neither is read from there.
* **Header** -- `.heading__name`, the logo, and `.heading__info` rows:
  `Stadium: Emirates Stadium (London)`, `Capacity: 60 704`, or a ranking
  (`FIFA: 4.`) for national teams.
* **Squad** -- a hidden `.lineup` block with one table per competition
  (`id="league-SY30SsKF-table"` ...) plus `overall-all-table` (all
  competitions). Rows sit under position titles (Goalkeepers ... Coach); a
  basketball squad has no titles. Columns vary by sport and are read from
  each cell's `lineupTable__cell--{name}` class.
* **Matches** -- `cjs.initialFeeds['results'|'fixtures']`: the newest ~40
  results, every fixture, and `allEventsCount` (Arsenal: 5,077 results).

Individual-sport players (tennis) are served by the same template under
`/player/`; `individual` marks them.
"""

from __future__ import annotations

import html as html_lib
import re
from typing import Any

from .feeds import to_float, to_int
from .sports import SPORT_BY_ID, SPORTS
from .urls import SITE_URL, absolute, parse_ref

_PARTICIPANT_RE = re.compile(r'participant_id\s*=\s*"(\w+)"')
_COUNTRY_RE = re.compile(r'country_id\s*=\s*"(\d+)"')
_BREADCRUMB_RE = re.compile(r'<h2 class="breadcrumb">(.*?)</h2>', re.S)
_CRUMB_RE = re.compile(r'class="breadcrumb__(?:link|text)"(?: href="([^"]*)")?>([^<]+)<')
_NAME_RE = re.compile(r'<div class="heading__name">([^<]+)</div>')
_LOGO_RE = re.compile(r'<img class="heading__logo[^"]*" src="([^"]+)"')
_FEED_RE = re.compile(
    r"cjs\.initialFeeds\[['\"](results|fixtures)['\"]\]\s*=\s*\{\s*data:\s*`(.*?)`,\s*allEventsCount:\s*(\d+)",
    re.S,
)
_FILTER_RE = re.compile(r'<button\s+role="tab" id="([\w-]+)"[^>]*>\s*([^<]+?)\s*</button>')
_TABLE_START_RE = re.compile(r'<div id="([\w-]+)-table" class="squad-table')
_TITLE_RE = re.compile(r'<div class="lineupTable__title">([^<]+)</div>')
_CELL_RE = re.compile(r'<div class="(?:lineupTable__cell--gray )?lineupTable__cell lineupTable__cell--(\w+)">\s*([^<]*?)\s*</div>')
_PLAYER_RE = re.compile(r'<a class="lineupTable__cell--name" href="([^"]+)">\s*([^<]+?)\s*</a>')
_FLAG_RE = re.compile(r'lineupTable__cell--flag flag fl_(\d+)" title="([^"]*)"')
_ABSENCE_RE = re.compile(r'<svg class="lineupTable__cell--absence ([\w-]+)">\s*<title>([^<]*)</title>')
_TAG_RE = re.compile(r"<[^>]+>")

# Squad columns -> dataset fields. An unlisted column keeps its class name.
SQUAD_COLUMNS = {
    "matchesPlayed": "matchesPlayed",
    "minutesPlayed": "minutesPlayed",
    "goal": "goals",
    "goals": "goals",
    "assist": "assists",
    "assists": "assists",
    "yellowCard": "yellowCards",
    "redCard": "redCards",
    "points": "points",
    "savesPercentage": "savePercentage",
    "goalsAgainstAverage": "goalsAgainstAverage",
    "shutouts": "cleanSheets",
}
_SKIP_CELLS = {"jersey", "player", "age", "flag", "name", "nameAndAbsence", "absence"}
_FLOAT_COLUMNS = {"savePercentage", "goalsAgainstAverage"}


class TeamPageError(ValueError):
    """The page is not a Flashscore team page."""


def parse_team_page(html: str, path: str) -> dict[str, Any]:
    team_id = _first(_PARTICIPANT_RE, html)
    name = _first(_NAME_RE, html)
    if not team_id or not name:
        raise TeamPageError(f"{SITE_URL}{path} is not a Flashscore team page (no participant id or name).")

    crumbs = _breadcrumbs(html)
    feeds = {
        m.group(1): {"data": m.group(2), "allEventsCount": int(m.group(3))}
        for m in _FEED_RE.finditer(html)
    }
    sport_slug, sport_id = _sport(crumbs, html)

    ref = parse_ref(path)
    return {
        "name": html_lib.unescape(name.strip()),
        "teamId": team_id,
        "url": ref.url if ref else SITE_URL + path,
        "sport": sport_slug,
        "sportId": sport_id,
        "country": html_lib.unescape(crumbs[-1][1]) if len(crumbs) > 1 else None,
        "countryId": _first(_COUNTRY_RE, html),
        "logoUrl": _first(_LOGO_RE, html),
        **_info(html),
        "individual": bool(ref and ref.kind == "player"),
        "feeds": feeds,
        **_squad(html),
    }


def _first(pattern: re.Pattern[str], text: str) -> str | None:
    m = pattern.search(text)
    return m.group(1) if m else None


def _sport(crumbs: list[tuple[str | None, str]], html: str) -> tuple[str | None, int | None]:
    """The breadcrumb's first link is `/basketball/`, but football's is `/` -- so fall back to its label."""
    if crumbs:
        href, label = crumbs[0]
        for candidate in ((href or "").strip("/").split("/")[0], label.strip().lower().replace(" ", "-")):
            if candidate in SPORTS:
                return candidate, SPORTS[candidate]
    sa = re.search(r"SA÷(\d+)", html)
    sport_id = int(sa.group(1)) if sa else None
    return SPORT_BY_ID.get(sport_id) if sport_id else None, sport_id


def _breadcrumbs(html: str) -> list[tuple[str | None, str]]:
    m = _BREADCRUMB_RE.search(html)
    if not m:
        return []
    return [(href or None, text.strip()) for href, text in _CRUMB_RE.findall(m.group(1))]


def _info(html: str) -> dict[str, Any]:
    """`.heading__info` rows. The block has no reliable end tag, so it runs to the next `<script`."""
    out: dict[str, Any] = {"stadium": None, "stadiumCity": None, "capacity": None, "ranking": None}
    start = html.find('<div class="heading__info">')
    if start < 0:
        return out
    end = html.find("<script", start)
    block = html[start + len('<div class="heading__info">') : end if end > 0 else start + 3000]
    rank = re.search(r'<span class="participant-detail-rank">(.*?)</span>', block, re.S)
    if rank:
        text = " ".join(html_lib.unescape(_TAG_RE.sub("", rank.group(1))).split())
        out["ranking"] = text.rstrip(".") or None
        return out
    for row in re.split(r"<div[^>]*>", block):
        text = " ".join(html_lib.unescape(_TAG_RE.sub(" ", row)).split())
        label, sep, value = text.partition(":")
        if not sep:
            continue
        label, value = label.strip().lower(), value.strip()
        if label == "stadium":
            city = re.search(r"\(([^)]*)\)\s*$", value)
            out["stadium"] = (value[: city.start()].strip() if city else value) or None
            out["stadiumCity"] = city.group(1).strip() if city else None
        elif label == "capacity":
            out["capacity"] = to_int(re.sub(r"\D", "", value))
    return out


# ------------------------------------------------------------------ squad


def _squad(html: str) -> dict[str, Any]:
    """Every squad table: `{"competitions": [...], "squad": {tableKey: [rows]}}`."""
    names = {tab_id: html_lib.unescape(label) for tab_id, label in _FILTER_RE.findall(html)}
    starts = list(_TABLE_START_RE.finditer(html))
    tables: dict[str, list[dict[str, Any]]] = {}
    for i, m in enumerate(starts):
        key = m.group(1)
        end = starts[i + 1].start() if i + 1 < len(starts) else html.find('<div class="lineup__', m.end())
        block = html[m.end() : end if end > 0 else len(html)]
        tables.setdefault(key, _table_rows(block))
    competitions = [
        {"key": key, "name": names.get(key), "type": _competition_type(key)}
        for key in tables
    ]
    return {"competitions": competitions, "squad": tables}


def _competition_type(key: str) -> str:
    if key == "overall-all":
        return "all"
    return key.rsplit("-", 1)[0]


def _table_rows(block: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    marks = sorted(
        [(m.start(), "title", m) for m in _TITLE_RE.finditer(block)]
        + [(m.start(), "row", m) for m in re.finditer(r'<div class="lineupTable__row">', block)]
    )
    group: str | None = None
    for index, (pos, kind, m) in enumerate(marks):
        if kind == "title":
            group = html_lib.unescape(m.group(1).strip())
            continue
        end = marks[index + 1][0] if index + 1 < len(marks) else len(block)
        row = _row(block[pos:end], group)
        if row:
            rows.append(row)
    return rows


def _row(chunk: str, group: str | None) -> dict[str, Any] | None:
    player = _PLAYER_RE.search(chunk)
    if not player:
        return None
    ref = parse_ref(player.group(1))
    cells = {name: html_lib.unescape(value) for name, value in _CELL_RE.findall(chunk)}
    flag = _FLAG_RE.search(chunk)
    absence = _ABSENCE_RE.search(chunk)
    row: dict[str, Any] = {
        "positionGroup": group,
        "role": "coach" if (group or "").lower() == "coach" else "player",
        "player": html_lib.unescape(player.group(2)),
        "playerId": ref.id if ref else None,
        "playerUrl": ref.url if ref else absolute(player.group(1)),
        "jerseyNumber": to_int(cells.get("jersey")),
        "nationality": html_lib.unescape(flag.group(2)) if flag and flag.group(2) else None,
        "age": to_int(cells.get("age")),
        "absence": html_lib.unescape(absence.group(2)).strip() or absence.group(1) if absence else None,
    }
    for cell, value in cells.items():
        if cell in _SKIP_CELLS:
            continue
        field = SQUAD_COLUMNS.get(cell, cell)
        row[field] = to_float(value) if field in _FLOAT_COLUMNS else _number(value)
    return row


def _number(value: str | None) -> int | float | None:
    number = to_int(value)
    return number if number is not None else to_float(value)
