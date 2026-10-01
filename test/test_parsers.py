"""Parsers against pages and feeds captured on 2026-09-30."""

from __future__ import annotations

import pytest

from src.feeds import iso
from src.matches import parse_team_matches, team_feed
from src.player_page import PlayerPageError, parse_player_page
from src.search import has_individual_hit, pick_hit
from src.team_page import TeamPageError, parse_team_page
from src.transfers import dotted_date, parse_fee, parse_team_transfers
from src.urls import parse_ref, player_url_from_transfer

from conftest import (
    ARSENAL, ARTETA, DJOKOVIC, ENGLAND, LAKERS, LEBRON, NYFFELER, RAPPERSWIL, RAYA, SAKA, TAA,
    page, read, read_json,
)

# ------------------------------------------------------------------ urls


@pytest.mark.parametrize("text, kind, slug, entity_id", [
    ("https://www.flashscore.com/team/arsenal/hA1Zm19f/", "team", "arsenal", "hA1Zm19f"),
    ("https://www.flashscore.co.uk/team/arsenal/hA1Zm19f/squad/", "team", "arsenal", "hA1Zm19f"),
    ("flashscore.com/player/saka-bukayo/08NLEo06", "player", "saka-bukayo", "08NLEo06"),
    ("/player/raya-david/nkVV0IXb/?x=1", "player", "raya-david", "nkVV0IXb"),
    ("HTTPS://WWW.FLASHSCORE.COM/TEAM/Arsenal/hA1Zm19f/", "team", "arsenal", "hA1Zm19f"),
])
def test_parse_ref(text, kind, slug, entity_id):
    ref = parse_ref(text)
    assert (ref.kind, ref.slug, ref.id) == (kind, slug, entity_id)
    assert ref.url == f"https://www.flashscore.com/{kind}/{slug}/{entity_id}/"


@pytest.mark.parametrize("text", [
    "", "arsenal", "https://www.flashscore.com/football/england/premier-league/",
    "https://www.flashscore.com/team/arsenal/", "https://www.flashscore.com/team/arsenal/hA1Zm19/",
])
def test_parse_ref_rejects(text):
    assert parse_ref(text) is None


def test_transfer_player_links_point_at_player_pages():
    assert player_url_from_transfer("/team/martinelli/dITe5M88/") == "https://www.flashscore.com/player/martinelli/dITe5M88/"
    assert player_url_from_transfer(None) is None


# ------------------------------------------------------------------ small helpers


@pytest.mark.parametrize("fee, expected", [
    ("€70.0m", (70_000_000, "EUR")),
    ("€500k", (500_000, "EUR")),
    ("£1.2bn", (1_200_000_000, "GBP")),
    ("$3m", (3_000_000, "USD")),
    ("", (None, None)),
    (None, (None, None)),
    ("free", (None, None)),
])
def test_parse_fee(fee, expected):
    assert parse_fee(fee) == expected


def test_dates():
    assert dotted_date("04.07.2024") == "2024-07-04"
    assert dotted_date("12.09.26") == "2026-09-12"
    assert dotted_date("") is None
    assert iso(-1864976400) == "1910-11-26T15:00:00Z"
    assert iso(0) is None and iso(None) is None


# ------------------------------------------------------------------ team page


def test_arsenal_page():
    p = parse_team_page(page(ARSENAL), ARSENAL)
    assert (p["name"], p["teamId"], p["sport"], p["sportId"]) == ("Arsenal", "hA1Zm19f", "football", 1)
    assert (p["country"], p["countryId"]) == ("England", "198")
    assert (p["stadium"], p["stadiumCity"], p["capacity"]) == ("Emirates Stadium", "London", 60704)
    assert p["ranking"] is None and not p["individual"]
    assert p["feeds"]["results"]["allEventsCount"] == 5077
    assert p["feeds"]["fixtures"]["allEventsCount"] == 41
    names = [c["name"] for c in p["competitions"]]
    assert names == ["Premier League", "EFL Cup", "FA Community Shield", "Champions League", "Total"]

    total = p["squad"]["overall-all"]
    assert len(total) == 32
    assert [r["positionGroup"] for r in total][:1] == ["Goalkeepers"] and total[-1]["role"] == "coach"
    assert total[-1]["player"] == "Arteta Mikel" and total[-1]["jerseyNumber"] is None
    mosquera = next(r for r in total if r["player"] == "Mosquera Cristhian")
    assert mosquera["absence"] == "Muscle Injury" and mosquera["nationality"] == "Spain"
    assert mosquera["playerUrl"] == "https://www.flashscore.com/player/mosquera-cristhian/4O15XViB/"
    assert {"matchesPlayed", "minutesPlayed", "goals", "assists", "yellowCards", "redCards"} <= set(total[0])


def test_basketball_squad_has_no_groups_or_stats():
    p = parse_team_page(page(LAKERS), LAKERS)
    assert (p["sport"], p["stadium"], p["stadiumCity"], p["capacity"]) == ("basketball", "Crypto.com Arena", "Los Angeles, CA", None)
    total = p["squad"]["overall-all"]
    assert len(total) == 19
    doncic = next(r for r in total if r["player"] == "Doncic Luka")
    assert doncic["positionGroup"] is None and doncic["jerseyNumber"] == 77 and doncic["absence"] == "Hamstring Injury"
    assert "matchesPlayed" not in doncic


def test_hockey_squad_columns():
    p = parse_team_page(page(RAPPERSWIL), RAPPERSWIL)
    keeper = p["squad"]["overall-all"][0]
    assert keeper["positionGroup"] == "Goalkeepers"
    assert {"savePercentage", "goalsAgainstAverage", "cleanSheets"} <= set(keeper)
    forward = next(r for r in p["squad"]["overall-all"] if r["positionGroup"] == "Forwards")
    assert {"goals", "assists", "points"} <= set(forward)


def test_national_team_ranking():
    p = parse_team_page(page(ENGLAND), ENGLAND)
    assert (p["sport"], p["ranking"], p["stadium"]) == ("football", "FIFA: 4", None)
    assert p["feeds"]["results"]["allEventsCount"] == 691


def test_not_a_team_page():
    with pytest.raises(TeamPageError):
        parse_team_page("<html>nothing</html>", ARSENAL)


# ------------------------------------------------------------------ matches


def test_embedded_results_seen_from_the_team():
    p = parse_team_page(page(ARSENAL), ARSENAL)
    matches = parse_team_matches(p["feeds"]["results"]["data"], "hA1Zm19f")
    assert len(matches) == 43
    assert all(m["venue"] in ("home", "away") for m in matches)
    for m in matches:
        mine, theirs = (m["homeScore"], m["awayScore"]) if m["venue"] == "home" else (m["awayScore"], m["homeScore"])
        assert m["result"] == ("W" if mine > theirs else "L" if mine < theirs else "D") or m["decidedBy"] == "penalties"


def test_paged_results():
    matches = parse_team_matches(read("pr_1_198_hA1Zm19f_1.txt"), "hA1Zm19f")
    assert len(matches) == 40
    united = matches[0]
    assert (united["competition"], united["competitionCountry"], united["competitionStage"]) == ("Premier League", "England", None)
    assert (united["venue"], united["opponent"], united["opponentId"], united["result"]) == ("home", "Manchester Utd", "ppjDR086", "L")
    assert (united["homeScore"], united["awayScore"], united["halfTimeScore"]) == (2, 3, "1-1")
    inter = matches[1]
    assert (inter["competition"], inter["competitionStage"], inter["venue"], inter["result"]) == ("Champions League", "League phase", "away", "W")


def test_fixtures_have_no_result():
    fixtures = parse_team_matches(read("pf_1_198_hA1Zm19f_1.txt"), "hA1Zm19f")
    assert fixtures and all(m["status"] == "scheduled" and m["result"] is None for m in fixtures)


def test_team_feed_name():
    assert team_feed("results", sport_id=1, country_id="198", team_id="hA1Zm19f", page=3) == "pr_1_198_hA1Zm19f_3_0_en_1"
    assert team_feed("fixtures", sport_id=3, country_id="200", team_id="ngegZ8bg", page=1) == "pf_3_200_ngegZ8bg_1_0_en_1"


# ------------------------------------------------------------------ transfers


def test_team_transfers_read_only_the_all_group():
    rows = parse_team_transfers(read("tetr_hA1Zm19f_1_1.txt"))
    assert len(rows) == 15
    martinelli = rows[1]
    assert martinelli == {
        "recordType": "transfer",
        "date": "2026-09-02",
        "direction": "out",
        "transferType": "Transfer",
        "fee": "€70.0m",
        "feeAmount": 70_000_000,
        "feeCurrency": "EUR",
        "player": "Martinelli Gabriel",
        "playerId": "dITe5M88",
        "playerUrl": "https://www.flashscore.com/player/martinelli/dITe5M88/",
        "nationality": "Brazil",
        "fromTeam": "Arsenal",
        "fromTeamId": "hA1Zm19f",
        "fromTeamUrl": "https://www.flashscore.com/team/arsenal/hA1Zm19f/",
        "toTeam": "Al Hilal",
        "toTeamId": "hxxcePl9",
        "toTeamUrl": "https://www.flashscore.com/team/al-hilal/hxxcePl9/",
    }
    assert rows[0]["transferType"] is None and rows[0]["fee"] is None
    assert {r["direction"] for r in rows} == {"in", "out"}


def test_empty_transfer_page():
    assert parse_team_transfers("") == []
    assert parse_team_transfers("A1÷c894efc05e4e85989175fdb33221d405¬~") == []


# ------------------------------------------------------------------ player page


def test_saka_profile():
    data = parse_player_page(page(SAKA), SAKA)
    p = data["profile"]
    assert (p["player"], p["playerId"], p["sport"], p["role"], p["position"]) == ("Bukayo Saka", "08NLEo06", "football", "player", "Forward")
    assert (p["team"], p["teamId"], p["nationality"]) == ("Arsenal", "hA1Zm19f", "England")
    assert (p["age"], p["dateOfBirth"], p["contractExpires"]) == (25, "2001-09-05", "2030-06-30")
    assert (p["marketValue"], p["marketValueAmount"], p["marketValueCurrency"]) == ("€113.9m", 113_900_000, "EUR")
    assert p["careerTotals"]["league"] == {"matchesPlayed": 255, "goals": 73, "assists": 50, "yellowCards": 28, "redCards": 0, "cleanSheets": 0}
    assert set(p["careerTotals"]) == {"league", "domestic-cup", "international-cup", "national-team"}
    assert len(data["career"]) == 59 and len(data["lastMatches"]) == 10
    assert data["transfers"] == [] and len(data["injuries"]) == 34


def test_goalkeeper_career_and_match_stats():
    data = parse_player_page(page(RAYA), RAYA)
    season = data["career"][0]
    assert (season["season"], season["competitionType"], season["competition"], season["team"]) == ("2026/2027", "league", "Premier League", "Arsenal")
    assert (season["teamId"], season["savePercentage"], season["cleanSheets"], season["rating"]) == ("hA1Zm19f", 69.2, 3, 6.9)
    assert season["statsPerGame"] is False
    played = [m for m in data["lastMatches"] if m.get("minutesPlayed") is not None]
    assert played and all({"saves", "shotsOnTargetFaced", "yellowCards", "redCards"} <= set(m) for m in played)
    assert all(m["shotsOnTargetFaced"] >= m["saves"] for m in played)
    bench = next(m for m in data["lastMatches"] if m["absence"] == "on the bench")
    assert bench["rating"] is None and "minutesPlayed" not in bench
    move = data["transfers"][0]
    assert (move["date"], move["fromTeam"], move["toTeam"], move["feeAmount"]) == ("2024-07-04", "Brentford", "Arsenal", 31_900_000)
    assert move["fromTeamId"] == "xYe7DwID"


def test_basketball_career_is_per_game():
    data = parse_player_page(page(LEBRON), LEBRON)
    p = data["profile"]
    assert (p["sport"], p["team"], p["heightCm"], p["marketValue"]) == ("basketball", None, 206, None)
    assert p["careerTotals"]["league"] == {"matchesPlayed": 1026}
    season = data["career"][0]
    assert season["statsPerGame"] is True and (season["points"], season["assists"]) == (21.3, 7.2)
    match = data["lastMatches"][0]
    assert (match["minutesPlayed"], match["points"], match["rebounds"], match["turnovers"]) == (40.43, 24, 12, 4)
    assert (match["season"], match["result"]) == ("2025/2026", "L")


def test_coach_profile():
    p = parse_player_page(page(ARTETA), ARTETA)["profile"]
    assert (p["role"], p["position"], p["team"], p["contractExpires"]) == ("coach", "Coach", "Arsenal", "2027-05-31")


def test_hockey_goalkeeper_totals_drop_summed_averages():
    data = parse_player_page(page(NYFFELER), NYFFELER)
    totals = data["profile"]["careerTotals"]["league"]
    assert "savePercentage" not in totals and "goalsAgainstAverage" not in totals
    assert totals["matchesPlayed"] == 513
    assert data["career"][0]["goalsAgainstAverage"] == 4.61


def test_injured_player_and_current_club():
    data = parse_player_page(page(TAA), TAA)
    assert data["profile"]["team"] == "Real Madrid" and len(data["injuries"]) == 26
    assert data["lastMatches"][0]["ratingRank"] == 1


def test_tennis_player_page_is_not_a_profile():
    with pytest.raises(PlayerPageError):
        parse_player_page(page(DJOKOVIC), DJOKOVIC)


# ------------------------------------------------------------------ search


def test_search_picks_the_team_sport_player():
    results = read_json("search_saka.json")
    ref, hit = pick_hit(results)
    assert (ref.kind, ref.slug, ref.id) == ("player", "saka-bukayo", "08NLEo06")
    assert hit["name"] == "Saka Bukayo"
    assert pick_hit(results, "basketball") == (None, None)
    assert has_individual_hit(results)


def test_search_skips_individual_players():
    results = [
        {"id": "AZg49Et9", "url": "djokovic-novak", "type": {"name": "Player"}, "sport": {"id": 2}},
        {"id": "ngegZ8bg", "url": "los-angeles-lakers", "type": {"name": "Team"}, "sport": {"id": 3}},
    ]
    ref, _ = pick_hit(results)
    assert ref.path == "/team/los-angeles-lakers/ngegZ8bg/"
