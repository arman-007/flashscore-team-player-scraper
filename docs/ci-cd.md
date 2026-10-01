# CI/CD

| Trigger | Workflow | Result |
| --- | --- | --- |
| Pull request to `main` / `production` | `ci.yml` | tests + schema validation |
| Push to `main` | `beta.yml` | tests, then Apify build tagged `beta` |
| Push to `production` | `deploy.yml` | tests, then Apify build tagged `latest` (what users run) |
| Thursdays 08:17 UTC | `canary.yml` | runs `latest` on live Flashscore and checks Arsenal and Saka |

All four workflows need one repository secret, `APIFY_TOKEN`. Any step that
drives the CLI logs in with `apify/setup-apify-cli-action@v1`, because the
CLI ignores the environment variable.

## Tests

`python -m pytest -q` runs against captured responses in `test/fixtures/`:

- team pages (gzipped): Arsenal, the Lakers, Rapperswil-Jona (hockey) and
  England (a national team);
- player pages (gzipped): Saka, Raya (a goalkeeper), LeBron James, Arteta
  (a coach), Nyffeler (a hockey goalie), Alexander-Arnold, and Djokovic
  (tennis, which must be rejected);
- Arsenal's `pr_`/`pf_` result and fixture pages, the `tetr_` transfers
  page, and a search API response.

They stay green through a Flashscore change. The canary is the check that
catches one.

`test_schemas.py` and `test_main.py` push every row shape the Actor can emit
through the dataset schema. The platform rejects a `null` in a non-nullable
field or a float in an integer field, and local runs never validate against
that schema.

## Canary

`scripts/canary-input.json` scrapes Arsenal (120 results, all fixtures, 40
transfers, the squad) and searches "Bukayo Saka" with every player section.
Because team data changes every week, `scripts/canary-check.mjs` checks
shape and coverage rather than exact values: every row has its key fields,
there are at least 110 distinct results newest first, at least 20 squad
members with a coach, 40 team transfers, and Saka's profile (id
`08NLEo06`, born 2001-09-05) with 10 last matches. On failure, the workflow
opens (or comments on) a `canary` issue.

| Symptom | Likely cause |
| --- | --- |
| fewer than 110 results | `pr_` feed name changed, or `country_id` / `participant_id` left the team page |
| squad checks red | `.lineup` markup changed (`lineupTable__row`, `lineupTable__cell--*`) |
| transfer checks red | `tetr_` changed (RTT, TEA, PLA nodes) |
| player checks red | `.playerHeader__wrapper` or `window.playerProfilePageEnvironment` changed |
| `NO_SEARCH_MATCH` for Saka | the search API's `type` names or fields changed |
| everything red, 401s in the log | `x-fsign` rotated and the refresh failed |

## The vendored push action

`.github/actions/push-actor/` wraps `apify push --force`. Without `--force`,
a `main` build followed by a `production` build refuses with "modified there
since modified locally". The action's header explains this in full.
