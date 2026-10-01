"""Transfers from a team feed or a player page -> one row shape. Pure functions.

* **Team** -- `tetr_{teamId}_{filter}_{page}` (filter `1` = all, `2` =
  arrivals, `3` = departures), 15 rows a page, newest first, an empty body
  past the end. Tree format: each `RTT` node holds `DATE` (midnight Prague
  time as epoch seconds), `TD` (in/out), `TT` (type, `-` when unknown), `TJ`
  (fee, blank when undisclosed) and three children -- `TEA` with `TEAT=1`
  (from) and `TEAT=2` (to), and `PLA` (the player, linked as
  `/team/{slug}/{id}/`). Each page repeats the rows under `ALL`, `IN` and
  `OUT` groups; only `ALL` is read.
* **Player** -- `playerProfilePageEnvironment.transfersTable.transfers[]`
  with `DD.MM.YYYY` dates and the clubs' public URLs.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from .feeds import parse_tree, to_int
from .urls import absolute, player_url_from_transfer, ref_from_path

_FEE_RE = re.compile(r"^\s*([^\d\s.,]+)?\s*([\d.,]+)\s*(k|m|bn)?\s*$", re.I)
_MULTIPLIER = {None: 1, "k": 1_000, "m": 1_000_000, "bn": 1_000_000_000}
_CURRENCY = {"€": "EUR", "£": "GBP", "$": "USD"}
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def parse_team_transfers(text: str) -> list[dict[str, Any]]:
    tree = parse_tree(text)
    group = next(
        (c for c in tree["children"] if c["tag"] == "GR" and c["props"].get("TI") == "ALL"),
        None,
    )
    if group is None:
        return []
    rows = []
    for table in group["children"]:
        for node in table["children"]:
            if node["tag"] == "RTT":
                rows.append(_team_transfer(node))
    return rows


def _team_transfer(node: dict[str, Any]) -> dict[str, Any]:
    props = node["props"]
    clubs = {c["props"].get("TEAT"): c["props"] for c in node["children"] if c["tag"] == "TEA"}
    player = next((c["props"] for c in node["children"] if c["tag"] == "PLA"), {})
    source, dest = clubs.get("1", {}), clubs.get("2", {})
    return _row(
        date=_epoch_date(props.get("DATE")),
        direction=props.get("TD") or None,
        kind=props.get("TT"),
        fee=props.get("TJ"),
        player=player.get("VA"),
        player_id=player.get("PID"),
        player_url=player_url_from_transfer(player.get("PURL")),
        nationality=player.get("CRNA"),
        from_name=source.get("VA"),
        from_path=source.get("TURL"),
        to_name=dest.get("VA"),
        to_path=dest.get("TURL"),
    )


def parse_player_transfers(env: dict[str, Any]) -> list[dict[str, Any]]:
    table = env.get("transfersTable") or {}
    return [
        _row(
            date=dotted_date(t.get("valid_from")),
            direction=None,
            kind=t.get("binding_type"),
            fee=t.get("fee"),
            player=None,
            player_id=None,
            player_url=None,
            nationality=None,
            from_name=t.get("participant_name_from"),
            from_path=t.get("participant_id_from_url"),
            to_name=t.get("participant_name_to"),
            to_path=t.get("participant_id_to_url"),
        )
        for t in table.get("transfers") or []
    ]


def _row(
    *,
    date: str | None,
    direction: str | None,
    kind: str | None,
    fee: str | None,
    player: str | None,
    player_id: str | None,
    player_url: str | None,
    nationality: str | None,
    from_name: str | None,
    from_path: str | None,
    to_name: str | None,
    to_path: str | None,
) -> dict[str, Any]:
    from_ref, to_ref = ref_from_path(from_path), ref_from_path(to_path)
    amount, currency = parse_fee(fee)
    return {
        "recordType": "transfer",
        "date": date,
        "direction": direction,
        "transferType": kind if kind and kind != "-" else None,
        "fee": (fee or "").strip() or None,
        "feeAmount": amount,
        "feeCurrency": currency,
        "player": player,
        "playerId": player_id,
        "playerUrl": player_url,
        "nationality": nationality,
        "fromTeam": from_name or None,
        "fromTeamId": from_ref.id if from_ref else None,
        "fromTeamUrl": from_ref.url if from_ref else absolute(from_path),
        "toTeam": to_name or None,
        "toTeamId": to_ref.id if to_ref else None,
        "toTeamUrl": to_ref.url if to_ref else absolute(to_path),
    }


def parse_fee(fee: str | None) -> tuple[int | None, str | None]:
    """`€70.0m` -> (70000000, "EUR"); `€500k` -> (500000, "EUR"); blank -> (None, None)."""
    m = _FEE_RE.match(fee or "")
    if not m:
        return None, None
    symbol, number, unit = m.groups()
    try:
        value = float(number.replace(",", ""))
    except ValueError:
        return None, None
    amount = int(round(value * _MULTIPLIER[unit.lower() if unit else None]))
    return amount, _CURRENCY.get((symbol or "").strip(), (symbol or "").strip() or None)


def _epoch_date(value: Any) -> str | None:
    """Flashscore stamps a transfer at midnight Prague time (22:00 or 23:00 UTC the day before)."""
    seconds = to_int(value)
    if not seconds:
        return None
    return (_EPOCH + timedelta(seconds=seconds, hours=12)).strftime("%Y-%m-%d")


def dotted_date(value: Any) -> str | None:
    """`04.07.2024` -> `2024-07-04`; `12.09.26` -> `2026-09-12`."""
    text = str(value or "").strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None
