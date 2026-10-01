"""Orchestration against a fake client serving the fixtures."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from src import billing as billing_module
from src import main as main_module
from src.flashscore_client import FlashscoreError, FlashscoreNotFoundError
from src.input import parse_input
from src.main import RunState, run_all

from conftest import ARSENAL, ARTETA, DJOKOVIC, LAKERS, RAYA, SAKA, page, read, read_json

TETR_1 = read("tetr_hA1Zm19f_1_1.txt")


class _Log:
    def info(self, *_a, **_k): ...
    def warning(self, *_a, **_k): ...
    def error(self, *_a, **_k): ...


class FakeActor:
    log = _Log()
    rows: list = []

    @classmethod
    async def push_data(cls, row, charged_event_name=None):
        cls.rows.append(row)


@pytest.fixture(autouse=True)
def fake_actor(monkeypatch):
    FakeActor.rows = []
    monkeypatch.setattr(main_module, "Actor", FakeActor)
    monkeypatch.setattr(billing_module, "Actor", FakeActor)
    return FakeActor


class FakeBilling:
    def __init__(self):
        self.budget_exhausted = False
        self.charged = Counter()
        self.pushed: list[tuple[str, list]] = []

    async def push(self, rows, event):
        self.pushed.append((event, rows))
        self.charged[event] += len(rows)
        return len(rows)

    def rows(self, event=None):
        return [r for e, rows in self.pushed if event in (None, e) for r in rows]


class FakeClient:
    def __init__(self, *, pages=None, feeds=None, search=None):
        self.pages = pages or {}
        self.feeds = feeds or {}
        self.search_results = search or {}
        self.feed_calls: list[str] = []
        self.page_calls: list[str] = []

    async def feed(self, name):
        self.feed_calls.append(name)
        value = self.feeds.get(name, "")
        if isinstance(value, Exception):
            raise value
        return value

    async def page(self, path):
        self.page_calls.append(path)
        value = self.pages.get(path)
        if value is None:
            raise FlashscoreNotFoundError(path)
        if isinstance(value, Exception):
            raise value
        return value

    async def search(self, query):
        value = self.search_results.get(query, [])
        if isinstance(value, Exception):
            raise value
        return value


SCHEMA = json.loads((Path(__file__).resolve().parents[1] / ".actor" / "dataset_schema.json").read_text())
JSON_TYPES = {"string": str, "number": (int, float), "boolean": bool, "array": list, "object": dict}


def assert_schema_ok(row):
    props = SCHEMA["fields"]["properties"]
    for key, value in row.items():
        assert key in props, key
        if value is None:
            assert "null" in props[key]["type"], key
            continue
        kinds = tuple(JSON_TYPES[t] for t in props[key]["type"] if t != "null")
        assert isinstance(value, kinds) and not (bool in kinds) ^ isinstance(value, bool), (key, value)


def state_for(raw):
    return RunState(billing=FakeBilling(), actor_input=parse_input(raw))


def arsenal_client(**extra_pages):
    return FakeClient(
        pages={ARSENAL: page(ARSENAL), **extra_pages},
        feeds={
            "pr_1_198_hA1Zm19f_1_0_en_1": read("pr_1_198_hA1Zm19f_1.txt"),
            "tetr_hA1Zm19f_1_1": TETR_1,
            "tetr_hA1Zm19f_1_2": TETR_1,  # overlapping pages must not duplicate rows
        },
    )


async def test_full_team():
    client = arsenal_client()
    state = state_for({"teamUrls": ["https://www.flashscore.com" + ARSENAL], "maxResultsPerTeam": 60, "maxTransfersPerTeam": 0})
    await run_all(client, state)
    b = state.billing
    assert [e for e, _ in b.pushed] == ["team-profile", "squad-player", "team-match", "team-match", "transfer"]

    profile = b.rows("team-profile")[0]
    assert (profile["team"], profile["coach"], profile["squadSize"], profile["totalResults"]) == ("Arsenal", "Arteta Mikel", 31, 5077)
    assert list(profile)[0] == "recordType"

    squad = b.rows("squad-player")
    assert len(squad) == 32 and {r["squadScope"] for r in squad} == {"Total"}

    results, fixtures = b.pushed[2][1], b.pushed[3][1]
    assert len(results) == 60 and len({m["eventId"] for m in results}) == 60
    assert [m["startTime"] for m in results] == sorted((m["startTime"] for m in results), reverse=True)
    assert len(fixtures) == 41 and all(m["status"] == "scheduled" for m in fixtures)
    assert [m["startTime"] for m in fixtures] == sorted(m["startTime"] for m in fixtures)
    assert client.feed_calls[0] == "pr_1_198_hA1Zm19f_1_0_en_1"
    assert not any(c.startswith("pf_") for c in client.feed_calls)

    transfers = b.rows("transfer")
    assert len(transfers) == 15 and all(t["source"] == "team" and t["team"] == "Arsenal" for t in transfers)
    assert "tetr_hA1Zm19f_1_3" in client.feed_calls

    for row in b.rows():
        assert_schema_ok(row)
    assert state.teams_done == 1 and client.page_calls == [ARSENAL]


async def test_embedded_results_need_no_feed_when_enough():
    client = arsenal_client()
    state = state_for({"teamUrls": ["https://www.flashscore.com" + ARSENAL], "teamSections": ["results"], "maxResultsPerTeam": 10})
    await run_all(client, state)
    assert len(state.billing.rows("team-match")) == 10 and client.feed_calls == []


async def test_squad_per_competition_and_fan_out():
    client = arsenal_client(**{ARTETA: page(ARTETA), RAYA: page(RAYA)})
    state = state_for({
        "teamUrls": ["https://www.flashscore.com" + ARSENAL],
        "teamSections": ["squad"],
        "squadPerCompetition": True,
        "scrapeSquadPlayers": True,
        "playerSections": ["profile"],
    })
    await run_all(client, state)
    scopes = Counter(r["squadScope"] for r in state.billing.rows("squad-player"))
    assert scopes["Total"] == 32 and scopes["Premier League"] == 22 and scopes["Champions League"] == 17
    # Every squad member's page was requested; only the two in the fixture set exist.
    assert len(client.page_calls) == 1 + 32
    names = {r["player"] for r in state.billing.rows("player-profile")}
    assert names == {"Mikel Arteta", "David Raya"}
    assert state.not_found == 30 and all(r["error"] == "PLAYER_NOT_FOUND" for r in FakeActor.rows)


async def test_player_with_every_section():
    client = FakeClient(pages={RAYA: page(RAYA)})
    state = state_for({"playerUrls": ["https://www.flashscore.com" + RAYA]})
    await run_all(client, state)
    b = state.billing
    assert [e for e, _ in b.pushed] == ["player-profile", "player-detail", "player-detail", "transfer", "player-detail"]
    assert Counter(r["recordType"] for r in b.rows("player-detail")) == {"careerSeason": 36, "playerMatch": 10, "injury": 4}
    detail = b.rows("player-detail")[0]
    assert list(detail)[:3] == ["recordType", "player", "playerId"] and detail["player"] == "David Raya"
    transfer = b.rows("transfer")[0]
    assert (transfer["source"], transfer["player"], transfer["playerId"]) == ("player", "David Raya", "nkVV0IXb")
    for row in b.rows():
        assert_schema_ok(row)
    assert state.players_done == 1


async def test_search_resolves_names():
    client = FakeClient(pages={SAKA: page(SAKA)}, search={"Bukayo Saka": read_json("search_saka.json")})
    state = state_for({"searchQueries": ["Bukayo Saka", "nobody at all"], "playerSections": ["profile"]})
    await run_all(client, state)
    assert state.billing.rows("player-profile")[0]["playerId"] == "08NLEo06"
    assert FakeActor.rows[0]["error"] == "NO_SEARCH_MATCH" and FakeActor.rows[0]["query"] == "nobody at all"


async def test_search_sport_filter_can_reject_the_only_match():
    client = FakeClient(search={"Saka": read_json("search_saka.json")})
    state = state_for({"searchQueries": ["Saka"], "searchSport": "basketball"})
    await run_all(client, state)
    assert FakeActor.rows[0]["error"] == "NO_SEARCH_MATCH" and "basketball" in FakeActor.rows[0]["errorMessage"]
    assert "individual-sport" in FakeActor.rows[0]["errorMessage"]


async def test_tennis_player_is_an_unbilled_note():
    client = FakeClient(pages={DJOKOVIC: page(DJOKOVIC)})
    state = state_for({"playerUrls": ["https://www.flashscore.com" + DJOKOVIC]})
    await run_all(client, state)
    assert FakeActor.rows[0]["error"] == "UNSUPPORTED_PLAYER" and state.billing.pushed == []
    assert state.players_done == 0 and not state.failed


async def test_unknown_team_is_an_unbilled_row():
    state = state_for({"teamUrls": ["https://www.flashscore.com/team/narnia/AAAAAAAA/"]})
    await run_all(FakeClient(), state)
    assert FakeActor.rows[0]["error"] == "TEAM_NOT_FOUND" and state.billing.pushed == [] and state.not_found == 1


async def test_failures_are_recorded_not_raised():
    client = FakeClient(
        pages={LAKERS: page(LAKERS), RAYA: FlashscoreError(RAYA, 500, "boom")},
        feeds={"tetr_ngegZ8bg_1_1": FlashscoreError("tetr_", 500, "boom")},
        search={"x y": FlashscoreError("search", 500, "boom")},
    )
    state = state_for({
        "teamUrls": ["https://www.flashscore.com" + LAKERS],
        "playerUrls": ["https://www.flashscore.com" + RAYA],
        "searchQueries": ["x y"],
        "teamSections": ["profile", "transfers"],
    })
    await run_all(client, state)
    assert len(state.failed) == 3
    assert any("transfers of Los Angeles Lakers" in f for f in state.failed)
    assert state.billing.rows("team-profile")[0]["team"] == "Los Angeles Lakers"


async def test_max_items_caps_rows():
    client = arsenal_client()
    state = state_for({"teamUrls": ["https://www.flashscore.com" + ARSENAL], "maxItems": 7})
    await run_all(client, state)
    assert len(state.billing.rows()) == 7 and state.done
    assert client.feed_calls == []
