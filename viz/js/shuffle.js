// Shuffle careers button (Chance tab): a browser version of step 10's null model
// (scripts/10_null_model.py), so each press deals a new, made-up Broadway for one network window.
//
// For cutoff T, the teams of the training window [T-10, T) and of the reunion window [T, T+10)
// are reshuffled separately. Within a window, a credit (one person on one show) only swaps with
// credits that have the same role set (e.g. "composer|lyricist"), so everyone keeps their number
// of credits and their roles, and every show keeps its team size and year. A person dealt twice
// onto the same show is swapped away. A pair "reunites" when two people who shared a training-
// window show also share a reunion-window show, the rule of step 08 and of the H1 numbers.

function shuffleInPlace(a) {
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

/** One window's credits as slots: person and show indexes, and the slots that may swap. */
function slots(credits, personIndex) {
  const showIds = [...new Set(credits.map(c => c.show))].sort();
  const showIndex = new Map(showIds.map((s, i) => [s, i]));
  const person = credits.map(c => personIndex.get(c.person));
  const show = credits.map(c => showIndex.get(c.show));
  const byRole = new Map();
  credits.forEach((c, r) => {
    const key = [...c.roles].sort().join("|");
    if (!byRole.has(key)) byRole.set(key, []);
    byRole.get(key).push(r);
  });
  const strata = [...byRole.values()];
  const stratumOf = new Array(credits.length);
  strata.forEach((g, k) => g.forEach(r => { stratumOf[r] = k; }));
  const members = showIds.map(() => []);
  show.forEach((s, r) => members[s].push(r));
  return { showIds, person, show, strata, stratumOf, members };
}

/** Swap away any person placed twice on the same show (team sizes must not shrink). */
function repair(p, w, n) {
  const key = (s, q) => s * n + q;
  const on = new Map();
  p.forEach((q, r) => {
    const k = key(w.show[r], q);
    if (!on.has(k)) on.set(k, []);
    on.get(k).push(r);
  });
  for (const k of [...on.keys()]) {
    while ((on.get(k)?.length ?? 0) > 1) {          // earlier swaps may have removed the key
      const s = Math.floor(k / n), person = k % n;
      let done = false;
      // move any duplicate slot that has a valid partner: a slot of the same roles whose person is
      // not on this show, on a show that doesn't already have this person
      for (const r of shuffleInPlace([...on.get(k)])) {
        const ok = w.strata[w.stratumOf[r]].filter(o =>
          w.show[o] !== s && !on.has(key(s, p[o])) && !on.has(key(w.show[o], person)));
        if (!ok.length) continue;
        const o = ok[Math.floor(Math.random() * ok.length)], q = p[o], ko = key(w.show[o], q);
        on.get(k).splice(on.get(k).indexOf(r), 1);
        on.get(ko).splice(on.get(ko).indexOf(o), 1);
        if (!on.get(ko).length) on.delete(ko);
        p[r] = q;
        p[o] = person;
        on.set(key(s, q), [r]);
        on.set(key(w.show[o], person), [o]);
        done = true;
        break;
      }
      if (!done) throw new Error("could not repair a shuffle");
    }
  }
  return p;
}

function dealt(w, n) {
  const p = w.person.slice();
  for (const g of w.strata) {
    const people = shuffleInPlace(g.map(r => p[r]));
    g.forEach((r, i) => { p[r] = people[i]; });
  }
  return repair(p, w, n);
}

/**
 * makeShuffler(db, mode, T) -> { real(), shuffle() }. Each returns
 *   { pairs, reunited, teams: Set of training-window show ids whose team had a reunion }
 * real() uses the actual careers and must equal the published count for the window.
 */
export function makeShuffler(db, mode, T, W = 10, H = 10) {
  const own = db.credits.filter(c => c[mode]);
  const train = own.filter(c => c.year >= T - W && c.year < T);
  const future = own.filter(c => c.year >= T && c.year < T + H);
  const people = [...new Set([...train, ...future].map(c => c.person))];
  const personIndex = new Map(people.map((p, i) => [p, i]));
  const n = people.length;
  const tw = slots(train, personIndex), fw = slots(future, personIndex);

  function evaluate(tp, fp) {
    const together = new Set();                 // pairs who share a reunion-window show
    for (const list of fw.members) {
      const ps = list.map(r => fp[r]);
      for (let i = 0; i < ps.length; i++) for (let j = i + 1; j < ps.length; j++) {
        const a = Math.min(ps[i], ps[j]), b = Math.max(ps[i], ps[j]);
        together.add(a * n + b);
      }
    }
    const pairs = new Set(), reunited = new Set(), teams = new Set();
    tw.members.forEach((list, s) => {
      const ps = list.map(r => tp[r]);
      for (let i = 0; i < ps.length; i++) for (let j = i + 1; j < ps.length; j++) {
        const a = Math.min(ps[i], ps[j]), b = Math.max(ps[i], ps[j]), code = a * n + b;
        pairs.add(code);
        if (together.has(code)) { reunited.add(code); teams.add(tw.showIds[s]); }
      }
    });
    return { pairs: pairs.size, reunited: reunited.size, teams };
  }

  return {
    real: () => evaluate(tw.person, fw.person),
    shuffle: () => evaluate(dealt(tw, n), dealt(fw, n)),
  };
}
