# SuumoViz data

This branch holds only data. It is written once a day by the `Daily crawl`
GitHub Actions workflow on `main`; do not commit to it by hand.

| Path | Content |
|---|---|
| `listings/{category}.csv` | current state of every listing (sorted by `listing_id`) |
| `events/{YYYY-MM}.csv` | new / price_change / delisted / relisted events |
| `counts/{YYYY}.csv` | listings per municipality × category, every day (from the city pages) |
| `stats/{YYYY}.csv` | price quartiles and unit-price median per municipality × category (`sample` = pages fetched that day, `census` = all active listings) |
| `runs.csv` | one row per day: slot, status, requests, pages, merged, quality, event counts |
| `state.json` | rotation offsets, cooldown, robots.txt digest |

Field definitions and rules: `docs/design.md` on the `main` branch.

Read it locally next to the code:

```bash
git fetch origin data
git worktree add data data   # once, inside the SuumoViz checkout
git -C data pull             # afterwards
```
