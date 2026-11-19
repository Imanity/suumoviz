# SuumoViz data

This branch holds only data. It is written once a day by the `Daily crawl`
GitHub Actions workflow on `main`; do not commit to it by hand.

Every CSV here is **obfuscated line by line** (first line `#suumoviz-obf/1`; see
`docs/design.md` section 5.2 on `main`). It is not encryption: decode a file with

```bash
suumoviz decode listings/used_condo.csv | head
```

| Path | Content |
|---|---|
| `listings/{category}.csv` | current state of every listing (sorted by `listing_id`) |
| `events/{YYYY-MM}.csv` | new / price_change / delisted / relisted events |
| `counts/{YYYY}.csv` | listings per municipality × category, every day (from the city pages) |
| `stats/{YYYY}.csv` | price quartiles and unit-price median per municipality × category (`sample` = pages fetched that day, `census` = all active listings) |
| `runs.csv` | one row per day: slot, status, requests, pages, merged, quality, event counts |
| `state.json` | rotation offsets, cooldown, robots.txt digest (plain JSON) |

History up to 2026-11-19 was collected in the former private repository
`Imanity/suumoviz-data` and imported here commit by commit, with every CSV encoded.

Read it locally next to the code:

```bash
git fetch origin data
git worktree add data data   # once, inside the SuumoViz checkout
git -C data pull             # afterwards
```
