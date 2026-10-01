"""Orchestration: resolve searches, then each team (profile, squad, matches,
transfers), then each player (profile, career, last matches, transfers, injuries)."""

from __future__ import annotations

import asyncio
import traceback
from typing import Any

from apify import Actor

from . import billing as bill
from .billing import Billing
from .feeds import is_empty
from .flashscore_client import FlashscoreClient, FlashscoreError, FlashscoreNotFoundError
from .input import ActorInput, parse_input
from .matches import parse_team_matches, team_feed
from .player_page import ENV_MARKER, PlayerPageError, parse_player_page
from .proxy_tiers import SessionRotator, TieredProxyFallback
from .search import has_individual_hit, pick_hit
from .team_page import TeamPageError, parse_team_page
from .transfers import parse_team_transfers
from .urls import Ref, parse_ref

# Player pages fetched at once. Each is one ~1 MB HTML request.
PLAYER_CONCURRENCY = 4
# Safety stops for paging. Arsenal's 5,077 results are ~127 `pr_` pages of
# 40; its transfers reach 2010 by `tetr_` page 80 (15 a page).
MAX_MATCH_PAGES = 200
MAX_TRANSFER_PAGES = 200


async def main() -> None:
    async with Actor:
        try:
            await _run()
        except Exception as exc:  # noqa: BLE001 - surface it, don't exit opaquely
            Actor.log.exception("Unhandled error")
            await Actor.fail(
                status_message=f"Unhandled error: {exc!r}\n{traceback.format_exc()[-1500:]}"
            )


async def _run() -> None:
    raw_input = await Actor.get_input() or {}
    try:
        actor_input = parse_input(raw_input)
    except ValueError as exc:
        await _report_bad_input(exc)
        return

    proxy_url, proxy_fallback = await _build_proxy_strategy(actor_input)
    state = RunState(billing=await Billing.create(), actor_input=actor_input)

    async with FlashscoreClient(proxy=proxy_url, proxy_fallback=proxy_fallback) as client:
        await run_all(client, state)
        state.escalations = client.escalations_used

    await _report(state)


class RunState:
    def __init__(self, *, billing: Billing, actor_input: ActorInput) -> None:
        self.billing = billing
        self.actor_input = actor_input
        self.teams: list[Ref] = list(actor_input.teams)
        self.players: list[Ref] = list(actor_input.players)
        self.pushed = 0
        self.teams_done = 0
        self.players_done = 0
        self.not_found = 0
        self.errors: list[str] = []
        self.failed: list[str] = []
        self.notes: list[str] = []
        self.escalations = 0

    @property
    def done(self) -> bool:
        return self.pushed >= self.actor_input.max_items or self.billing.budget_exhausted

    def add(self, ref: Ref) -> None:
        bucket = self.teams if ref.kind == "team" else self.players
        if all(r.id != ref.id for r in bucket):
            bucket.append(ref)

    async def push(self, rows: list[dict[str, Any]], event: str) -> int:
        room = self.actor_input.max_items - self.pushed
        if room <= 0 or self.billing.budget_exhausted or not rows:
            return 0
        pushed = await self.billing.push(rows[:room], event)
        self.pushed += pushed
        return pushed

    def record_failure(self, label: str, exc: Exception) -> None:
        Actor.log.warning(f"Failed to scrape {label}: {exc}")
        self.errors.append(str(exc))
        self.failed.append(label)


async def run_all(client: FlashscoreClient, state: RunState) -> None:
    await resolve_searches(client, state)
    index = 0
    while index < len(state.teams) and not state.done:
        await scrape_team(client, state, state.teams[index])
        index += 1
    await scrape_players(client, state)


# ------------------------------------------------------------------ search


async def resolve_searches(client: FlashscoreClient, state: RunState) -> None:
    sport = state.actor_input.search_sport
    for query in state.actor_input.search_queries:
        try:
            results = await client.search(query)
        except FlashscoreError as exc:
            state.record_failure(f"search {query!r}", exc)
            continue
        ref, hit = pick_hit(results, sport)
        if ref is None:
            state.not_found += 1
            hint = (
                " Only individual-sport players (e.g. tennis) matched; this Actor covers teams and "
                "team-sport players."
                if has_individual_hit(results)
                else ""
            )
            await Billing.push_unbilled({
                "recordType": "error",
                "error": "NO_SEARCH_MATCH",
                "query": query,
                "errorMessage": (
                    f"Flashscore search found no team or player for {query!r}"
                    f"{f' in {sport}' if sport else ''} (not charged).{hint}"
                ),
            })
            continue
        sport_name = ((hit or {}).get("sport") or {}).get("name")
        Actor.log.info(f"Search {query!r} -> {ref.kind} {hit.get('name')} ({sport_name}) {ref.url}")
        state.add(ref)


# ------------------------------------------------------------------ teams


async def scrape_team(client: FlashscoreClient, state: RunState, ref: Ref) -> None:
    try:
        page = parse_team_page(await client.page(ref.path), ref.path)
    except FlashscoreNotFoundError:
        state.not_found += 1
        await Billing.push_unbilled({
            "recordType": "error",
            "error": "TEAM_NOT_FOUND",
            "url": ref.url,
            "errorMessage": (
                f"Flashscore has no team at {ref.url} (not charged). The id and the name in the URL "
                "must both match; search for the team by name if unsure."
            ),
        })
        return
    except (FlashscoreError, TeamPageError) as exc:
        state.record_failure(f"team {ref.url}", exc)
        return

    actor_input = state.actor_input
    sections = set(actor_input.team_sections)
    context = {"team": page["name"], "teamId": page["teamId"]}
    squad_total = page["squad"].get("overall-all") or []

    if "profile" in sections:
        await state.push([team_profile(page)], bill.TEAM_EVENT)

    if "squad" in sections and not state.done:
        await state.push(squad_rows(page, context, per_competition=actor_input.squad_per_competition), bill.SQUAD_EVENT)

    for kind, limit in (("results", actor_input.max_results), ("fixtures", None)):
        if kind not in sections or state.done:
            continue
        try:
            matches = await team_matches(client, page, kind, limit)
        except FlashscoreError as exc:
            state.record_failure(f"{kind} of {page['name']}", exc)
            continue
        await state.push([{"recordType": "match", **context, **m} for m in matches], bill.MATCH_EVENT)

    if "transfers" in sections and not state.done:
        try:
            transfers = await team_transfers(client, page["teamId"], actor_input.max_transfers)
        except FlashscoreError as exc:
            state.record_failure(f"transfers of {page['name']}", exc)
        else:
            await state.push(
                [{"recordType": "transfer", "source": "team", **context, **t} for t in transfers],
                bill.TRANSFER_EVENT,
            )

    if actor_input.scrape_squad_players:
        for row in squad_total:
            player_ref = parse_ref(row.get("playerUrl") or "")
            if player_ref:
                state.add(player_ref)
    state.teams_done += 1
    Actor.log.info(f"{page['name']}: done ({state.pushed} row(s) so far).")


def team_profile(page: dict[str, Any]) -> dict[str, Any]:
    total = page["squad"].get("overall-all") or []
    coach = next((r["player"] for r in total if r["role"] == "coach"), None)
    feeds = page["feeds"]
    return {
        "recordType": "team",
        "team": page["name"],
        "teamId": page["teamId"],
        "url": page["url"],
        "sport": page["sport"],
        "country": page["country"],
        "logoUrl": page["logoUrl"],
        "stadium": page["stadium"],
        "stadiumCity": page["stadiumCity"],
        "capacity": page["capacity"],
        "ranking": page["ranking"],
        "coach": coach,
        "squadSize": sum(1 for r in total if r["role"] == "player") if total else None,
        "competitions": [c["name"] for c in page["competitions"] if c["type"] != "all" and c["name"]] or None,
        "totalResults": feeds["results"]["allEventsCount"] if "results" in feeds else None,
        "upcomingFixtures": feeds["fixtures"]["allEventsCount"] if "fixtures" in feeds else None,
    }


def squad_rows(page: dict[str, Any], context: dict[str, Any], *, per_competition: bool) -> list[dict[str, Any]]:
    rows = []
    for competition in page["competitions"]:
        if competition["type"] != "all" and not per_competition:
            continue
        scope = "Total" if competition["type"] == "all" else competition["name"]
        for r in page["squad"].get(competition["key"]) or []:
            rows.append({"recordType": "squadPlayer", **context, "squadScope": scope, **r})
    return rows


async def team_matches(
    client: FlashscoreClient, page: dict[str, Any], kind: str, limit: int | None
) -> list[dict[str, Any]]:
    """The embedded list, then `pr_`/`pf_` pages until `limit` (or the whole
    history) is reached. Pages overlap the embedded list, hence the dedupe.
    Results come newest first, fixtures soonest first."""
    block = page["feeds"].get(kind)
    if not block:
        return []
    team_id = page["teamId"]
    matches: dict[str, dict[str, Any]] = {}
    for m in parse_team_matches(block["data"], team_id):
        matches.setdefault(m["eventId"], m)
    total = block["allEventsCount"]
    wanted = min(total, limit) if limit else total
    if len(matches) < wanted and page["sportId"] and page["countryId"]:
        for number in range(1, MAX_MATCH_PAGES + 1):
            text = await client.feed(
                team_feed(kind, sport_id=page["sportId"], country_id=page["countryId"], team_id=team_id, page=number)
            )
            more = parse_team_matches(text, team_id) if not is_empty(text) else []
            if not more:
                break
            for m in more:
                matches.setdefault(m["eventId"], m)
            if len(matches) >= wanted:
                break
    rows = sorted(matches.values(), key=lambda m: m["startTime"] or "", reverse=kind == "results")
    return rows[:limit] if limit else rows


async def team_transfers(client: FlashscoreClient, team_id: str, limit: int | None) -> list[dict[str, Any]]:
    """`tetr_{team}_1_{page}` (all directions), newest first, until `limit` or the end."""
    rows: dict[tuple, dict[str, Any]] = {}
    for number in range(1, MAX_TRANSFER_PAGES + 1):
        text = await client.feed(f"tetr_{team_id}_1_{number}")
        page_rows = parse_team_transfers(text) if not is_empty(text) else []
        if not page_rows:
            break
        for t in page_rows:
            key = (t["date"], t["playerId"], t["direction"], t["fromTeamId"], t["toTeamId"])
            rows.setdefault(key, t)
        if limit and len(rows) >= limit:
            break
    out = list(rows.values())
    return out[:limit] if limit else out


# ------------------------------------------------------------------ players


async def scrape_players(client: FlashscoreClient, state: RunState) -> None:
    index = 0
    while index < len(state.players) and not state.done:
        chunk = state.players[index : index + PLAYER_CONCURRENCY]
        index += len(chunk)
        results = await asyncio.gather(*(scrape_player(client, state, ref) for ref in chunk))
        for batches in results:
            if batches is None:
                continue
            for rows, event in batches:
                if state.done:
                    return
                await state.push(rows, event)
            state.players_done += 1


async def scrape_player(
    client: FlashscoreClient, state: RunState, ref: Ref
) -> list[tuple[list[dict[str, Any]], str]] | None:
    """One player page -> (rows, event) batches in push order; None if it could not be scraped."""
    try:
        html = await client.page(ref.path)
    except FlashscoreNotFoundError:
        state.not_found += 1
        await Billing.push_unbilled({
            "recordType": "error",
            "error": "PLAYER_NOT_FOUND",
            "url": ref.url,
            "errorMessage": (
                f"Flashscore has no player at {ref.url} (not charged). The id and the name in the URL "
                "must both match; search for the player by name if unsure."
            ),
        })
        return None
    except FlashscoreError as exc:
        state.record_failure(f"player {ref.url}", exc)
        return None

    try:
        data = parse_player_page(html, ref.path)
    except PlayerPageError as exc:
        if ENV_MARKER not in html and "teamPageEnvironment" in html:
            await Billing.push_unbilled({
                "recordType": "error",
                "error": "UNSUPPORTED_PLAYER",
                "url": ref.url,
                "errorMessage": (
                    f"{ref.url} is an individual-sport player (e.g. tennis), which has no squad, career "
                    "or transfer data on Flashscore (not charged)."
                ),
            })
            state.notes.append("Individual-sport players (tennis) are skipped.")
        else:
            state.record_failure(f"player {ref.url}", exc)
        return None

    sections = set(state.actor_input.player_sections)
    profile = data["profile"]
    context = {"player": profile["player"], "playerId": profile["playerId"]}
    batches: list[tuple[list[dict[str, Any]], str]] = []
    if "profile" in sections:
        batches.append(([profile], bill.PLAYER_EVENT))
    if "career" in sections:
        batches.append((_detail(context, data["career"]), bill.DETAIL_EVENT))
    if "lastMatches" in sections:
        batches.append((_detail(context, data["lastMatches"]), bill.DETAIL_EVENT))
    if "transfers" in sections:
        transfers = [
            {
                "recordType": "transfer",
                "source": "player",
                **t,
                "player": profile["player"],
                "playerId": profile["playerId"],
                "playerUrl": profile["url"],
                "nationality": profile["nationality"],
            }
            for t in data["transfers"]
        ]
        batches.append((transfers, bill.TRANSFER_EVENT))
    if "injuries" in sections:
        batches.append((_detail(context, data["injuries"]), bill.DETAIL_EVENT))
    return [(rows, event) for rows, event in batches if rows]


def _detail(context: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"recordType": r["recordType"], **context, **r} for r in rows]


# ------------------------------------------------------------------ reporting


async def _report(state: RunState) -> None:
    if state.pushed == 0 and state.not_found == 0 and state.errors:
        sample = "; ".join(state.errors[:3])
        await Actor.fail(
            status_message=(
                f"Could not scrape anything -- every Flashscore request failed "
                f"({len(state.errors)} error(s)). Sample: {sample}"
            )
        )
        return

    if state.escalations:
        Actor.log.info(f"Flashscore refused some requests; {state.escalations} proxy IP(s) were used.")

    charged = state.billing.charged
    parts = [
        (charged[bill.TEAM_EVENT], "team profile", "team profiles"),
        (charged[bill.SQUAD_EVENT], "squad member", "squad members"),
        (charged[bill.MATCH_EVENT], "match", "matches"),
        (charged[bill.TRANSFER_EVENT], "transfer", "transfers"),
        (charged[bill.PLAYER_EVENT], "player profile", "player profiles"),
        (charged[bill.DETAIL_EVENT], "player detail row", "player detail rows"),
    ]
    listed = ", ".join(f"{n} {one if n == 1 else many}" for n, one, many in parts if n)
    summary = (
        f"Done. {state.teams_done} team(s) and {state.players_done} player(s) scraped: "
        f"{listed or 'no rows'}."
    )
    if state.billing.budget_exhausted:
        summary += " Stopped early: the run's maximum charge was reached."
    elif state.pushed >= state.actor_input.max_items:
        summary += f" Stopped at the maxItems cap of {state.actor_input.max_items}."
    if state.not_found:
        summary += f" {state.not_found} team(s)/player(s)/search(es) not found on Flashscore (not charged)."
    if state.notes:
        notes = list(dict.fromkeys(state.notes))
        summary += " " + " ".join(notes[:3]) + (f" (+{len(notes) - 3} more)" if len(notes) > 3 else "")
    if state.failed:
        shown = ", ".join(state.failed[:10])
        more = f" and {len(state.failed) - 10} more" if len(state.failed) > 10 else ""
        summary += f" {len(state.failed)} request(s) failed: {shown}{more}. Re-running usually succeeds."
    Actor.log.info(summary)
    await Actor.set_status_message(summary)


async def _report_bad_input(exc: Exception) -> None:
    message = str(exc)
    Actor.log.error(f"Invalid input: {message}")
    await Actor.push_data({"recordType": "error", "error": "INVALID_INPUT", "errorMessage": message})
    await Actor.exit(status_message=f"Invalid input: {message}")


async def _build_proxy_strategy(actor_input: ActorInput) -> tuple[str | None, Any]:
    """No proxy by default: Flashscore's hosts do not gate on IP."""
    proxy_input = actor_input.proxy_config_input
    if proxy_input and proxy_input.get("useApifyProxy"):
        configuration = await Actor.create_proxy_configuration(actor_proxy_input=proxy_input)
        if configuration:
            Actor.log.info("Using the proxy configuration from input.")
            return await configuration.new_url(), SessionRotator(configuration)
        Actor.log.warning("The proxy configuration from input could not be created; going direct.")
    return None, TieredProxyFallback()
