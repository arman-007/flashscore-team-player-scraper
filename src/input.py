"""Actor input parsing and validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .sports import ALIASES, SPORTS
from .urls import Ref, parse_ref

TEAM_SECTIONS = ("profile", "squad", "results", "fixtures", "transfers")
PLAYER_SECTIONS = ("profile", "career", "lastMatches", "transfers", "injuries")

DEFAULT_TEAM_SECTIONS = TEAM_SECTIONS
DEFAULT_PLAYER_SECTIONS = PLAYER_SECTIONS
DEFAULT_MAX_RESULTS = 50
DEFAULT_MAX_TRANSFERS = 50
DEFAULT_MAX_ITEMS = 10000

MAX_URLS = 500
MAX_QUERIES = 100


@dataclass(frozen=True)
class ActorInput:
    teams: list[Ref]
    players: list[Ref]
    search_queries: list[str]
    search_sport: str | None
    team_sections: list[str]
    player_sections: list[str]
    squad_per_competition: bool
    scrape_squad_players: bool
    max_results: int | None
    max_transfers: int | None
    max_items: int
    proxy_config_input: dict[str, Any] | None


def parse_input(raw: dict[str, Any] | None) -> ActorInput:
    raw = raw or {}

    teams: list[Ref] = []
    players: list[Ref] = []
    for name in ("teamUrls", "playerUrls"):
        for value in _as_list(raw.get(name), name, MAX_URLS):
            text = _url_value(value)
            if not text:
                continue
            ref = parse_ref(text)
            if ref is None:
                raise ValueError(
                    f"{text!r} in `{name}` is not a Flashscore team or player URL. Use one like "
                    "https://www.flashscore.com/team/arsenal/hA1Zm19f/ or "
                    "https://www.flashscore.com/player/saka-bukayo/08NLEo06/, or put the name in "
                    "`searchQueries`."
                )
            # A player URL pasted into teamUrls (or the reverse) is still unambiguous.
            bucket = teams if ref.kind == "team" else players
            if ref not in bucket:
                bucket.append(ref)

    queries: list[str] = []
    for value in _as_list(raw.get("searchQueries"), "searchQueries", MAX_QUERIES):
        text = " ".join(str(value or "").split())
        if len(text) == 1:
            raise ValueError(f"Search query {text!r} is too short; use at least two characters.")
        if text and text.lower() not in (q.lower() for q in queries):
            queries.append(text)

    if not teams and not players and not queries:
        raise ValueError(
            "Add at least one team or player: a URL in `teamUrls` / `playerUrls` (e.g. "
            "https://www.flashscore.com/team/arsenal/hA1Zm19f/) or a name in `searchQueries` "
            "(e.g. \"Arsenal\" or \"Bukayo Saka\")."
        )

    return ActorInput(
        teams=teams,
        players=players,
        search_queries=queries,
        search_sport=_sport(raw.get("searchSport")),
        team_sections=_sections(raw.get("teamSections"), TEAM_SECTIONS, DEFAULT_TEAM_SECTIONS, "teamSections"),
        player_sections=_sections(raw.get("playerSections"), PLAYER_SECTIONS, DEFAULT_PLAYER_SECTIONS, "playerSections"),
        squad_per_competition=bool(raw.get("squadPerCompetition")),
        scrape_squad_players=bool(raw.get("scrapeSquadPlayers")),
        max_results=_limit(raw.get("maxResultsPerTeam"), "maxResultsPerTeam", DEFAULT_MAX_RESULTS),
        max_transfers=_limit(raw.get("maxTransfersPerTeam"), "maxTransfersPerTeam", DEFAULT_MAX_TRANSFERS),
        max_items=_positive(raw.get("maxItems"), "maxItems", DEFAULT_MAX_ITEMS),
        proxy_config_input=raw.get("proxyConfiguration"),
    )


def _sport(value: Any) -> str | None:
    text = str(value or "").strip().lower().replace(" ", "-")
    if not text or text == "any":
        return None
    text = ALIASES.get(text, text)
    if text not in SPORTS:
        raise ValueError(f"`searchSport` {value!r} is not a Flashscore sport. Use e.g. football, basketball or hockey.")
    return text


def _sections(raw: Any, options: tuple[str, ...], default: tuple[str, ...], name: str) -> list[str]:
    if raw in (None, []):
        return list(default)
    by_lower = {o.lower(): o for o in options}
    out: list[str] = []
    for value in _as_list(raw, name, len(options) * 2):
        text = str(value or "").strip().lower()
        if text not in by_lower:
            raise ValueError(f"{value!r} is not valid in `{name}`. Use any of: {', '.join(options)}.")
        if by_lower[text] not in out:
            out.append(by_lower[text])
    return out


def _limit(value: Any, name: str, default: int) -> int | None:
    """A per-team cap: blank -> default, 0 -> no cap."""
    if value in (None, ""):
        return default
    number = _int(value, name)
    if number < 0:
        raise ValueError(f"`{name}` must be 0 (no limit) or more; got {number}.")
    return number or None


def _positive(value: Any, name: str, default: int) -> int:
    if value in (None, ""):
        return default
    number = _int(value, name)
    if number < 1:
        raise ValueError(f"`{name}` must be at least 1; got {number}.")
    return number


def _int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"`{name}` must be a whole number; got {value!r}.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"`{name}` must be a whole number; got {value!r}.") from exc


def _url_value(value: Any) -> str:
    """Apify's `requestListSources` editor sends `{"url": ...}` objects."""
    if isinstance(value, dict):
        value = value.get("url")
    return str(value or "").strip()


def _as_list(raw: Any, name: str, limit: int) -> list:
    if raw in (None, ""):
        return []
    values = raw if isinstance(raw, list) else [raw]
    if len(values) > limit:
        raise ValueError(f"`{name}` accepts at most {limit} values; got {len(values)}.")
    return values
