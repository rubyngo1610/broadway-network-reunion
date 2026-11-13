// Cohort mode: everyone on a show that opened in the cohort year is a dot, clustered at that
// show's theatre. Playing the timeline moves each dot to the theatre of the person's latest show,
// so teams scatter; when two people from the same starting team work together again, both dots
// get a gold halo (a reunion). Dots are coloured by starting show or by community.
//
// URL: #cohort?from=1943&color=show|community&year=1950
import * as d3 from "https://cdn.jsdelivr.net/npm/d3@7.9.0/+esm";
import { esc, showTooltip, hideTooltip } from "../tooltip.js";
import { communitiesFor, cutoffFor } from "../communities.js";

const NETWORK = "strict";
const SLOTS = 7;          // categorical colours (css --cat-1..7); the rest are grey "other"
const DOT_R = 4;
const SPACING = 6.5;      // sunflower layout spacing around a theatre (screen px)
const IDLE_YEARS = 10;    // no new show for this long: the dot fades
const DEFAULT_FROM = 1943;
const REUNION_GAP = 5;    // same rule as Career mode: starting teammates back together after 5+ years apart

function buildCohort(db, from) {
  // the starting teams: shows that opened in `from`, largest team first
  const teams = d3.groups(db.credits.filter(c => c[NETWORK] && c.year === from), c => c.show)
    .map(([show, cs]) => ({ show, showObj: db.showById.get(show), theatre: db.theatreOf(show), people: [...new Set(cs.map(c => c.person))] }))
    .sort((a, b) => b.people.length - a.people.length || d3.ascending(a.showObj?.title, b.showObj?.title));
  teams.forEach((t, i) => { t.slot = i < SLOTS ? i : null; });

  const members = new Map();
  for (const t of teams) for (const p of t.people) {
    if (!members.has(p)) members.set(p, { id: p, person: db.personById.get(p), team: t, teams: [t], career: db.career(p, NETWORK) });
    else members.get(p).teams.push(t);
  }
  const mates = new Set();   // "a|b" for pairs who shared a starting show
  for (const t of teams) for (const a of t.people) for (const b of t.people) if (a < b) mates.add(`${a}|${b}`);

  // later shows with 2+ cohort members. For starting teammates on the show: a reunion if they had
  // been apart REUNION_GAP+ years, else they are still together; anyone else is a new pairing.
  const lastTogether = new Map([...mates].map(k => [k, from]));
  const later = d3.groups(db.credits.filter(c => c[NETWORK] && c.year > from && members.has(c.person)), c => c.show)
    .map(([show, cs]) => ({ show, year: cs[0].year, people: [...new Set(cs.map(c => c.person))].sort() }))
    .filter(e => e.people.length > 1);
  const events = [];
  // classify a year at a time, then record who worked together that year (a pair on two shows in
  // one year is compared with their last year together before it)
  for (const [, list] of d3.groups(later, e => e.year).sort((a, b) => a[0] - b[0])) {
    const seen = [];
    for (const e of list) {
      const reunited = new Set(), still = new Set();
      for (const a of e.people) for (const b of e.people) {
        const k = `${a}|${b}`;
        if (a >= b || !mates.has(k)) continue;
        (e.year - lastTogether.get(k) >= REUNION_GAP ? reunited : still).add(a).add(b);
        seen.push(k);
      }
      events.push({ ...e, showObj: db.showById.get(e.show), theatre: db.theatreOf(e.show), reunited: [...reunited], still: [...still],
        reunion: reunited.size > 0, kind: reunited.size ? "reunion" : still.size ? "still together" : "new pairing" });
    }
    for (const k of seen) lastTogether.set(k, list[0].year);
  }
  events.sort((a, b) => a.year - b.year || b.reunion - a.reunion);
  const reunionShows = new Set(events.filter(e => e.reunion).map(e => e.show));
  const end = d3.max([...members.values()], m => d3.max(m.career, c => c.year)) ?? from;
  return { from, teams, members: [...members.values()], events, reunionShows, end };
}

export function cohortMode() {
  let root = null, pen = null, labelG = null, offZoom = null, ctxRef = null;
  let cohort = null, from = null, colorBy = "show", year = null, focus = null;
  let comm = null;   // { cutoff, method, slotOf: Map communityId -> slot, ranked: [{ id, members }] }

  // --- state at a year --------------------------------------------------------------------------

  /** The member's latest show by year y (preferring a reunion show, then one with a known theatre). */
  function lastShow(m, y) {
    const done = m.career.filter(c => c.year <= y);
    if (!done.length) return null;
    const ly = done[done.length - 1].year;
    const same = done.filter(c => c.year === ly);
    return same.find(c => cohort.reunionShows.has(c.show)) ?? same.find(c => ctxRef.db.theatreOf(c.show)) ?? same[0];
  }

  function statusAt(m, y) {
    const c = lastShow(m, y);
    const theatre = c ? ctxRef.db.theatreOf(c.show) : null;
    const died = m.person?.died;
    const faded = !c || y - c.year > IDLE_YEARS || (died != null && died < y);
    return { credit: c, theatre, working: c?.year === y, faded };
  }

  function colourSlot(m) {
    if (colorBy === "community") {
      const cid = comm?.byPerson.get(m.id)?.[0]?.id;
      const slot = comm?.slotOf.get(cid);
      return slot ?? null;
    }
    return m.team.slot;
  }

  // --- map --------------------------------------------------------------------------------------

  /** Screen positions: dots sharing a theatre are laid out in a sunflower around it. */
  function positions() {
    const { map } = ctxRef;
    const groups = d3.groups(cohort.members, m => m.st.theatre?.id ?? "pen");
    const pos = new Map();
    for (const [key, list] of groups) {
      list.sort((a, b) => (a.st.faded - b.st.faded) || ((colourSlot(a) ?? 99) - (colourSlot(b) ?? 99)) || d3.ascending(a.id, b.id));
      if (key === "pen") {
        list.forEach((m, i) => pos.set(m.id, [26 + (i % 12) * 10, map.height - 40 - Math.floor(i / 12) * 10]));
        continue;
      }
      const [x, y] = map.xy(list[0].st.theatre.lat, list[0].st.theatre.lon);
      list.forEach((m, i) => {
        const r = SPACING * Math.sqrt(i), a = i * 2.39996;   // golden angle
        pos.set(m.id, [x + r * Math.cos(a), y + r * Math.sin(a)]);
      });
    }
    return pos;
  }

  function place(animate = false) {
    if (!root || !cohort) return;
    const pos = positions();
    const sel = root.selectAll("circle.cdot");
    const target = animate ? sel.transition("move").duration(550).ease(d3.easeCubicInOut) : sel;
    target.attr("cx", m => pos.get(m.id)[0]).attr("cy", m => pos.get(m.id)[1]);
    const halo = root.selectAll("circle.chalo");
    (animate ? halo.transition("move").duration(550).ease(d3.easeCubicInOut) : halo)
      .attr("cx", m => pos.get(m.id)[0]).attr("cy", m => pos.get(m.id)[1]);
    const inPen = cohort.members.filter(m => !m.st.theatre).length;
    pen.attr("display", inPen ? null : "none")
      .select("text").attr("x", 21).attr("y", ctxRef.map.height - 52 - Math.floor((inPen - 1) / 12) * 10);
    placeLabels();
  }

  function placeLabels() {
    labelG.selectAll("text").attr("x", d => ctxRef.map.xy(d.theatre.lat, d.theatre.lon)[0])
      .attr("y", d => ctxRef.map.xy(d.theatre.lat, d.theatre.lon)[1] - 14);
  }

  function update(y, animate = true) {
    year = y;
    for (const m of cohort.members) m.st = statusAt(m, y);
    const nowReunited = new Set(cohort.events.filter(e => e.year === y && e.reunion).flatMap(e => e.reunited));
    root.selectAll("circle.cdot")
      .attr("class", m => `cdot ${slotClass(m)}${m.st.working ? " working" : ""}${m.st.faded ? " faded" : ""}${focus && !focus(m) ? " dim" : ""}`);
    root.selectAll("circle.chalo").classed("on", m => nowReunited.has(m.id));
    // labels: the starting shows in the cohort year, reunion shows afterwards
    const labels = y === from
      ? cohort.teams.filter(t => t.theatre).map(t => ({ key: t.show, theatre: t.theatre, text: t.showObj?.title ?? "", kind: "start" }))
      : cohort.events.filter(e => e.year === y && e.reunion && e.theatre).map(e => ({ key: e.show, theatre: e.theatre, text: `Reunion: ${e.showObj?.title ?? ""}`, kind: "reunion" }));
    labelG.selectAll("text").data(labels, d => d.key).join("text")
      .attr("class", d => `cohort-label ${d.kind}`).attr("text-anchor", "middle").text(d => d.text);
    place(animate);
    updatePanelYear();
  }

  const slotClass = m => { const s = colourSlot(m); return s == null ? "kother" : `k${s}`; };

  function tipHtml(m) {
    const c = m.st.credit, s = c && ctxRef.db.showById.get(c.show);
    const cid = comm?.byPerson.get(m.id)?.[0]?.id;
    return `<div class="t-title">${esc(m.person?.name ?? m.id)}</div>
      <div class="t-sub">started on <em>${esc(m.team.showObj?.title)}</em> (${from})</div>
      ${c && c.year > from ? `<div>${c.year === year ? "now" : `last, ${c.year}`}: <em>${esc(s?.title)}</em>${m.st.theatre ? ` · ${esc(m.st.theatre.name)}` : ""}</div>` : ""}
      ${cid != null ? `<div class="t-sub">${comm.method === "stand-in" ? "stand-in " : ""}community ${cid}</div>` : ""}
      ${m.st.faded ? `<div class="t-sub">${m.person?.died != null && m.person.died < year ? `died ${m.person.died}` : `no new show since ${c?.year ?? from}`}</div>` : ""}`;
  }

  // --- panel ------------------------------------------------------------------------------------

  function legendRows() {
    if (colorBy === "community") {
      if (!comm) return `<p class="hint">No network window contains ${from} (windows run ${ctxRef.db.meta.network.cutoffs[0] - 10}–${ctxRef.db.meta.network.cutoffs.at(-1) - 1}), so there are no communities for this cohort.</p>`;
      const nameOf = id => ctxRef.db.personById.get(id)?.name ?? id;
      const rows = comm.ranked.slice(0, SLOTS).map((c, i) => {
        const inCohort = cohort.members.filter(m => comm.byPerson.get(m.id)?.[0]?.id === c.id);
        return `<li data-key="c${c.id}"><span class="swatch k${i}"></span><div><strong>Community ${c.id}</strong> <span class="roles">${c.size} people in ${comm.cutoff - 10}–${comm.cutoff - 1}</span>
          <div class="where">${inCohort.slice(0, 4).map(m => esc(nameOf(m.id))).join(", ")}${inCohort.length > 4 ? ` and ${inCohort.length - 4} more` : ""}</div></div></li>`;
      });
      const rest = cohort.members.filter(m => colourSlot(m) == null).length;
      if (rest) rows.push(`<li data-key="cother"><span class="swatch kother"></span><div>other communities <span class="roles">${rest} people</span></div></li>`);
      return `<ul class="cohort-legend">${rows.join("")}</ul>`;
    }
    const rows = cohort.teams.filter(t => t.slot != null).map(t => `<li data-key="s${t.show}"><span class="swatch k${t.slot}"></span><div><strong>${esc(t.showObj?.title)}</strong>
      <span class="roles">${t.people.length} people</span><div class="where">${t.theatre ? esc(t.theatre.name) : "theatre unknown"}</div></div></li>`);
    const others = cohort.teams.filter(t => t.slot == null);
    if (others.length) rows.push(`<li data-key="sother"><span class="swatch kother"></span><div>${others.length} other show${others.length === 1 ? "" : "s"}
      <span class="roles">${d3.sum(others, t => t.people.length)} people</span><div class="where">${others.map(t => esc(t.showObj?.title)).join(", ")}</div></div></li>`);
    return `<ul class="cohort-legend">${rows.join("")}</ul>`;
  }

  function fillPanel() {
    const { db, panel } = ctxRef;
    const nameOf = id => db.personById.get(id)?.name ?? id;
    const nRe = cohort.events.filter(e => e.reunion).length;
    panel.innerHTML = `
      <h2>The class of ${from}</h2>
      <p class="sub">Everyone on a show that opened in ${from}: ${cohort.members.length} people on ${cohort.teams.length} shows.
        Press play to follow them. Each dot moves to the theatre of the person's latest show; a gold halo marks a reunion:
        people from the same starting team back together after ${REUNION_GAP}+ years apart.</p>
      <div class="cohort-controls">
        <label>Cohort year
          <button type="button" class="btn step" data-step="-1" aria-label="Previous year">◀</button>
          <input type="number" class="from" min="${ctxRef.years[0]}" max="${ctxRef.years[1]}" value="${from}">
          <button type="button" class="btn step" data-step="1" aria-label="Next year">▶</button>
        </label>
        <div class="seg" role="group" aria-label="Colour dots by">
          <button type="button" data-color="show" aria-pressed="${colorBy === "show"}">Starting show</button>
          <button type="button" data-color="community" aria-pressed="${colorBy === "community"}">Community</button>
        </div>
      </div>
      ${colorBy === "community" && comm ? `<p class="hint">${comm.method === "stand-in"
        ? `Stand-in communities (label propagation on the ${comm.cutoff - 10}–${comm.cutoff - 1} network) until step 11's BigCLAM output is exported.`
        : `BigCLAM communities, ${comm.cutoff - 10}–${comm.cutoff - 1} network.`}</p>` : ""}
      ${legendRows()}
      <p class="cohort-now"></p>
      <div class="legend">
        <span><span class="key dot-working"></span>has a show this year</span>
        <span><span class="key dot-idle"></span>at their latest show's theatre</span>
        <span><span class="key dot-halo"></span>reunion this year</span>
      </div>
      <h3 class="list-title">Working together again (${nRe} reunion${nRe === 1 ? "" : "s"})</h3>
      <ol class="event-list">
        ${cohort.events.map(e => `<li data-year="${e.year}" class="${e.reunion ? "reunion" : ""}">
          <span class="yr">${e.year}</span>
          <div><strong>${esc(e.showObj?.title ?? e.show)}</strong> <span class="roles">${e.kind}</span>
            <div class="where">${e.people.map(id => `${e.reunited.includes(id) ? "<b>" : ""}${esc(nameOf(id))}${e.reunited.includes(id) ? "</b>" : ""}`).join(", ")}</div>
          </div></li>`).join("") || `<li class="none">No two members of this cohort worked together again in our data.</li>`}
      </ol>`;

    const goFrom = f => { location.hash = `#cohort?from=${f}&color=${colorBy}`; };
    panel.querySelectorAll("button.step").forEach(b => b.addEventListener("click", () => goFrom(from + +b.dataset.step)));
    panel.querySelector("input.from").addEventListener("change", ev => { if (+ev.target.value) goFrom(+ev.target.value); });
    panel.querySelectorAll(".seg button").forEach(b => b.addEventListener("click", () => {
      if (b.dataset.color !== colorBy) location.hash = `#cohort?from=${from}&color=${b.dataset.color}&year=${year}`;
    }));
    panel.querySelectorAll(".event-list li[data-year]").forEach(li => li.addEventListener("click", () => ctxRef.setYear(+li.dataset.year)));
    panel.querySelectorAll(".cohort-legend li").forEach(li => {
      const key = li.dataset.key;
      const test = key === "sother" || key === "cother" ? m => colourSlot(m) == null
        : key[0] === "s" ? m => m.teams.some(t => t.show === key.slice(1))
        : m => comm?.byPerson.get(m.id)?.[0]?.id === +key.slice(1);
      li.addEventListener("pointerenter", () => { focus = test; update(year, false); });
      li.addEventListener("pointerleave", () => { focus = null; update(year, false); });
    });
  }

  function updatePanelYear() {
    const panel = ctxRef.panel;
    const working = cohort.members.filter(m => m.st.working).length;
    const scattered = new Set(cohort.members.filter(m => !m.st.faded && m.st.theatre).map(m => m.st.theatre.id)).size;
    const reunionsSoFar = cohort.events.filter(e => e.reunion && e.year <= year).length;
    const now = panel.querySelector(".cohort-now");
    if (now) now.innerHTML = year === from
      ? `In <strong>${year}</strong>: ${cohort.members.length} people at ${new Set(cohort.teams.filter(t => t.theatre).map(t => t.theatre.id)).size} theatres.`
      : `In <strong>${year}</strong>: ${working} of ${cohort.members.length} have a show this year · the cohort is spread over ${scattered} theatre${scattered === 1 ? "" : "s"} · ${reunionsSoFar} reunion${reunionsSoFar === 1 ? "" : "s"} so far.`;
    panel.querySelectorAll(".event-list li[data-year]").forEach(li => {
      li.classList.toggle("future", +li.dataset.year > year);
      li.classList.toggle("current", +li.dataset.year === year);
    });
  }

  // --- building ---------------------------------------------------------------------------------

  function setupCommunities() {
    const cutoff = cutoffFor(ctxRef.db, from);
    if (cutoff == null) { comm = null; return; }
    const c = communitiesFor(ctxRef.db, NETWORK, cutoff);
    // colour the communities with the most cohort members
    const counts = d3.rollup(cohort.members, v => v.length, m => c.byPerson.get(m.id)?.[0]?.id);
    const ranked = [...counts].filter(([id]) => id != null).sort((a, b) => b[1] - a[1] || a[0] - b[0])
      .map(([id]) => ({ id, size: c.members.get(id).length }));
    comm = { ...c, ranked, slotOf: new Map(ranked.slice(0, SLOTS).map((r, i) => [r.id, i])) };
  }

  function build(ctx, { yearFromUrl } = {}) {
    cohort = buildCohort(ctx.db, from);
    setupCommunities();
    root.selectAll("*").remove();
    labelG.selectAll("*").remove();
    root.selectAll("circle.chalo").data(cohort.members, m => m.id).join("circle").attr("class", "chalo").attr("r", DOT_R + 4);
    root.selectAll("circle.cdot").data(cohort.members, m => m.id).join("circle").attr("class", "cdot").attr("r", DOT_R)
      .on("pointermove", (ev, m) => showTooltip(ev, tipHtml(m)))
      .on("pointerleave", hideTooltip)
      .on("click", (ev, m) => { location.hash = `#career?p=${m.id}`; });
    fillPanel();
    ctx.setRange([from, Math.max(from, cohort.end)]);
    const y = yearFromUrl && yearFromUrl >= from && yearFromUrl <= cohort.end ? yearFromUrl : from;
    for (const m of cohort.members) m.st = statusAt(m, y);
    // start every dot at its starting theatre, then zoom to the cohort
    update(y, false);
    ctx.setYear(y);
    const pts = cohort.teams.filter(t => t.theatre).map(t => [t.theatre.lat, t.theatre.lon]);
    if (pts.length) ctx.map.zoomTo(pts, { pad: 160, duration: 900 });
  }

  return {
    id: "cohort", label: "Cohort", caption: "teams scatter and reunite", usesYear: true,

    enter(ctx) {
      ctxRef = ctx;
      const p = ctx.state.params;
      // a link's cohort year, else the last cohort, else the year the timeline is on
      from = +p.get("from") || from || ctx.state.year || DEFAULT_FROM;
      colorBy = p.get("color") === "community" ? "community" : "show";
      ctx.theatres.dots.attr("class", "t theatre faint").transition("mode").duration(500).attr("r", 3).attr("opacity", 0.3);
      pen = ctx.map.layer("overlay").append("g").attr("class", "cohort-pen");
      pen.append("text").text("theatre unknown");
      root = ctx.map.layer("overlay").append("g").attr("class", "mode-cohort");
      labelG = ctx.map.layer("top").append("g").attr("class", "cohort-labels");
      offZoom = ctx.map.onZoom(() => place(false));
      build(ctx, { yearFromUrl: +p.get("year") });
    },

    onParams(ctx) {
      const p = ctx.state.params;
      const nextFrom = +p.get("from") || from;
      const nextColor = p.get("color") === "community" ? "community" : "show";
      if (nextFrom !== from) { from = nextFrom; colorBy = nextColor; build(ctx, { yearFromUrl: +p.get("year") }); return; }
      if (nextColor !== colorBy) { colorBy = nextColor; fillPanel(); }
      update(ctx.state.year, false);
    },

    setYear(ctx, y) { if (cohort && y !== year) update(y, true); },

    exit() {
      offZoom?.();
      for (const g of [root, pen, labelG]) g?.transition().duration(250).attr("opacity", 0).remove();
      root = pen = labelG = null;
      cohort = null;
      year = null;
    },

    params: () => ({ from, color: colorBy }),
    tip: t => `<div class="t-title">${esc(t.name)}</div>`,
  };
}
