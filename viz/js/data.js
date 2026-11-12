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

/** Optional files: missing ones load as null, so the page works without them. */
async function fetchOptional(name) {
  try { return await fetchJson(name); } catch { return null; }
}

/** h1.json (scripts/10_null_model.py) stores compact rows; expand per mode, index shows by "cutoff|show". */
function expandH1(raw) {
  if (!raw) return null;
  const h1 = { alpha: raw.alpha, note: raw.note };
  for (const mode of ["strict", "loose"]) {
    const toObj = (cols, rows) => rows.map(r => Object.fromEntries(cols.map((c, i) => [c, r[i]])));
    const shows = toObj(raw.columns.shows, raw[mode].shows);
    h1[mode] = {
      shows: new Map(shows.map(s => [`${s.cutoff}|${s.show}`, s])),
      windows: toObj(raw.columns.windows, raw[mode].windows),
    };
  }
  return h1;
}

export async function loadData() {
  const [[meta, theatres, shows, people, credits, reunionsRaw, basemap], h1Raw] = await Promise.all([
    Promise.all(FILES.map(fetchJson)), fetchOptional("h1")]);
  const h1 = expandH1(h1Raw);

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
    meta, theatres, shows, people, credits, reunions, basemap, h1,
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
    /** Did this show's team (a show in [cutoff-10, cutoff)) reunite above chance? (H1 null model) */
    aboveChance(mode, cutoff, showId) {
      const s = h1 && h1[mode].shows.get(`${cutoff}|${showId}`);
      return !!s && s.p_value < h1.alpha;
    },
    /** Should a reunion row (from db.reunions[mode]) glow? True when the pair reunited and a show they
     *  shared in the training window reunited above chance. */
    glows(mode, row) {
      if (!row.reunion_shows) return false;
      const shared = new Set(this.career(row.person_a, mode)
        .filter(c => c.year >= row.cutoff - 10 && c.year < row.cutoff).map(c => c.show));
      return this.career(row.person_b, mode)
        .some(c => shared.has(c.show) && this.aboveChance(mode, row.cutoff, c.show));
    },
  };
  return db;
}
