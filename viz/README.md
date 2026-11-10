# Web views (`viz/`)

A static web page built with D3 v7: no build step and no npm install. D3 is loaded from the jsDelivr CDN at a pinned version (`d3@7.9.0`).

## Run it locally

The page loads JSON with `fetch`, so it has to be served over HTTP. Opening `index.html` straight from disk doesn't work.

```bash
cd viz
python3 -m http.server 8000
# open http://localhost:8000
```

After any rerun of pipeline steps 05, 08 or 09, refresh the data:

```bash
export BROADWAY_DATA_DIR=~/broadway-data
python scripts/13_export_viz_data.py      # writes viz/data/*.json
```

## Publish (GitHub Pages)

`.github/workflows/pages.yml` publishes this folder on every push to `main` that touches `viz/`. It can also be run by hand from the Actions tab.

One-time setup on GitHub:

1. Open **Settings → Pages** and set **Source** to **GitHub Actions**.
2. Merge to `main`, or run the workflow from the **Actions** tab.

The site appears at `https://<owner>.github.io/<repo>/`. Free GitHub Pages needs a public repository.

## Layout

| Path | What it is |
|---|---|
| `index.html` | Page shell: header, view navigation, one `<main>` the views render into, a shared tooltip |
| `css/style.css` | Design tokens (colours, type) as CSS custom properties for light and dark mode, then layout. Restyle the project by changing the tokens, not the views |
| `js/main.js` | Loads the data once, then renders the view named in the URL hash (`#data`, `#trajectory`, …) |
| `js/data.js` | `loadData()` returns a `db` object: the raw tables, lookup maps (`showById`, `personById`, `theatreById`, `creditsByPerson`, `creditsByShow`, `showsByTheatre`) and helpers (`theatreOf`, `standing`, `career`) |
| `js/grid.js` | `toGrid(lat, lon)` converts to Manhattan grid units (street number, avenue number), plus Broadway's diagonal and the avenue list. This is the base of the stylized Theater District map |
| `js/tooltip.js` | One shared tooltip |
| `js/views/*.js` | One file per view, each exporting `render…(el, db)` |
| `data/*.json` | Written by `scripts/13_export_viz_data.py`. Don't edit by hand |

## Data files

| File | One entry per | Fields |
|---|---|---|
| `meta.json` | — | export date, counts, network settings (roles, window, horizon, cutoffs), coverage notes |
| `theatres.json` | theatre (86) | `id` (Wikidata QID), `name` (current name), `lat`, `lon`, `opened`, `demolished`, `first_show`, `last_show`, `n_shows` |
| `shows.json` | core show (1,234) | `id`, `title`, `year` (opening), `venue` (theatre id or null), `venue_basis`, `wiki` |
| `people.json` | person in the network (3,208) | `id`, `name`, `born`, `died`, `birthplace`, `lat`, `lon` (birthplace), `wiki` |
| `credits.json` | person–show pair (6,351) | `person`, `show`, `year`, `roles` (list), `original` (true/false/null), `strict`, `loose`, `posthumous` |
| `reunions.json` | pair per cutoff, by mode | compact rows `[cutoff, person_a, person_b, shows_together, reunion_shows, first_reunion_year]`; `data.js` expands them to objects |

**`strict` and `loose`** match the network modes of step 08. `strict` keeps credits confirmed as part of the original production; `loose` also keeps unknowns. Both drop posthumous credits. Views default to `strict`.

## Views

| Hash | View | Status |
|---|---|---|
| `#data` | Data check: counts, coverage notes, theatres on the grid with a year slider | working |
| `#trajectory` | One person's career as a path between theatres | planned |
| `#birthplaces` | Birthplace map | planned |
| `#showmap` | NYC show map, explore mode | planned |
| `#cohort` | Cohort view (animated) | planned |
| `#multiples` | Small-multiples baseline | planned |
