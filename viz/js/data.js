// Loads the JSON written by scripts/13_export_viz_data.py and builds lookup indexes.
// Every view gets the same `db` object, so views never parse files themselves.

const FILES = ["meta", "theatres", "shows", "people", "credits", "reunions", "basemap"];

async function fetchJson(name) {
  const res = await fetch(`data/${name}.json`);
  if (!res.ok) throw new Error(`Could not load data/${name}.json (${res.status})`);
  return res.json();
}

function groupBy(rows, key) {
  const m = new Map();
  for (const r of rows) {
    const k = r[key];
    if (!m.has(k)) m.set(k, []);
    m.get(k).push(r);
  }
  return m;
}

export async function loadData() {
  const [meta, theatres, shows, people, credits, reunionsRaw, basemap] = await Promise.all(FILES.map(fetchJson));

  const theatreById = new Map(theatres.map(t => [t.id, t]));
  const showById = new Map(shows.map(s => [s.id, s]));
  const personById = new Map(people.map(p => [p.id, p]));

  // reunions.json stores compact rows; expand them into objects once
  const cols = meta.columns.reunions;
  const reunions = {};
  for (const [mode, rows] of Object.entries(reunionsRaw)) {
    reunions[mode] = rows.map(r => Object.fromEntries(cols.map((c, i) => [c, r[i]])));
  }

  const db = {
    meta, theatres, shows, people, credits, reunions, basemap,
    theatreById, showById, personById,
    creditsByPerson: groupBy(credits, "person"),
    creditsByShow: groupBy(credits, "show"),
    showsByTheatre: groupBy(shows.filter(s => s.venue), "venue"),

    /** Theatre a show opened in, or undefined. */
    theatreOf(showId) {
      const s = showById.get(showId);
      return s && s.venue ? theatreById.get(s.venue) : undefined;
    },
    /** Was the theatre standing in this year? With no recorded opening date, the year its first
     *  show opened stands in; with no demolition date, it counts as still standing. */
    standing(t, year) {
      const opened = t.opened ?? t.first_show;
      return (opened == null || opened <= year) && (t.demolished == null || t.demolished >= year);
    },
    /** A person's credits in time order; mode "strict" | "loose" | "all". */
    career(personId, mode = "strict") {
      const rows = this.creditsByPerson.get(personId) || [];
      return rows.filter(c => mode === "all" || c[mode]).slice().sort((a, b) => a.year - b.year);
    },
  };
  return db;
}
