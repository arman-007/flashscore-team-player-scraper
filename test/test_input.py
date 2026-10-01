from __future__ import annotations

import pytest

from src.input import DEFAULT_MAX_RESULTS, PLAYER_SECTIONS, TEAM_SECTIONS, parse_input


def test_defaults():
    i = parse_input({"teamUrls": ["https://www.flashscore.com/team/arsenal/hA1Zm19f/"]})
    assert [r.path for r in i.teams] == ["/team/arsenal/hA1Zm19f/"]
    assert i.players == [] and i.search_queries == [] and i.search_sport is None
    assert i.team_sections == list(TEAM_SECTIONS) and i.player_sections == list(PLAYER_SECTIONS)
    assert (i.max_results, i.max_transfers, i.max_items) == (DEFAULT_MAX_RESULTS, 50, 10000)
    assert not i.squad_per_competition and not i.scrape_squad_players


def test_urls_are_routed_by_kind_and_deduplicated():
    i = parse_input({
        "teamUrls": [
            "https://www.flashscore.co.uk/team/arsenal/hA1Zm19f/squad/",
            {"url": "https://www.flashscore.com/team/arsenal/hA1Zm19f/"},
            "https://www.flashscore.com/player/saka-bukayo/08NLEo06/",
        ],
        "playerUrls": ["https://www.flashscore.com/player/saka-bukayo/08NLEo06/", ""],
    })
    assert [r.id for r in i.teams] == ["hA1Zm19f"]
    assert [r.id for r in i.players] == ["08NLEo06"]


def test_search_only_is_enough():
    i = parse_input({"searchQueries": ["  Real   Madrid ", "real madrid", "Saka"], "searchSport": "Soccer"})
    assert i.search_queries == ["Real Madrid", "Saka"] and i.search_sport == "football"


def test_zero_means_no_limit():
    i = parse_input({"searchQueries": ["Arsenal"], "maxResultsPerTeam": 0, "maxTransfersPerTeam": "0"})
    assert i.max_results is None and i.max_transfers is None


def test_sections_are_case_insensitive():
    i = parse_input({"searchQueries": ["Arsenal"], "teamSections": ["Squad", "squad"], "playerSections": ["lastmatches"]})
    assert i.team_sections == ["squad"] and i.player_sections == ["lastMatches"]


@pytest.mark.parametrize("raw, message", [
    ({}, "at least one team or player"),
    ({"teamUrls": [""]}, "at least one team or player"),
    ({"teamUrls": ["https://www.flashscore.com/football/england/premier-league/"]}, "not a Flashscore team or player URL"),
    ({"searchQueries": ["A"]}, "too short"),
    ({"searchQueries": ["Arsenal"], "searchSport": "quidditch"}, "not a Flashscore sport"),
    ({"searchQueries": ["Arsenal"], "teamSections": ["lineups"]}, "not valid in `teamSections`"),
    ({"searchQueries": ["Arsenal"], "maxResultsPerTeam": -1}, r"0 \(no limit\) or more"),
    ({"searchQueries": ["Arsenal"], "maxItems": 0}, "at least 1"),
    ({"searchQueries": ["Arsenal"], "maxItems": "lots"}, "whole number"),
    ({"searchQueries": ["Arsenal"], "maxItems": True}, "whole number"),
])
def test_invalid_input(raw, message):
    with pytest.raises(ValueError, match=message):
        parse_input(raw)
