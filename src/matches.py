"""A team's result/fixture lists -> match rows. Pure functions.

The embedded lists (`initialFeeds`) and the paged feeds
(`pr_{sport}_{country}_{team}_{page}_{tz}_en_1` for results, `pf_` for
fixtures) share the day-list format: a `ZA` competition header applies to
every `AA` match after it, and a team's history mixes competitions.

In these lists `BC`/`BD` is the **second-half** score for football and there
is no `BA`/`BB`, so the half-time score is regular time (`AT`/`AU`) minus
the second half.
"""

from __future__ import annotations

from typing import Any

from .feeds import Record, first, iso, records, to_int
from .urls import SITE_URL

STATUS_BY_CODE = {"1": "scheduled", "2": "live", "3": "finished"}

# Event stage (`AC`), Flashscore's own labels. An unmapped code leaves
# `statusDetail` null rather than guessing.
STAGE_BY_CODE = {
    "2": "Live",
    "3": "Finished",
    "4": "Postponed",
    "5": "Cancelled",
    "6": "Extra Time",
    "7": "Penalties",
    "8": "Retired",
    "9": "Walkover",
    "10": "After Extra Time",
    "11": "After Penalties",
    "12": "1st Half",
    "13": "2nd Half",
    "36": "Interrupted",
    "37": "Abandoned",
    "38": "Half Time",
    "42": "Awaiting updates",
    "43": "Delayed",
    "45": "To finish",
    "46": "Break Time",
    "54": "Awarded",
}
DECIDED_BY = {"10": "extra-time", "11": "penalties"}
WINNER_BY_CODE = {"0": "draw", "1": "home", "2": "away"}

PERIOD_KEYS = (("BA", "BB"), ("BC", "BD"), ("BE", "BF"), ("BG", "BH"), ("BI", "BJ"))


def team_feed(kind: str, *, sport_id: int, country_id: str, team_id: str, page: int) -> str:
    """`pr_` (results) / `pf_` (fixtures) page `n` of one team, UTC, English."""
    prefix = "pr" if kind == "results" else "pf"
    return f"{prefix}_{sport_id}_{country_id}_{team_id}_{page}_0_en_1"


def parse_team_matches(text: str, team_id: str) -> list[dict[str, Any]]:
    """A list -> match rows seen from `team_id` (venue, opponent, result)."""
    out: list[dict[str, Any]] = []
    header: Record = []
    for rec in records(text):
        key = rec[0][0]
        if key == "ZA":
            header = rec
        elif key == "AA":
            out.append(_match(rec, header, team_id))
    return out


def _match(rec: Record, header: Record, team_id: str) -> dict[str, Any]:
    event_id = first(rec, "AA")
    status = STATUS_BY_CODE.get(first(rec, "AB") or "")
    stage_code = first(rec, "AC") or ""
    finished = status == "finished"
    competition_path = first(header, "ZL") or ""
    sport = competition_path.strip("/").split("/")[0] if competition_path else ""

    home_id, away_id = first(rec, "PX"), first(rec, "PY")
    home, away = to_int(first(rec, "AG")), to_int(first(rec, "AH"))
    home_rt, away_rt = to_int(first(rec, "AT")), to_int(first(rec, "AU"))
    periods = _periods(rec, sport, home_rt, away_rt)
    winner = WINNER_BY_CODE.get(first(rec, "AS") or "") if finished else None

    venue = "home" if home_id == team_id else "away" if away_id == team_id else None
    result = None
    if winner and venue:
        result = "D" if winner == "draw" else "W" if winner == venue else "L"

    return {
        "recordType": "match",
        "eventId": event_id,
        "url": f"{SITE_URL}/match/{event_id}/",
        "competition": _competition(first(header, "ZA")),
        "competitionCountry": first(header, "ZY"),
        "competitionStage": _stage(first(header, "ZA")),
        "competitionUrl": SITE_URL + competition_path if competition_path else None,
        "round": first(rec, "ER"),
        "startTime": iso(first(rec, "AD")),
        "status": status,
        "statusDetail": STAGE_BY_CODE.get(stage_code),
        "venue": venue,
        "opponent": first(rec, "AF") if venue == "home" else first(rec, "AE") if venue == "away" else None,
        "opponentId": away_id if venue == "home" else home_id if venue == "away" else None,
        "result": result,
        "homeTeam": first(rec, "AE"),
        "homeTeamId": home_id,
        "awayTeam": first(rec, "AF"),
        "awayTeamId": away_id,
        "homeScore": home,
        "awayScore": away,
        "homeScoreRegularTime": home_rt,
        "awayScoreRegularTime": away_rt,
        "halfTimeScore": f"{periods[0]['home']}-{periods[0]['away']}" if periods and sport == "football" else None,
        "periodScores": periods or None,
        "decidedBy": (DECIDED_BY.get(stage_code) or "regular-time") if finished else None,
        "winner": winner,
    }


def _periods(rec: Record, sport: str, home_rt: int | None, away_rt: int | None) -> list[dict[str, int]]:
    values = [(to_int(first(rec, h)), to_int(first(rec, a))) for h, a in PERIOD_KEYS]
    if sport == "football" and values[0] == (None, None) and None not in values[1]:
        if home_rt is None or away_rt is None:
            return []
        second_home, second_away = values[1]
        values[0] = (home_rt - second_home, away_rt - second_away)
        if values[0][0] < 0 or values[0][1] < 0:
            return []
    out = []
    for h, a in values:
        if h is None or a is None:
            break
        out.append({"home": h, "away": a})
    return out


def _competition(za: str | None) -> str | None:
    """`EUROPE: Champions League - League phase` -> `Champions League`."""
    if not za:
        return None
    return za.split(": ", 1)[-1].split(" - ", 1)[0] or None


def _stage(za: str | None) -> str | None:
    """`EUROPE: Champions League - League phase` -> `League phase`; no suffix -> null."""
    if not za:
        return None
    name = za.split(": ", 1)[-1]
    return name.split(" - ", 1)[1] if " - " in name else None
