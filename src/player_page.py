"""A Flashscore player page -> profile, career, last matches, transfers, injuries. Pure functions.

One request to `/player/{slug}/{id}/` carries everything:

* **Header** (server HTML, `.playerHeader__wrapper`) -- name, photo, position
  and club (`Forward (Arsenal)`), then `playerInfoItem` label/value pairs:
  `Age: 25 (05.09.2001)`, `Market value: €113.9m`, `Contract expires:
  30.06.2030`, `Height: 206 cm`. Which labels appear depends on the sport and
  the player. The breadcrumb's second item is the player's country.
* **`window.playerProfilePageEnvironment`** -- a JSON object followed by more
  JavaScript on the same line, so it is decoded from its first brace:
  `lastMatchesData.lastMatches` (10 matches, rating and a small stat block
  keyed by stat id), `careerTables` (league, domestic cups, international
  cups, national team -- one row per season and team), `transfersTable`
  and `injuryHistoryTable`.

Career ids (`team_id: 226`) are numeric internal ids; only the `url` fields
carry the public 8-character ids, so those are what rows expose.

Tennis players use the team-page template instead, with no environment
object; `PlayerPageError` marks them.
"""

from __future__ import annotations

import html as html_lib
import json
import re
from typing import Any

from .feeds import to_float, to_int
from .sports import SPORT_BY_ID
from .transfers import dotted_date, parse_fee, parse_player_transfers
from .urls import SITE_URL, absolute, parse_ref, ref_from_path

ENV_MARKER = "window.playerProfilePageEnvironment"

_TAG_RE = re.compile(r"<[^>]+>")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_SVG_RE = re.compile(r"<svg.*?</svg>", re.S)
_NAME_RE = re.compile(r'role="heading">([^<]+)<')
_PHOTO_RE = re.compile(r'<img[^>]*src="([^"]+)"')
_TEAM_LINK_RE = re.compile(r'<a href="([^"]+)" title="([^"]*)" class="playerInfoItem__link"')
_INFO_ITEM_RE = re.compile(r'<div class="playerInfoItem">(.*?)</div>', re.S)
_SPAN_RE = re.compile(r"<span[^>]*>(.*?)</span>", re.S)
_BREADCRUMB_RE = re.compile(r'itemProp="name">([^<]+)</span>')

CAREER_TYPES = {
    "league": "league",
    "nacional-cup": "domestic-cup",
    "international-cups": "international-cup",
    "national-team": "national-team",
}

# Career-table keys -> dataset fields. Every other non-metadata key is kept
# under its camelCased name.
CAREER_STATS = {
    "matches_played": "matchesPlayed",
    "goals": "goals",
    "assists": "assists",
    "yellow_card": "yellowCards",
    "red_card": "redCards",
    "avg_fs_rating": "rating",
    "goalkeeper_saves_percentage": "savePercentage",
    "shutouts": "cleanSheets",
    "minutes_played": "minutesPlayed",
    "points": "points",
    "rebounds": "rebounds",
    "steals": "steals",
    "blocks": "blocks",
    "penalty_minutes": "penaltyMinutes",
    "goals_against_average": "goalsAgainstAverage",
}
TOTAL_COUNTS = {
    "matchesPlayed", "goals", "assists", "yellowCards", "redCards", "cleanSheets", "points", "penaltyMinutes",
}
_CAREER_META = {
    "even", "flag_id", "flag_name", "hide_arrow", "key", "logo", "participant_id", "raw_logo",
    "season_id", "season_name", "team_id", "team_name", "team_three_char_name", "tournament_id",
    "tournament_name", "tournament_stage_id", "tournament_url", "url", "title", "rowspan",
}

# Last-match stat ids. A zero is sent as type `grey` with no name, so the id
# is the only key; the order per sport is `config.last_matches_stats_order`
# and matches the column headers (football: MIN, goals, assists, saves,
# shots on target faced, yellow, red).
MATCH_STATS = {
    "595": "minutesPlayed",
    "596": "goals",
    "541": "assists",
    "649": "saves",
    "965": "shotsOnTargetFaced",
    "599": "yellowCards",
    "600": "redCards",
    "169": "points",
    "713": "rebounds",
    "696": "steals",
    "697": "turnovers",
    "715": "savePercentage",
    "777": "penaltyMinutes",
    "781": "timeOnIce",
}


class PlayerPageError(ValueError):
    """The page has no player profile data (an individual-sport player, or a changed template)."""


def extract_env(html: str) -> dict[str, Any] | None:
    i = html.find(ENV_MARKER)
    if i < 0:
        return None
    start = html.find("{", i)
    try:
        env, _ = json.JSONDecoder().raw_decode(html, start)
    except ValueError:
        return None
    return env if isinstance(env, dict) else None


def parse_player_page(html: str, path: str) -> dict[str, Any]:
    env = extract_env(html)
    if env is None:
        raise PlayerPageError(f"{SITE_URL}{path} has no player profile data.")
    ref = parse_ref(path)
    header = parse_header(html)
    injuries = parse_injuries(env)
    current = next((i for i in injuries if i["isCurrent"]), None)
    career = parse_career(env)
    profile = {
        "recordType": "player",
        "player": header["name"],
        "playerId": env.get("participantId") or (ref.id if ref else None),
        "url": ref.url if ref else SITE_URL + path,
        "sport": SPORT_BY_ID.get(to_int(env.get("sportId")) or 0),
        "role": "coach" if (header["position"] or "").lower() == "coach" else "player",
        "position": header["position"],
        "team": header["team"],
        "teamId": header["teamId"],
        "teamUrl": header["teamUrl"],
        "nationality": header["nationality"],
        "age": header["age"],
        "dateOfBirth": header["dateOfBirth"],
        "marketValue": header["marketValue"],
        "marketValueAmount": header["marketValueAmount"],
        "marketValueCurrency": header["marketValueCurrency"],
        "contractExpires": header["contractExpires"],
        "heightCm": header["heightCm"],
        "photoUrl": header["photoUrl"],
        "currentInjury": current["injury"] if current else None,
        "injuredUntil": current["until"] if current else None,
        "careerTotals": career_totals(env) or None,
        "otherInfo": header["otherInfo"] or None,
    }
    return {
        "profile": profile,
        "career": career,
        "lastMatches": parse_last_matches(env),
        "transfers": parse_player_transfers(env),
        "injuries": injuries,
    }


# ------------------------------------------------------------------ header


def parse_header(html: str) -> dict[str, Any]:
    out: dict[str, Any] = {
        "name": None, "photoUrl": None, "position": None, "team": None, "teamId": None, "teamUrl": None,
        "nationality": None, "age": None, "dateOfBirth": None, "marketValue": None,
        "marketValueAmount": None, "marketValueCurrency": None, "contractExpires": None,
        "heightCm": None, "otherInfo": {},
    }
    start = html.find("playerHeader__wrapper")
    if start < 0:
        return out
    end = html.find('id="player-profile"', start)
    seg = _COMMENT_RE.sub("", _SVG_RE.sub("", html[start : end if end > 0 else start + 8000]))

    name = _NAME_RE.search(seg)
    out["name"] = _text(name.group(1)) if name else None
    photo = _PHOTO_RE.search(seg)
    out["photoUrl"] = photo.group(1) if photo else None

    team = _TEAM_LINK_RE.search(seg)
    if team:
        team_ref = ref_from_path(team.group(1))
        out["team"] = _text(team.group(2)) or None
        out["teamId"] = team_ref.id if team_ref else None
        out["teamUrl"] = team_ref.url if team_ref else absolute(team.group(1))

    first_item = seg.find('class="playerInfoItem"')
    heading_end = seg.find("</h2>")
    lead = seg[heading_end if heading_end > 0 else 0 : first_item if first_item > 0 else len(seg)]
    for span in _SPAN_RE.findall(lead):
        text = _text(span)
        if text and not text.startswith("("):
            out["position"] = text
            break

    for item in _INFO_ITEM_RE.findall(seg):
        spans = [_text(s) for s in _SPAN_RE.findall(item)]
        if not spans:
            continue
        label = spans[0].rstrip(": ").strip()
        value = " ".join(s for s in spans[1:] if s).strip()
        _apply_info(out, label, value)

    crumbs = [_text(c) for c in _BREADCRUMB_RE.findall(html[: start])]
    out["nationality"] = crumbs[1] if len(crumbs) > 1 else None
    return out


def _apply_info(out: dict[str, Any], label: str, value: str) -> None:
    key = label.lower()
    if key == "age":
        out["age"] = to_int(value.split("(")[0])
        dob = re.search(r"\(([\d.]+)\)", value)
        out["dateOfBirth"] = dotted_date(dob.group(1)) if dob else None
    elif key == "market value":
        out["marketValue"] = value or None
        out["marketValueAmount"], out["marketValueCurrency"] = parse_fee(value)
    elif key == "contract expires":
        out["contractExpires"] = dotted_date(value)
    elif key == "height":
        out["heightCm"] = to_int(re.sub(r"\D", "", value))
    elif label and value:
        out["otherInfo"][label] = value


def _text(fragment: str) -> str:
    return " ".join(html_lib.unescape(_TAG_RE.sub("", fragment or "")).split())


# ------------------------------------------------------------------ career


def parse_career(env: dict[str, Any]) -> list[dict[str, Any]]:
    per_game = _per_game(env)
    rows = []
    for table in env.get("careerTables") or []:
        kind = CAREER_TYPES.get(table.get("table_id"), table.get("table_id"))
        for season in table.get("seasons") or []:
            team_ref = ref_from_path(season.get("url"))
            rows.append({
                "recordType": "careerSeason",
                "competitionType": kind,
                "season": season.get("season_name"),
                "team": season.get("team_name"),
                "teamId": team_ref.id if team_ref else None,
                "teamUrl": team_ref.url if team_ref else absolute(season.get("url")),
                "competition": season.get("tournament_name"),
                "competitionUrl": absolute(season.get("tournament_url")),
                "competitionCountry": season.get("flag_name"),
                "statsPerGame": per_game,
                **_stats(season),
            })
    return rows


def career_totals(env: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """`{"league": {"matchesPlayed": 255, "goals": 73, ...}, ...}` from each table's `total`.

    Flashscore's total row adds up every column, including averages (save
    percentage, goals-against average, rating) and, for basketball, every
    per-game stat. Only counts survive that, so only counts are kept.
    """
    keep = {"matchesPlayed"} if _per_game(env) else TOTAL_COUNTS
    totals = {}
    for table in env.get("careerTables") or []:
        total = table.get("total")
        if isinstance(total, dict):
            stats = {k: v for k, v in _stats(total).items() if k in keep}
            totals[CAREER_TYPES.get(table.get("table_id"), table.get("table_id"))] = stats
    return totals


def _per_game(env: dict[str, Any]) -> bool:
    """Basketball career rows are per-game averages (LeBron 2025/26: 21.3 points)."""
    return SPORT_BY_ID.get(to_int(env.get("sportId")) or 0) == "basketball"


def _stats(source: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in source.items():
        if key in _CAREER_META or isinstance(value, (dict, list, bool)):
            continue
        out[CAREER_STATS.get(key, _camel(key))] = _number(value)
    return out


def _camel(key: str) -> str:
    head, *rest = key.split("_")
    return head + "".join(part.title() for part in rest)


def _number(value: Any) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(value, 2)
    text = str(value).strip()
    if text in ("", "-"):
        return None
    number = to_int(text)
    if number is not None:
        return number
    number = to_float(text)
    return round(number, 2) if number is not None else None


# ------------------------------------------------------------------ last matches


def parse_last_matches(env: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for m in (env.get("lastMatchesData") or {}).get("lastMatches") or []:
        event_id = m.get("eventEncodedId")
        home_id, away_id = m.get("homeParticipantEncodedId"), m.get("awayParticipantEncodedId")
        row = {
            "recordType": "playerMatch",
            "eventId": event_id,
            "url": f"{SITE_URL}/match/{event_id}/" if event_id else None,
            "date": dotted_date(m.get("eventStartTime")),
            "competition": m.get("tournamentTitle"),
            "competitionUrl": absolute(m.get("tournamentUrl")),
            "season": (m.get("tournamentSeason") or "").replace("-", "/") or None,
            "homeTeam": m.get("homeParticipantName"),
            "homeTeamId": home_id,
            "awayTeam": m.get("awayParticipantName"),
            "awayTeamId": away_id,
            "homeScore": to_int(m.get("homeScore")),
            "awayScore": to_int(m.get("awayScore")),
            "result": m.get("winLoseShort") or None,
            "rating": to_float(m.get("rating")),
            "ratingRank": to_int(m.get("ratingRank")),
            "absence": m.get("absenceCategory") or None,
            "absenceReason": m.get("absenceTypeText") or None,
        }
        row.update(_match_stats(m.get("stats")))
        rows.append(row)
    return rows


def _match_stats(stats: Any) -> dict[str, Any]:
    if not isinstance(stats, dict):
        return {}
    out: dict[str, Any] = {}
    for stat_id, entry in stats.items():
        if not isinstance(entry, dict):
            continue
        field = MATCH_STATS.get(str(stat_id))
        if field is None:
            kind = entry.get("type")
            if not kind or kind == "grey":
                continue
            field = _camel(kind.replace("-", "_"))
        out[field] = _stat_value(entry.get("value"))
    return out


def _stat_value(value: Any) -> int | float | None:
    """`90'` -> 90, `40:26` -> 40.43 (minutes), `82.72` -> 82.72."""
    text = str(value or "").strip().rstrip("'")
    if ":" in text:
        minutes, _, seconds = text.partition(":")
        m, s = to_int(minutes), to_int(seconds)
        return round(m + s / 60, 2) if m is not None and s is not None else None
    return _number(text)


# ------------------------------------------------------------------ injuries


def parse_injuries(env: dict[str, Any]) -> list[dict[str, Any]]:
    table = env.get("injuryHistoryTable") or {}
    return [
        {
            "recordType": "injury",
            "injury": i.get("injury_name") or None,
            "from": dotted_date(i.get("injury_from")),
            "until": dotted_date(i.get("injury_until")),
            "isCurrent": str(i.get("is_valid")) == "1",
        }
        for i in table.get("injury_history") or []
    ]
