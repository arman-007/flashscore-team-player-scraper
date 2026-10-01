"""Search API results -> the team or player a query means. Pure functions.

`s.livesport.services/api/v2/search/` returns entities best match first,
each with `type.name`: `Team` (clubs and national teams), `PlayerInTeam`
(team-sport players and coaches), `Player` (individual-sport players, e.g.
tennis) or `Tournament`. `url` is the slug and `id` the public id, which
together make the page path.
"""

from __future__ import annotations

from typing import Any

from .sports import SPORTS
from .urls import Ref

TEAM_TYPES = {"Team"}
PLAYER_TYPES = {"PlayerInTeam"}
INDIVIDUAL_TYPES = {"Player"}


def pick_hit(results: list[dict[str, Any]], sport: str | None = None) -> tuple[Ref | None, dict[str, Any] | None]:
    """The first team or team-sport player, optionally of one sport."""
    sport_id = SPORTS.get(sport) if sport else None
    for entry in results:
        kind = (entry.get("type") or {}).get("name")
        if kind not in TEAM_TYPES | PLAYER_TYPES:
            continue
        if sport_id is not None and (entry.get("sport") or {}).get("id") != sport_id:
            continue
        slug, entity_id = entry.get("url"), entry.get("id")
        if not slug or not entity_id:
            continue
        return Ref("team" if kind in TEAM_TYPES else "player", str(slug).lower(), str(entity_id)), entry
    return None, None


def has_individual_hit(results: list[dict[str, Any]]) -> bool:
    return any((e.get("type") or {}).get("name") in INDIVIDUAL_TYPES for e in results)
