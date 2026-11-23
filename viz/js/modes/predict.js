// Predict mode (H3): which pairs will work together again? Step 15 scores every pair who shared a
// show in a training window [T-10, T) using only that window, and checks whether they share a show
// again in [T, T+10). This view picks one score, ranks the window's pairs by it and shows:
//   - AUC per score for this window and pooled (how often a reunited pair outranks one that didn't)
//   - reunion rate by score level over all windows (does a higher score mean more reunions?)
//   - the top-ranked pairs, hit or miss, and the reunited pairs the score ranked lowest
// On the map, each top pair is a mark at the theatre of their last shared training show; when they
// reunited, a gold arc runs to the theatre of their first show together again.
//
// Data: db.models (viz/data/models.json, scripts/17_export_model_viz.py).
// URL: #predict?score=bigclam&year=1955
import * as d3 from "https://cdn.jsdelivr.net/npm/d3@7.9.0/+esm";
import { esc, showTooltip, hideTooltip } from "../tooltip.js";
import { cutoffFor } from "../communities.js";

const NETWORK = "strict";
const TOP = 20, MISSED = 6;
const SCORE_INFO = {
  shows_together:   { label: "Shows together", fmt: d3.format("d"),
    text: "Shows the pair did together in the window. The simple heuristic every model has to beat. Most pairs did one show, so it can't rank them." },
  activity:         { label: "Both still working", fmt: d3.format("d"),
    text: "The smaller of the two people's show counts in the window: are both still active? The strongest single signal." },
  bigclam:          { label: "BigCLAM", fmt: d3.format(".2f"),
    text: "F_a · F_b from BigCLAM (step 11): how strongly the two share learned communities. H3 asked whether this beats shows together." },
  weighted:         { label: "Weighted BigCLAM", fmt: d3.format(".3f"),
    text: "The same with links weighted by team size (a duo's show counts more than a revue's). Exploratory, after H3." },
  common_neighbors: { label: "Common collaborators", fmt: d3.format("d"),
    text: "People both of them worked with in the window. A classic link-prediction baseline." },
};
const pct = v => `${(100 * v).toFixed(v < 0.1 ? 1 : 0)}%`;

export function predictMode() {
  let root = null, offZoom = null, ctxRef = null, cutoff = null, score = "bigclam";
  let ranked = [], top = [], missed = [];

  const nameOf = id => ctxRef.db.personById.get(id)?.name ?? id;
  const short = id => { const p = nameOf(id).replace(/,/g, "").split(" "); while (p.length > 1 && /^(II|III|IV|Jr\.?|Sr\.?)$/i.test(p.at(-1))) p.pop(); return p.at(-1); };

  /** Shows the two shared, from their credits: last in the training window, first in the outcome window. */
  function sharedShows(a, b) {
    const { db } = ctxRef;
    const mine = new Set(db.career(a, NETWORK).map(c => c.show));
    const both = db.career(b, NETWORK).filter(c => mine.has(c.show));
    const before = both.filter(c => c.year >= cutoff - 10 && c.year < cutoff);
    const after = both.filter(c => c.year >= cutoff && c.year < cutoff + 10);
    const pick = c => c && { show: db.showById.get(c.show), year: c.year, theatre: db.theatreOf(c.show) };
    return { met: pick(before.at(-1)), again: pick(after.find(c => db.theatreOf(c.show)) ?? after[0]), total: both.length };
  }

  // --- ranking ---------------------------------------------------------------------------------

  function rank() {
    const rows = ctxRef.db.models.pairs.filter(p => p.cutoff === cutoff);
    // ties broken by pair id, so the order is stable; ties are reported in the panel
    ranked = [...rows].sort((p, q) => q[score] - p[score] || d3.ascending(p.person_a + p.person_b, q.person_a + q.person_b));
    ranked.forEach((p, i) => { p.rank = i + 1; });
    top = ranked.slice(0, TOP).map(p => ({ ...p, ...sharedShows(p.person_a, p.person_b) }));
    missed = ranked.filter(p => p.reunion_shows > 0).slice(-MISSED).reverse().map(p => ({ ...p, ...sharedShows(p.person_a, p.person_b) }));
  }

  // --- map -------------------------------------------------------------------------------------

  function place() {
    if (!root) return;
    const xy = t => ctxRef.map.xy(t.lat, t.lon);
    // pairs meeting at the same theatre fan out around it
    const seat = new Map();
    const at = d => {
      const k = d.met.theatre.id, i = seat.get(k) ?? 0;
      seat.set(k, i + 1);
      const [x, y] = xy(d.met.theatre), r = 7 * Math.sqrt(i), a = i * 2.39996;
      return [x + r * Math.cos(a), y + r * Math.sin(a)];
    };
    const pos = new Map(top.filter(d => d.met?.theatre).map(d => [d, at(d)]));
    root.selectAll("path.arc").attr("d", d => {
      const [x0, y0] = pos.get(d), [x1, y1] = xy(d.again.theatre);
      const dx = x1 - x0, dy = y1 - y0, bend = 0.3;
      return `M${x0},${y0} Q${(x0 + x1) / 2 - dy * bend},${(y0 + y1) / 2 + dx * bend} ${x1},${y1}`;
    });
    root.selectAll("circle.pmark").attr("cx", d => pos.get(d)[0]).attr("cy", d => pos.get(d)[1]);
    root.selectAll("circle.pend").attr("cx", d => xy(d.again.theatre)[0]).attr("cy", d => xy(d.again.theatre)[1]);
  }

  function drawMap() {
    root.selectAll("*").remove();
    const onMap = top.filter(d => d.met?.theatre);
    const hits = onMap.filter(d => d.reunion_shows > 0 && d.again?.theatre);
    root.selectAll("path.arc").data(hits).join("path").attr("class", "arc");
    root.selectAll("circle.pend").data(hits).join("circle").attr("class", "pend").attr("r", 3.5);
    root.selectAll("circle.pmark").data(onMap).join("circle")
      .attr("class", d => `pmark ${d.reunion_shows > 0 ? "hit" : "miss"}`).attr("r", 5.5)
      .on("pointerenter", (ev, d) => highlight(d))
      .on("pointermove", (ev, d) => showTooltip(ev, pairTip(d)))
      .on("pointerleave", () => { highlight(null); hideTooltip(); })
      .on("click", (ev, d) => openCareers(d));
    place();
    root.selectAll("path.arc").each(function () {
      const len = this.getTotalLength();
      d3.select(this).attr("stroke-dasharray", `${len} ${len}`).attr("stroke-dashoffset", len)
        .transition().duration(900).delay(200).attr("stroke-dashoffset", 0)
        .on("end", function () { d3.select(this).attr("stroke-dasharray", null); });
    });
  }

  function highlight(d) {
    const key = d && d.person_a + d.person_b;
    root?.selectAll("circle.pmark, path.arc").classed("active", x => key && x.person_a + x.person_b === key)
      .classed("dim", x => key && x.person_a + x.person_b !== key);
    ctxRef.panel.querySelectorAll(".pair-list li").forEach(li => li.classList.toggle("active", li.dataset.key === key));
  }

  function openCareers(d) {
    // the career view compares people who did 2+ shows together; otherwise open the first person
    location.hash = d.total >= 2 ? `#career?p=${d.person_a},${d.person_b}` : `#career?p=${d.person_a}`;
  }

  function pairTip(d) {
    const info = SCORE_INFO[score];
    return `<div class="t-title">${esc(nameOf(d.person_a))} & ${esc(nameOf(d.person_b))}</div>
      <div class="t-sub">rank ${d.rank} of ${ranked.length} by ${esc(info.label.toLowerCase())} (${info.fmt(d[score])})</div>
      ${d.met ? `<div>last together: <em>${esc(d.met.show?.title)}</em> (${d.met.year})${d.met.theatre ? ` · ${esc(d.met.theatre.name)}` : ""}</div>` : ""}
      <div>${d.reunion_shows > 0
        ? `<strong>worked together again</strong>${d.again ? `: <em>${esc(d.again.show?.title)}</em> (${d.again.year})${d.again.theatre ? ` · ${esc(d.again.theatre.name)}` : ""}` : ""}`
        : `no show together in ${cutoff}–${cutoff + 9}`}</div>`;
  }

  // --- panel -----------------------------------------------------------------------------------

  /** AUC per score: bars for this window, a tick for all windows pooled, a rule at 0.5 (chance). */
  function drawAuc(el) {
    const m = ctxRef.db.models;
    const w = m.auc.windows.find(d => d.cutoff === cutoff);
    const rows = m.scores.map(k => ({ k, win: w?.[k], pooled: m.auc.pooled[k] }));
    const W = el.clientWidth || 320, rowH = 24, mg = { t: 18, r: 44, b: 22, l: 132 };
    const H = mg.t + rows.length * rowH + mg.b;
    const x = d3.scaleLinear().domain([0.3, 0.8]).range([mg.l, W - mg.r]).clamp(true);
    const y = d3.scaleBand().domain(rows.map(r => r.k)).range([mg.t, H - mg.b]).padding(0.3);
    const svg = d3.select(el).html("").append("svg").attr("class", "chart auc-chart").attr("width", W).attr("height", H)
      .attr("role", "img").attr("aria-label", "AUC per score");
    svg.append("g").attr("class", "grid").selectAll("line").data([0.4, 0.6, 0.7]).join("line")
      .attr("x1", x).attr("x2", x).attr("y1", mg.t - 4).attr("y2", H - mg.b);
    svg.append("g").attr("class", "axis").attr("transform", `translate(0,${H - mg.b})`)
      .call(d3.axisBottom(x).tickValues([0.4, 0.5, 0.6, 0.7]).tickSize(0).tickPadding(6)).call(g => g.select(".domain").remove());
    svg.append("line").attr("class", "chance-rule").attr("x1", x(0.5)).attr("x2", x(0.5)).attr("y1", mg.t - 8).attr("y2", H - mg.b);
    svg.append("text").attr("class", "series-label muted").attr("x", x(0.5)).attr("y", mg.t - 10).attr("text-anchor", "middle").text("chance");
    const g = svg.append("g").selectAll("g").data(rows).join("g").attr("class", d => `auc-row${d.k === score ? " sel" : ""}`)
      .attr("transform", d => `translate(0,${y(d.k)})`);
    g.append("text").attr("class", "row-label").attr("x", mg.l - 8).attr("y", y.bandwidth() / 2).attr("dy", "0.35em")
      .attr("text-anchor", "end").text(d => SCORE_INFO[d.k].label);
    // bar from 0.5 to the window's AUC, so below-chance scores point left
    g.append("rect").attr("class", "auc-bar").attr("y", 0).attr("height", y.bandwidth()).attr("rx", 2)
      .attr("x", d => x(Math.min(0.5, d.win ?? 0.5))).attr("width", d => Math.abs(x(d.win ?? 0.5) - x(0.5)));
    g.append("line").attr("class", "pooled-tick").attr("x1", d => x(d.pooled)).attr("x2", d => x(d.pooled))
      .attr("y1", -3).attr("y2", y.bandwidth() + 3);
    g.append("text").attr("class", "auc-val").attr("x", W - mg.r + 6).attr("y", y.bandwidth() / 2).attr("dy", "0.35em")
      .text(d => (d.win == null ? "–" : d.win.toFixed(2)));
    g.append("rect").attr("class", "hit").attr("x", 0).attr("width", W).attr("y", -3).attr("height", y.bandwidth() + 6)
      .on("pointermove", (ev, d) => showTooltip(ev, `<div class="t-title">${esc(SCORE_INFO[d.k].label)}</div>
        <div>AUC in ${cutoff - 10}–${cutoff - 1}: <strong>${d.win?.toFixed(3) ?? "–"}</strong></div>
        <div>all windows pooled: ${d.pooled.toFixed(3)}</div>
        <div class="t-sub">${esc(SCORE_INFO[d.k].text)}</div>`))
      .on("pointerleave", hideTooltip)
      .on("click", (ev, d) => setScore(d.k));
  }

  /** Reunion rate by score level, all windows: distinct values when few, else five equal groups. */
  function drawLevels(el) {
    const pairs = ctxRef.db.models.pairs;
    const vals = [...new Set(pairs.map(p => p[score]))].sort(d3.ascending);
    let bins;
    if (vals.length <= 6) {
      bins = vals.map(v => ({ label: SCORE_INFO[score].fmt(v), list: pairs.filter(p => p[score] === v) }));
    } else {
      const sorted = [...pairs].sort((a, b) => a[score] - b[score]);
      const q = 5;
      bins = d3.range(q).map(i => ({ label: ["lowest", "low", "middle", "high", "highest"][i], list: sorted.slice(Math.floor(i * sorted.length / q), Math.floor((i + 1) * sorted.length / q)) }));
    }
    // merge tiny groups at the top so every bar has enough pairs to mean something
    while (bins.length > 1 && bins.at(-1).list.length < 30) { const last = bins.pop(); bins.at(-1).list.push(...last.list); bins.at(-1).label += "+"; }
    for (const b of bins) { b.n = b.list.length; b.rate = d3.mean(b.list, p => +(p.reunion_shows > 0)); }
    const W = el.clientWidth || 320, H = 150, mg = { t: 16, r: 8, b: 34, l: 38 };
    const x = d3.scaleBand().domain(bins.map(b => b.label)).range([mg.l, W - mg.r]).padding(0.25);
    const y = d3.scaleLinear().domain([0, Math.max(0.1, d3.max(bins, b => b.rate))]).nice().range([H - mg.b, mg.t]);
    const svg = d3.select(el).html("").append("svg").attr("class", "chart level-chart").attr("width", W).attr("height", H)
      .attr("role", "img").attr("aria-label", "Share of pairs who reunited, by score level");
    svg.append("g").attr("class", "grid").selectAll("line").data(y.ticks(3)).join("line").attr("x1", mg.l).attr("x2", W - mg.r).attr("y1", y).attr("y2", y);
    svg.append("g").attr("class", "axis").attr("transform", `translate(${mg.l},0)`)
      .call(d3.axisLeft(y).ticks(3).tickFormat(d3.format(".0%")).tickSize(0).tickPadding(6)).call(g => g.select(".domain").remove());
    svg.append("g").attr("class", "axis").attr("transform", `translate(0,${H - mg.b})`)
      .call(d3.axisBottom(x).tickSize(0).tickPadding(6)).call(g => g.select(".domain").remove());
    svg.append("text").attr("class", "series-label muted").attr("x", (mg.l + W - mg.r) / 2).attr("y", H - 4).attr("text-anchor", "middle")
      .text(vals.length <= 6 ? SCORE_INFO[score].label.toLowerCase() : `${SCORE_INFO[score].label} score, five equal groups of pairs`);
    svg.append("g").selectAll("path").data(bins).join("path").attr("class", "level-bar")
      .attr("d", b => { const x0 = x(b.label), w = x.bandwidth(), y0 = y(0), y1 = y(b.rate), r = Math.min(4, (y0 - y1) / 2);
        return `M${x0},${y0}V${y1 + r}Q${x0},${y1} ${x0 + r},${y1}H${x0 + w - r}Q${x0 + w},${y1} ${x0 + w},${y1 + r}V${y0}Z`; });
    svg.append("g").selectAll("rect").data(bins).join("rect").attr("class", "hit")
      .attr("x", b => x(b.label)).attr("width", x.bandwidth()).attr("y", mg.t).attr("height", H - mg.t - mg.b)
      .on("pointermove", (ev, b) => showTooltip(ev, `<div class="t-title">${esc(b.label)}</div>
        <div><strong>${pct(b.rate)}</strong> of ${b.n.toLocaleString()} pairs worked together again</div>`))
      .on("pointerleave", hideTooltip);
  }

  // --- pair, not team ----------------------------------------------------------------------------
  // The pair's team size is the smallest team among the shows they shared in the training window
  // (team = everyone credited on the show in this network mode). Bands as in step 16.

  const BANDS = [["2–3", 2, 3], ["4–5", 4, 5], ["6–8", 6, 8], ["9+", 9, Infinity]];
  let teamCache = null;
  function withTeams() {
    if (teamCache) return teamCache;
    const { db } = ctxRef;
    const size = new Map();
    for (const [show, rows] of db.creditsByShow) size.set(show, new Set(rows.filter(r => r[NETWORK]).map(r => r.person)).size);
    const showsIn = (p, T) => new Set(db.career(p, NETWORK).filter(c => c.year >= T - 10 && c.year < T).map(c => c.show));
    teamCache = db.models.pairs.map(p => {
      const a = showsIn(p.person_a, p.cutoff);
      const shared = db.career(p.person_b, NETWORK).filter(c => a.has(c.show) && c.year >= p.cutoff - 10 && c.year < p.cutoff);
      const team = d3.min(shared, c => size.get(c.show)) ?? 2;
      return { p, team, band: BANDS.findIndex(([, lo, hi]) => team >= lo && team <= hi) };
    });
    return teamCache;
  }

  /** Two small charts on the same team-size bands: the score's average (left) and the share of pairs
   *  who reunited (right). Separate y axes, so each reads on its own scale. */
  function drawTeamSize(el) {
    const rows = withTeams();
    const by = BANDS.map(([label], i) => {
      const list = rows.filter(r => r.band === i);
      return { label, n: list.length, score: d3.mean(list, r => r.p[score]), rate: d3.mean(list, r => +(r.p.reunion_shows > 0)) };
    });
    const W = el.clientWidth || 320, gap = 18, w = (W - gap) / 2, H = 150, mg = { t: 22, r: 4, b: 30, l: 34 };
    const svg = d3.select(el).html("").append("svg").attr("class", "chart team-chart").attr("width", W).attr("height", H)
      .attr("role", "img").attr("aria-label", "Average score and reunion rate by team size");
    const panelChart = (x0, key, title, fmt, cls) => {
      const g = svg.append("g").attr("transform", `translate(${x0},0)`);
      const x = d3.scaleBand().domain(by.map(b => b.label)).range([mg.l, w - mg.r]).padding(0.25);
      const y = d3.scaleLinear().domain([0, d3.max(by, b => b[key]) || 1]).nice().range([H - mg.b, mg.t]);
      g.append("g").attr("class", "grid").selectAll("line").data(y.ticks(3)).join("line").attr("x1", mg.l).attr("x2", w - mg.r).attr("y1", y).attr("y2", y);
      g.append("g").attr("class", "axis").attr("transform", `translate(${mg.l},0)`)
        .call(d3.axisLeft(y).ticks(3).tickFormat(fmt).tickSize(0).tickPadding(4)).call(a => a.select(".domain").remove());
      g.append("g").attr("class", "axis").attr("transform", `translate(0,${H - mg.b})`)
        .call(d3.axisBottom(x).tickSize(0).tickPadding(6)).call(a => a.select(".domain").remove());
      g.append("text").attr("class", "series-label").attr("x", mg.l).attr("y", 10).text(title);
      g.append("g").selectAll("path").data(by).join("path").attr("class", cls)
        .attr("d", b => { const bx = x(b.label), bw = x.bandwidth(), y0 = y(0), y1 = y(b[key] || 0), r = Math.min(4, (y0 - y1) / 2);
          return `M${bx},${y0}V${y1 + r}Q${bx},${y1} ${bx + r},${y1}H${bx + bw - r}Q${bx + bw},${y1} ${bx + bw},${y1 + r}V${y0}Z`; });
      g.append("g").selectAll("rect").data(by).join("rect").attr("class", "hit")
        .attr("x", b => x(b.label)).attr("width", x.bandwidth()).attr("y", mg.t).attr("height", H - mg.t - mg.b)
        .on("pointermove", (ev, b) => showTooltip(ev, `<div class="t-title">Team of ${esc(b.label)}</div>
          <div>${b.n.toLocaleString()} pairs</div><div>average ${esc(SCORE_INFO[score].label.toLowerCase())}: ${SCORE_INFO[score].fmt(b.score)}</div>
          <div>worked together again: <strong>${pct(b.rate)}</strong></div>`))
        .on("pointerleave", hideTooltip);
    };
    panelChart(0, "score", `${SCORE_INFO[score].label} (average)`, d3.format(".2~f"), "team-bar score");
    panelChart(w + gap, "rate", "Worked together again", d3.format(".0%"), "team-bar rate");
    svg.append("text").attr("class", "series-label muted").attr("x", W / 2).attr("y", H - 4).attr("text-anchor", "middle").text("team size");
    return by;
  }

  /** Reunion rate by team size x shows together in the window: the partnership table. */
  function drawHeat(el) {
    const rows = withTeams();
    const COLS = [["1 show", 1, 1], ["2 shows", 2, 2], ["3+ shows", 3, Infinity]];
    const cells = [];
    BANDS.forEach((b, i) => COLS.forEach(([c, lo, hi], j) => {
      const list = rows.filter(r => r.band === i && r.p.shows_together >= lo && r.p.shows_together <= hi);
      cells.push({ i, j, row: b[0], col: c, n: list.length, rate: list.length ? d3.mean(list, r => +(r.p.reunion_shows > 0)) : null });
    }));
    const MIN_N = 15;
    const max = d3.max(cells.filter(c => c.n >= MIN_N), c => c.rate) || 1;
    const W = el.clientWidth || 320, mg = { t: 22, l: 54, r: 4, b: 4 }, cw = (W - mg.l - mg.r) / COLS.length, ch = 34;
    const H = mg.t + BANDS.length * ch + mg.b;
    const svg = d3.select(el).html("").append("svg").attr("class", "chart heat-chart").attr("width", W).attr("height", H)
      .attr("role", "img").attr("aria-label", "Share of pairs who reunited by team size and shows together");
    svg.append("g").selectAll("text").data(COLS).join("text").attr("class", "series-label muted").attr("text-anchor", "middle")
      .attr("x", (d, j) => mg.l + j * cw + cw / 2).attr("y", 14).text(d => `${d[0]} together`);
    svg.append("g").selectAll("text").data(BANDS).join("text").attr("class", "row-label").attr("text-anchor", "end")
      .attr("x", mg.l - 8).attr("y", (d, i) => mg.t + i * ch + ch / 2).attr("dy", "0.35em").text(d => `team ${d[0]}`);
    const g = svg.append("g").selectAll("g").data(cells).join("g")
      .attr("transform", c => `translate(${mg.l + c.j * cw},${mg.t + c.i * ch})`);
    const level = c => (c.n >= MIN_N && c.rate != null ? Math.round(10 + 80 * Math.sqrt(c.rate / max)) : 0);
    g.append("rect").attr("class", c => `heat-cell${c.n < MIN_N ? " few" : ""}`).attr("x", 1).attr("y", 1).attr("width", cw - 2).attr("height", ch - 2).attr("rx", 3)
      .style("fill", c => (c.n < MIN_N ? null : `color-mix(in srgb, var(--accent) ${level(c)}%, var(--surface-1))`));
    g.append("text").attr("class", c => `heat-val${level(c) > 55 ? " on-dark" : ""}`).attr("x", cw / 2).attr("y", ch / 2).attr("dy", "0.35em")
      .attr("text-anchor", "middle").text(c => (c.n < MIN_N ? (c.n ? `few (${c.n})` : "–") : pct(c.rate)));
    g.append("rect").attr("class", "hit").attr("width", cw).attr("height", ch)
      .on("pointermove", (ev, c) => showTooltip(ev, `<div class="t-title">Team of ${esc(c.row)}, ${esc(c.col)} together</div>
        <div>${c.n.toLocaleString()} pair${c.n === 1 ? "" : "s"}${c.rate != null ? ` · <strong>${pct(c.rate)}</strong> worked together again` : ""}</div>
        ${c.n < MIN_N ? `<div class="t-sub">fewer than ${MIN_N} pairs: not coloured</div>` : ""}`))
      .on("pointerleave", hideTooltip);
    return cells;
  }

  const pairRow = d => `<li data-key="${d.person_a + d.person_b}" class="${d.reunion_shows > 0 ? "reunion" : ""}">
    <span class="yr">#${d.rank}</span>
    <div><strong>${esc(nameOf(d.person_a))} & ${esc(nameOf(d.person_b))}</strong>
      <span class="roles">${SCORE_INFO[score].fmt(d[score])}</span>
      <div class="where">${d.met ? `last together on <em>${esc(d.met.show?.title)}</em> (${d.met.year})` : ""}${d.shows_together > 1 ? ` · ${d.shows_together} shows together` : ""}</div>
      <div class="${d.reunion_shows > 0 ? "again" : "still"}">${d.reunion_shows > 0
        ? `✓ again${d.again ? `: <em>${esc(d.again.show?.title)}</em> (${d.again.year})` : ""}`
        : "✗ no show together in the next 10 years"}</div>
    </div></li>`;

  function fillPanel() {
    const { db, panel } = ctxRef;
    const info = SCORE_INFO[score];
    const w = db.models.auc.windows.find(d => d.cutoff === cutoff);
    const hits = top.filter(d => d.reunion_shows > 0).length;
    const base = w ? w.reunited / w.pairs : 0;
    const tieTop = ranked.filter(p => p[score] === ranked[0]?.[score]).length;
    const tieMost = d3.greatest(d3.rollups(ranked, v => v.length, p => p[score]), d => d[1]);
    panel.innerHTML = `
      <h2>Who works together again?</h2>
      <p class="sub">H3. Every pair who shared a show in ${cutoff - 10}–${cutoff - 1} gets a score from that window only.
        Did they share a show in ${cutoff}–${cutoff + 9}? A good score ranks the pairs who did near the top.</p>
      <div class="seg score-seg" role="group" aria-label="Score">
        ${db.models.scores.map(k => `<button type="button" data-score="${k}" aria-pressed="${k === score}">${esc(SCORE_INFO[k].label)}</button>`).join("")}
      </div>
      <p class="hint">${esc(info.text)}</p>
      <h3>How well each score ranks (AUC)</h3>
      <div class="auc-wrap"></div>
      <p class="hint">Bar: this window. Tick: all ${db.models.auc.windows.length} windows pooled. AUC is how often a pair who reunited
        outranks one who didn't; 0.5 is a coin flip. Click a row to switch score.</p>
      <h3>Does a higher score mean more reunions?</h3>
      <div class="level-wrap"></div>
      <p class="hint">All windows, ${db.models.pairs.length.toLocaleString()} pairs; ${pct(d3.mean(db.models.pairs, p => +(p.reunion_shows > 0)))} reunite overall.</p>
      <h3>It's the pair, not the team</h3>
      <p class="sub">Why communities miss: big teams (revues, many writers) make dense communities, so BigCLAM scores
        their pairs high, but those pairs rarely work together again. Compare the two charts for each score.</p>
      <div class="team-wrap"></div>
      <p class="team-read hint"></p>
      <h3>Partnerships predict reunions</h3>
      <div class="heat-wrap"></div>
      <p class="heat-read hint"></p>
      <h3>Top ${TOP} pairs, ${cutoff - 10}–${cutoff - 1}</h3>
      <p class="pred-sum"><strong>${hits} of ${TOP}</strong> worked together again, against ${pct(base)} of all
        ${w?.pairs ?? ranked.length} pairs in this window${base ? ` (${(hits / TOP / base).toFixed(1)}×)` : ""}.
        ${tieTop > TOP ? `<br>${tieTop} pairs tie at the top score, so this top ${TOP} is partly arbitrary.` : ""}
        ${tieMost && tieMost[1] > ranked.length / 2 ? `<br>${pct(tieMost[1] / ranked.length)} of pairs have the same score (${info.fmt(tieMost[0])}): the score can't tell them apart.` : ""}</p>
      <div class="legend">
        <span><span class="key pred-hit"></span>worked together again (arc: from their last show together to where they reunited)</span>
        <span><span class="key pred-miss"></span>did not</span>
      </div>
      <ol class="pair-list event-list">${top.map(pairRow).join("")}</ol>
      <h3>Missed: reunited, but ranked low</h3>
      <ol class="pair-list event-list missed">${missed.map(pairRow).join("") || `<li class="none">No pair reunited in this window.</li>`}</ol>`;
    drawAuc(panel.querySelector(".auc-wrap"));
    drawLevels(panel.querySelector(".level-wrap"));
    const by = drawTeamSize(panel.querySelector(".team-wrap"));
    const first = by[0], last = by.at(-1);
    const up = last.score > first.score, avg = d3.format(".2~f");
    panel.querySelector(".team-read").innerHTML = `All windows. Pairs from teams of ${first.label} reunite ${pct(first.rate)}, teams of ${last.label} ${pct(last.rate)}.
      ${esc(SCORE_INFO[score].label)} ${up ? `<strong>rises</strong> with team size (${avg(first.score)} → ${avg(last.score)}): it points the wrong way.`
        : `falls with team size (${avg(first.score)} → ${avg(last.score)}), the same way as reunions${score === "weighted" ? " (by design: its weights shrink big teams)" : ""}.`}
      A pair's team is the smallest show they shared in the window.`;
    const cells = drawHeat(panel.querySelector(".heat-wrap"));
    const c = (i, j) => cells.find(x => x.i === i && x.j === j);
    panel.querySelector(".heat-read").innerHTML = `Share of pairs who worked together again in the next 10 years, all windows.
      Doing more shows together matters most (small teams: ${pct(c(0, 0).rate)} after one show, ${pct(c(0, 2).rate ?? 0)} after 3+);
      among first-time pairs, small teams still beat big ones (${pct(c(0, 0).rate)} vs ${pct(c(3, 0).rate)}).
      Pale or "few" cells have fewer than 15 pairs.`;
    panel.querySelectorAll(".seg button[data-score]").forEach(b => b.addEventListener("click", () => setScore(b.dataset.score)));
    const all = [...top, ...missed];
    panel.querySelectorAll(".pair-list li[data-key]").forEach(li => {
      const d = all.find(x => x.person_a + x.person_b === li.dataset.key);
      li.addEventListener("pointerenter", () => highlight(d));
      li.addEventListener("pointerleave", () => highlight(null));
      li.addEventListener("click", () => openCareers(d));
    });
  }

  function setScore(k) {
    if (k === score) return;
    location.hash = `#predict?score=${k}&year=${ctxRef.state.year}`;
  }

  function apply(year, force = false) {
    const T = cutoffFor(ctxRef.db, year);
    if (T === cutoff && !force) return;
    cutoff = T;
    rank();
    drawMap();
    const scrollTop = ctxRef.panel.scrollTop;
    fillPanel();
    ctxRef.panel.scrollTop = scrollTop;
  }

  return {
    id: "predict", label: "Predict", caption: "H3: who reunites?", usesYear: true,

    enter(ctx) {
      ctxRef = ctx;
      cutoff = null;
      if (!ctx.db.models) {
        ctx.panel.innerHTML = `<h2>Who works together again?</h2><p class="hint">viz/data/models.json is missing: run scripts/17_export_model_viz.py.</p>`;
        return;
      }
      const s = ctx.state.params.get("score");
      if (s && SCORE_INFO[s] && ctx.db.models.scores.includes(s)) score = s;
      const cut = ctx.db.meta.network.cutoffs;
      ctx.setRange([cut[0] - 10, cut[cut.length - 1] - 1]);
      ctx.theatres.dots.attr("class", "t theatre faint").transition("mode").duration(500).attr("r", 2.5).attr("opacity", 0.3);
      root = ctx.map.layer("overlay").append("g").attr("class", "mode-predict");
      offZoom = ctx.map.onZoom(place);
      apply(ctx.state.year);
      const pts = top.flatMap(d => [d.met?.theatre, d.again?.theatre]).filter(Boolean).map(t => [t.lat, t.lon]);
      if (pts.length) ctx.map.zoomTo(pts, { pad: 80, duration: 900 });
    },

    onParams(ctx) {
      const s = ctx.state.params.get("score");
      if (s && SCORE_INFO[s] && s !== score) { score = s; apply(ctx.state.year, true); }
      else apply(ctx.state.year);
    },

    setYear(ctx, y) { if (root) apply(y); },

    exit() {
      offZoom?.();
      root?.transition().duration(250).attr("opacity", 0).remove();
      root = null;
      hideTooltip();
    },

    params: () => ({ score }),
    tip: t => `<div class="t-title">${esc(t.name)}</div>`,
  };
}
