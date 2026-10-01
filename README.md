# Flashscore Teams & Players: Squads, Transfers

Scrape **team and player profiles** from Flashscore for football,
basketball, hockey and every other team sport it covers. For a team you get
the squad with season stats, the full match history, upcoming fixtures and
transfers with fees. For a player you get club, market value, contract
expiry, career stats for every season, the last 10 matches with ratings,
transfers and injury history.

- **Search by name.** Type "Real Madrid" or "Bukayo Saka". You don't need
  to find Flashscore URLs.
- **A team's whole history** if you want it. Arsenal's 5,077 results go
  back more than a century, and every transfer since the 1970s comes too,
  in under two minutes.
- **Market values and contracts.** These are the header fields Flashscore
  shows for footballers: market value (`€113.9m` plus a number),
  contract expiry and date of birth.
- **One switch for the whole squad.** Turn on full profiles for every squad
  member and a single team URL returns about 30 complete player profiles.
- **No API key, no browser, no proxy.** Runs are fast and cheap.

---

## What can it scrape?

| Data | What you get |
| --- | --- |
| **Team profile** | Name, sport, country, logo, stadium, city, capacity, FIFA ranking (national teams), coach, squad size, current competitions, size of the match archive |
| **Squad** | Every player and coach: shirt number, position group, nationality, age, current injury or suspension, and season stats (matches, minutes, goals, assists, cards; points, save % and goals-against average for hockey). One table for all competitions, or one per competition |
| **Results** | Past matches newest first, from the team's side: competition, venue, opponent, W/D/L, score, half-time and period scores, extra time and penalties |
| **Fixtures** | Every scheduled match |
| **Transfers (team)** | Arrivals and departures: date, player, nationality, from/to club, type (transfer, loan, return, free agent) and fee as a number |
| **Player profile** | Club, position, age, date of birth, market value, contract expiry, height, photo, current injury, career totals |
| **Career** | One row per season, club and competition (league, domestic cup, international cup, national team): matches, goals, assists, cards, rating, clean sheets. Basketball rows are per-game averages |
| **Last matches** | The 10 most recent matches with Flashscore rating, minutes, goals, assists, saves (or points, rebounds and steals), and why the player missed a match |
| **Transfers (player)** | Every career move with fee |
| **Injuries** | Injury history with dates, flagging any current injury |

Sports: football, basketball, hockey, handball, volleyball, American
football, baseball, rugby, futsal and any other team sport with team pages
on Flashscore. Tennis and other individual-sport players use a different
page type and are skipped, with a free note in the dataset.

---

## Output example

Each row has a `recordType`: `team`, `squadPlayer`, `match`, `transfer`,
`player`, `careerSeason`, `playerMatch` or `injury`. The dataset has one view
for each.

```json
{
  "recordType": "player",
  "player": "Bukayo Saka",
  "playerId": "08NLEo06",
  "sport": "football",
  "position": "Forward",
  "team": "Arsenal",
  "teamUrl": "https://www.flashscore.com/team/arsenal/hA1Zm19f/",
  "nationality": "England",
  "age": 25,
  "dateOfBirth": "2001-09-05",
  "marketValue": "€113.9m",
  "marketValueAmount": 113900000,
  "marketValueCurrency": "EUR",
  "contractExpires": "2030-06-30",
  "careerTotals": {
    "league": { "matchesPlayed": 255, "goals": 73, "assists": 50, "yellowCards": 28, "redCards": 0 },
    "national-team": { "matchesPlayed": 73, "goals": 21, "assists": 13 }
  },
  "url": "https://www.flashscore.com/player/saka-bukayo/08NLEo06/"
}
```

```json
{
  "recordType": "squadPlayer",
  "team": "Arsenal",
  "squadScope": "Total",
  "positionGroup": "Defenders",
  "player": "Mosquera Cristhian",
  "jerseyNumber": 3,
  "nationality": "Spain",
  "age": 22,
  "absence": "Muscle Injury",
  "matchesPlayed": 3,
  "minutesPlayed": 259,
  "goals": 0,
  "assists": 0,
  "playerUrl": "https://www.flashscore.com/player/mosquera-cristhian/4O15XViB/"
}
```

```json
{
  "recordType": "transfer",
  "source": "team",
  "team": "Arsenal",
  "date": "2026-09-02",
  "direction": "out",
  "transferType": "Transfer",
  "fee": "€70.0m",
  "feeAmount": 70000000,
  "player": "Martinelli Gabriel",
  "nationality": "Brazil",
  "fromTeam": "Arsenal",
  "toTeam": "Al Hilal"
}
```

```json
{
  "recordType": "match",
  "team": "Arsenal",
  "competition": "Premier League",
  "competitionCountry": "England",
  "startTime": "2026-09-19T14:00:00Z",
  "status": "finished",
  "venue": "away",
  "opponent": "Brighton",
  "result": "L",
  "homeTeam": "Brighton",
  "awayTeam": "Arsenal",
  "homeScore": 3,
  "awayScore": 0,
  "halfTimeScore": "2-0",
  "periodScores": [{ "home": 2, "away": 0 }, { "home": 1, "away": 0 }],
  "decidedBy": "regular-time",
  "url": "https://www.flashscore.com/match/j52jHsN8/"
}
```

```json
{
  "recordType": "careerSeason",
  "player": "LeBron James",
  "season": "2025/2026",
  "competitionType": "league",
  "competition": "NBA",
  "team": "Los Angeles Lakers",
  "statsPerGame": true,
  "matchesPlayed": 69,
  "minutesPlayed": 33.9,
  "points": 21.3,
  "rebounds": 6,
  "assists": 7.2
}
```

---

## How to use it

Give it team URLs, player URLs or plain names, in any combination.

**A club's squad, recent form and transfer window:**

```json
{ "teamUrls": ["https://www.flashscore.com/team/arsenal/hA1Zm19f/"] }
```

**Players by name: profiles, market values and careers:**

```json
{ "searchQueries": ["Bukayo Saka", "Declan Rice", "Erling Haaland"],
  "playerSections": ["profile", "career"] }
```

**Every player in a squad, with full profiles:**

```json
{ "teamUrls": ["https://www.flashscore.com/team/real-madrid/W8mj7MDD/"],
  "teamSections": ["profile", "squad"],
  "scrapeSquadPlayers": true }
```

**A team's complete match history for modelling:**

```json
{ "teamUrls": ["https://www.flashscore.com/team/arsenal/hA1Zm19f/"],
  "teamSections": ["results"], "maxResultsPerTeam": 0 }
```

**A hockey team, found by name:**

```json
{ "searchQueries": ["Rapperswil-Jona"], "searchSport": "hockey" }
```

### Tips

- **Name search** picks Flashscore's best team or team-sport player match.
  Some names belong to clubs in several sports. Set `searchSport` to choose
  one.
- **`maxResultsPerTeam`** and **`maxTransfersPerTeam`** default to the 50
  newest. Set either to `0` for everything Flashscore has.
- **Squad stats** cover the current season. `squadScope` is `Total` (all
  competitions) unless you turn on `squadPerCompetition`.
- **Basketball career rows are per-game averages** (`statsPerGame: true`).
  Career totals keep only counts, because a sum of averages means nothing.
- **Coaches** have player pages too. Their `role` is `coach`, and their
  career rows are from their playing days.
- A URL whose name part is wrong returns a free `TEAM_NOT_FOUND` /
  `PLAYER_NOT_FOUND` row. Flashscore needs both the name and the id.

---

## Pricing

Pay per event. You are charged only for rows you receive:

| Row | Price |
| --- | ---: |
| Player profile | $0.003 |
| Team profile | $0.002 |
| Squad member | $0.001 |
| Match (result or fixture) | $0.0005 |
| Transfer | $0.0005 |
| Player detail (career season, last match or injury) | $0.0002 |

Some examples:

- A club with default settings (profile, ~30 squad members, 50 results,
  ~40 fixtures, 50 transfers) costs about **$0.10**.
- A player with everything (profile, ~50 career seasons, 10 matches, ~20
  injuries) costs about **$0.02**.
- Arsenal's complete history of 5,077 results costs **$2.54**.

Invalid input, unknown teams or players and failed searches are never
charged. The run stops cleanly when it reaches your maximum charge.

---

## FAQ

**Is it legal to scrape Flashscore?** This Actor only collects publicly
visible sports data, without logging in. You are responsible for how you use
the data. Check Flashscore's terms and your local laws before using it
commercially.

**Why is the market value missing for some players?** Flashscore shows
market values for footballers only, and not for every one. Height appears
for basketball players. Anything else Flashscore lists in a player's header
goes into `otherInfo`.

**Can I get more than the last 10 matches of a player?** A player page
holds 10. For a full match list, scrape the player's team history with
`maxResultsPerTeam: 0`.

**Can I get league tables or whole seasons?** That's the Flashscore League
Archive Actor on this account.
