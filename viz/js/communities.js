// Communities per network window, in the format agreed with step 11 (mode, cutoff, community_id,
// person_id, strength). Views call communitiesFor(db, mode, cutoff) and never care where the rows
// come from.
//
// STAND-IN: until step 11's BigCLAM output is exported to viz/data, communities are computed here
// by weighted label propagation on the window's co-credit graph (edge weight = shows shared).
// To swap in the real thing: export the rows as db.communityRows (e.g. communities.json from
// step 13) and this module uses them instead. BigCLAM communities overlap; a person's entries
// are sorted by strength, strongest first.

const cache = new Map();

/** The window [cutoff-10, cutoff) that contains `year`, as its cutoff; null if none does. */
export function cutoffFor(db, year) {
  const w = db.meta.network.window_years;
  return db.meta.network.cutoffs.find(T => T - w <= year && year < T) ?? null;
}

/** { method, cutoff, byPerson: Map id -> [{ id, strength }], members: Map communityId -> [person ids] } */
export function communitiesFor(db, mode, cutoff) {
  const key = `${mode}|${cutoff}`;
  if (!cache.has(key)) cache.set(key, db.communityRows ? fromRows(db, mode, cutoff) : standIn(db, mode, cutoff));
  return cache.get(key);
}

function index(rows, method, cutoff) {
  const byPerson = new Map(), members = new Map();
  for (const r of rows) {
    if (!byPerson.has(r.person_id)) byPerson.set(r.person_id, []);
    byPerson.get(r.person_id).push({ id: r.community_id, strength: r.strength });
    if (!members.has(r.community_id)) members.set(r.community_id, []);
    members.get(r.community_id).push(r.person_id);
  }
  for (const list of byPerson.values()) list.sort((a, b) => b.strength - a.strength);
  return { method, cutoff, byPerson, members };
}

function fromRows(db, mode, cutoff) {
  return index(db.communityRows.filter(r => r.mode === mode && r.cutoff === cutoff), "bigclam", cutoff);
}

function standIn(db, mode, cutoff) {
  const from = cutoff - db.meta.network.window_years;
  // co-credit graph of the window, weighted by shows shared
  const byShow = new Map();
  for (const c of db.credits) {
    if (!c[mode] || c.year < from || c.year >= cutoff) continue;
    if (!byShow.has(c.show)) byShow.set(c.show, new Set());
    byShow.get(c.show).add(c.person);
  }
  const nb = new Map();
  const add = (a, b) => {
    if (!nb.has(a)) nb.set(a, new Map());
    nb.get(a).set(b, (nb.get(a).get(b) || 0) + 1);
  };
  for (const team of byShow.values()) {
    const t = [...team];
    for (const p of t) if (!nb.has(p)) nb.set(p, new Map());
    for (let i = 0; i < t.length; i++) for (let j = i + 1; j < t.length; j++) { add(t[i], t[j]); add(t[j], t[i]); }
  }
  // label propagation: each person takes the label with the most edge weight among neighbours;
  // ties keep the current label (so one shared person doesn't chain whole teams together),
  // otherwise the smallest label, so the result is deterministic
  const nodes = [...nb.keys()].sort();
  const label = new Map(nodes.map(n => [n, n]));
  for (let round = 0; round < 30; round++) {
    let changed = false;
    for (const n of nodes) {
      const tally = new Map();
      for (const [m, w] of nb.get(n)) tally.set(label.get(m), (tally.get(label.get(m)) || 0) + w);
      if (!tally.size) continue;
      const best = Math.max(...tally.values());
      const winners = [...tally].filter(([, w]) => w === best).map(([l]) => l).sort();
      const next = winners.includes(label.get(n)) ? label.get(n) : winners[0];
      if (next !== label.get(n)) { label.set(n, next); changed = true; }
    }
    if (!changed) break;
  }
  // number communities by size, largest first
  const groups = new Map();
  for (const [n, l] of label) {
    if (!groups.has(l)) groups.set(l, []);
    groups.get(l).push(n);
  }
  const ordered = [...groups.values()].sort((a, b) => b.length - a.length || (a[0] < b[0] ? -1 : 1));
  const rows = ordered.flatMap((list, i) => list.map(p => ({ mode, cutoff, community_id: i + 1, person_id: p, strength: 1 })));
  return index(rows, "stand-in", cutoff);
}
