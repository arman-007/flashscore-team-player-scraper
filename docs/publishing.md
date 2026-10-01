# Publishing

Market, pricing, listing copy and the Console settings. The Console steps
are applied by the agent. The only step reserved for the owner is the final
**Publish** click, which also accepts the monetization terms.

---

## 1. Market (Apify Store, 2026-09-30)

| Actor type | Price |
| --- | ---: |
| Transfermarkt player profiles (`bovi`, `webdatalabs`) | $3–$10 / 1K players |
| Transfermarkt squad members (`incognito_mode`) | $1.20 / 1K |
| Transfermarkt generic rows (`haketa`, `data_xplorer`, `parsebird`) | $1.25–$2 / 1K |
| Football API wrappers (`sian.agency`), profile | $24 / 1K |
| Football API wrappers (`sian.agency`), squad / transfer / match | $15 / 1K |
| Flashscore match listings (`extractify-labs`) | $1 / 1K |

There is no Flashscore team or player scraper in the Store. The Transfermarkt
Actors are football only and have no match history, and none offers
per-match player ratings. This listing competes on:

1. **Every team sport**, including per-game basketball and hockey goalie
   stats.
2. **Depth.** A club's whole match archive and transfer history, and a
   player's whole career, in one run.
3. **Name search** across sports.
4. **Price.** Profiles sit at the bottom of the Transfermarkt range. Bulk
   rows (matches, transfers) are half the usual $1 / 1K, because a full
   history is thousands of rows.

---

## 2. Pricing — pay per event

| Event | Code name | Price | Primary |
| --- | --- | ---: | :-: |
| Actor start | `apify-actor-start` | $0.00005 | |
| Player profile | `player-profile` | **$0.003** | ✅ |
| Team profile | `team-profile` | $0.002 | |
| Squad member | `squad-player` | $0.001 | |
| Team match | `team-match` | $0.0005 | |
| Transfer | `transfer` | $0.0005 | |
| Player detail | `player-detail` | $0.0002 | |

**Do not enable `apify-default-dataset-item`**, because it would bill every
row twice. Leave "Pay per event + usage" off. Set the minimum spend to $0.01.

### Measured cost (local, 2026-09-30)

| Run | Rows | Time |
| --- | ---: | ---: |
| Arsenal (10 results, 10 transfers) + Saka by search + LeBron James | 370 | 4 s |
| Lakers + England + Rapperswil by search + 3 players, per-competition squads | 962 | 14 s |
| Arsenal's complete history: 5,077 results, 1,694 transfers | 6,800 | ~100 s |

No proxy was used. At 512 MB even the full-history run costs well under
$0.01 of compute, so the margin is above 95% on every event.

---

## 3. Event titles and descriptions

| Event | Title | Description |
| --- | --- | --- |
| `player-profile` | Player profile | One player: club, position, age, date of birth, market value, contract expiry, height, photo, current injury and career totals. |
| `team-profile` | Team profile | One team: sport, country, stadium, capacity, coach, squad size, competitions and archive size. |
| `squad-player` | Squad member | One player or coach in a squad table, with shirt number, nationality, age, absence and season stats. |
| `team-match` | Team match | One past result or upcoming fixture of a team, from the team's side, with scores and period scores. |
| `transfer` | Transfer | One transfer with date, player, from/to club, type and fee. |
| `player-detail` | Player detail | One career season, one of the last 10 matches (with rating) or one injury of a player. |
| `apify-actor-start` | Actor start | Charged once when a run starts. The Actor runs at 512 MB, so this is under a tenth of a cent. |

---

## 4. Listing copy

| Field | Value |
| --- | --- |
| Unique name | `flashscore-team-player-scraper` |
| Title (45) | `Flashscore Teams & Players: Squads, Transfers` |
| SEO title | `Flashscore Player & Team Scraper: Squads, Stats` |
| Categories | `SPORTS`, `DEVELOPER_TOOLS`, `OTHER` |

**Description** (same text as `.actor/actor.json`):

```
Scrape Flashscore team and player profiles: squads with season stats, full match history, transfers with fees, market values, contracts, career stats per season, last-match ratings and injury history. Football, basketball, hockey and more. Search by name. No API key.
```

**SEO description**:

```
Football & sports player data from Flashscore: squads, market values, contracts, career stats, match ratings, transfers with fees and injuries.
```

---

## 5. Console settings (applied by the agent)

1. `defaultRunOptions` → 512 MB, 3600 s, build `latest`. A new Actor reads
   4096 MB, and the start event is billed per GB.
2. `exampleRunInput` → Arsenal plus a search for "Bukayo Saka".
3. Display information: logo, title, SEO title and descriptions from §4.
4. Monetization: the events from §2 and §3. `player-profile` is primary.
5. Publish. **This click is the owner's.**
