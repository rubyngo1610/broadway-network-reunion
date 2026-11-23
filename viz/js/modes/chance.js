// Chance mode (H1): do teams reunite more often than chance? Step 10's null model reshuffles who
// worked with whom (keeping everyone's number of credits, roles, team sizes and dates) 1,000 times.
// The panel charts the observed reunion rate per network window against the shuffled range; the
// map shows the window's shows, gold where the team reunited more than in the shuffles.
//
// The timeline picks the window: the year falls in the training window [T-10, T) of cutoff T.
// Data: db.h1 (viz/data/h1.json, written by scripts/10_null_model.py).
//
// URL: #chance?year=1943
import * as d3 from "https://cdn.jsdelivr.net/npm/d3@7.9.0/+esm";
import { esc, showTooltip, hideTooltip } from "../tooltip.js";
import { cutoffFor } from "../communities.js";

const NETWORK = "strict";
const DOT_R = 4.5, SPACING = 7;
const pct = v => `${(100 * v).toFixed(1)}%`;

export function chanceMode() {
  let root = null, offZoom = null, ctxRef = null, cutoff = null, dots = [];

  // --- data for one window -------------------------------------------------------------------

  /** Every show in the training window [T-10, T), with its H1 result if its team had a reunion. */
  function windowShows(T) {
    const { db } = ctxRef;
    const h = db.h1[NETWORK];
    const shows = new Set(db.credits.filter(c => c[NETWORK] && c.year >= T - 10 && c.year < T).map(c => c.show));
    return [...shows].map(id => {
      const r = h.shows.get(`${T}|${id}`);
      const status = !r ? "none" : r.p_value < db.h1.alpha ? "above" : "reunited";
      return { id, show: db.showById.get(id), theatre: db.theatreOf(id), r, status };
    }).sort((a, b) => (a.show?.year ?? 0) - (b.show?.year ?? 0));
  }

  // --- map -----------------------------------------------------------------------------------

  const order = { above: 0, reunited: 1, none: 2 };
  function positions() {
    const pos = new Map();
    for (const [, list] of d3.groups(dots.filter(d => d.theatre), d => d.theatre.id)) {
      list.sort((a, b) => order[a.status] - order[b.status] || d3.ascending(a.id, b.id));
      const [x, y] = ctxRef.map.xy(list[0].theatre.lat, list[0].theatre.lon);
      list.forEach((d, i) => {
        const r = SPACING * Math.sqrt(i), a = i * 2.39996;
        pos.set(d.id, [x + r * Math.cos(a), y + r * Math.sin(a)]);
      });
    }
    return pos;
  }

  function place() {
    if (!root) return;
    const pos = positions();
    root.selectAll("circle.hdot").attr("cx", d => pos.get(d.id)[0]).attr("cy", d => pos.get(d.id)[1]);
  }

  function drawMap() {
    const sel = root.selectAll("circle.hdot").data(dots.filter(d => d.theatre), d => d.id);
    sel.exit().transition().duration(250).attr("r", 0).remove();
    const enter = sel.enter().append("circle").attr("r", 0)
      .on("pointerenter", (ev, d) => highlight(d.id))
      .on("pointermove", (ev, d) => showTooltip(ev, showTip(d)))
      .on("pointerleave", () => { highlight(null); hideTooltip(); });
    sel.merge(enter)
      .attr("class", d => `hdot ${d.status}`)
      .transition().duration(350).attr("r", d => (d.status === "none" ? DOT_R - 1.5 : DOT_R));
    root.selectAll("circle.hdot").filter(d => d.status !== "none").raise();
    root.selectAll("circle.hdot").filter(d => d.status === "above").raise();
    place();
  }

  function highlight(id) {
    root?.selectAll("circle.hdot").classed("active", d => d.id === id);
    ctxRef.panel.querySelectorAll(".h1-list li").forEach(li => li.classList.toggle("active", li.dataset.show === id));
  }

  function showTip(d) {
    const r = d.r;
    return `<div class="t-title"><em>${esc(d.show?.title ?? d.id)}</em> (${d.show?.year ?? "?"})</div>
      <div class="t-sub">${d.theatre ? esc(d.theatre.name) : "theatre unknown"}</div>
      ${r ? `<div>${r.reunited_pairs} of ${r.team_size * (r.team_size - 1) / 2} team pairs worked together again by ${cutoff + 9}</div>
             <div>shuffled careers: ${r.null_mean.toFixed(2)} pairs on average · p = ${r.p_value.toFixed(3)}</div>
             <div>${d.status === "above" ? "<strong>more than chance</strong>" : "within what chance gives"}</div>`
          : `<div>no one from this team worked together again in ${cutoff}–${cutoff + 9}</div>`}`;
  }

  // --- panel ---------------------------------------------------------------------------------

  /** Observed reunion rate per window against the shuffled 95% range (one-axis line chart). */
  function drawChart(el) {
    const rows = ctxRef.db.h1[NETWORK].windows;
    const W = el.clientWidth || 320, H = 190, m = { t: 14, r: 64, b: 26, l: 38 };
    const x = d3.scaleLinear().domain(d3.extent(rows, d => d.cutoff)).range([m.l, W - m.r]);
    const y = d3.scaleLinear().domain([0, d3.max(rows, d => Math.max(d.observed_rate, d.null_hi)) * 1.1]).nice().range([H - m.b, m.t]);
    const svg = d3.select(el).append("svg").attr("class", "chart h1-chart").attr("width", W).attr("height", H)
      .attr("role", "img").attr("aria-label", "Observed reunion rate per window against the range from shuffled careers");
    svg.append("g").attr("class", "grid").selectAll("line").data(y.ticks(4)).join("line")
      .attr("x1", m.l).attr("x2", W - m.r).attr("y1", y).attr("y2", y);
    svg.append("g").attr("class", "axis").attr("transform", `translate(0,${H - m.b})`)
      .call(d3.axisBottom(x).ticks(5).tickFormat(d => d - 10).tickSize(0).tickPadding(8)).call(g => g.select(".domain").remove());
    svg.append("g").attr("class", "axis").attr("transform", `translate(${m.l},0)`)
      .call(d3.axisLeft(y).ticks(4).tickFormat(d3.format(".0%")).tickSize(0).tickPadding(6)).call(g => g.select(".domain").remove());
    svg.append("path").attr("class", "null-band").datum(rows)
      .attr("d", d3.area().x(d => x(d.cutoff)).y0(d => y(d.null_lo)).y1(d => y(d.null_hi)));
    svg.append("path").attr("class", "null-line").datum(rows).attr("d", d3.line().x(d => x(d.cutoff)).y(d => y(d.null_mean)));
    svg.append("path").attr("class", "obs-line").datum(rows).attr("d", d3.line().x(d => x(d.cutoff)).y(d => y(d.observed_rate)));
    svg.append("line").attr("class", "now-rule").attr("y1", m.t).attr("y2", H - m.b);
    svg.append("g").selectAll("circle").data(rows).join("circle").attr("class", "obs-dot")
      .attr("cx", d => x(d.cutoff)).attr("cy", d => y(d.observed_rate)).attr("r", 4);
    // direct labels at the right end
    const last = rows[rows.length - 1];
    svg.append("text").attr("class", "series-label").attr("x", W - m.r + 6).attr("y", y(last.observed_rate)).attr("dy", "0.35em").text("observed");
    svg.append("text").attr("class", "series-label muted").attr("x", W - m.r + 6).attr("y", y(last.null_mean)).attr("dy", "0.35em").text("chance");
    // hover: one column per window, bigger than the marks
    const step = rows.length > 1 ? x(rows[1].cutoff) - x(rows[0].cutoff) : 20;
    svg.append("g").selectAll("rect").data(rows).join("rect").attr("class", "hit")
      .attr("x", d => x(d.cutoff) - step / 2).attr("width", step).attr("y", m.t).attr("height", H - m.t - m.b)
      .on("pointermove", (ev, d) => showTooltip(ev, `<div class="t-title">Teams of ${d.cutoff - 10}–${d.cutoff - 1}</div>
        <div>${d.reunited} of ${d.pairs} pairs worked together again in ${d.cutoff}–${d.cutoff + 9}: <strong>${pct(d.observed_rate)}</strong></div>
        <div>shuffled careers: ${pct(d.null_mean)} (95% of shuffles ${pct(d.null_lo)}–${pct(d.null_hi)})</div>`))
      .on("pointerleave", hideTooltip)
      .on("click", (ev, d) => ctxRef.setYear(d.cutoff - 5));
    el._x = x;
  }

  function fillPanel() {
    const { db, panel } = ctxRef;
    const rows = db.h1[NETWORK].windows;
    const obs = d3.sum(rows, d => d.reunited) / d3.sum(rows, d => d.pairs);
    const exp = d3.sum(rows, d => d.null_mean * d.pairs) / d3.sum(rows, d => d.pairs);
    panel.innerHTML = `
      <h2>More than chance?</h2>
      <p class="sub">H1. For each 10-year window, the share of pairs who shared a show and worked together
        again in the next 10 years (gold), against <strong>shuffled careers</strong>: the same people, roles,
        team sizes and dates, but who works with whom reassigned at random, 1,000 times (grey band: 95% of shuffles).</p>
      <p class="h1-headline">Pooled over all windows: <strong>${pct(obs)}</strong> of pairs reunite vs <strong>${pct(exp)}</strong>
        in shuffled careers, <strong>${(obs / exp).toFixed(1)}×</strong> chance.</p>
      <div class="h1-chart-wrap"></div>
      <p class="hint">x axis: first year of the window. Click a point to move the timeline there.</p>
      <div class="h1-window"></div>
      <div class="legend">
        <span><span class="key h1-above"></span>team reunited more than chance (p &lt; ${db.h1.alpha})</span>
        <span><span class="key h1-reunited"></span>some reunited, within chance</span>
        <span><span class="key h1-none"></span>no reunion</span>
      </div>
      <p class="hint">Each show is tested on its own, so about 1 in 20 would pass by luck: read gold as a highlight, not proof for that team.</p>
      <ol class="h1-list event-list"></ol>`;
    drawChart(panel.querySelector(".h1-chart-wrap"));
  }

  function updatePanel() {
    const { db, panel } = ctxRef;
    const w = db.h1[NETWORK].windows.find(d => d.cutoff === cutoff);
    const wrap = panel.querySelector(".h1-chart-wrap");
    if (wrap?._x) d3.select(wrap).select(".now-rule").attr("x1", wrap._x(cutoff)).attr("x2", wrap._x(cutoff));
    d3.select(wrap).selectAll(".obs-dot").classed("now", d => d.cutoff === cutoff);
    const n = { above: 0, reunited: 0, none: 0 };
    for (const d of dots) n[d.status]++;
    panel.querySelector(".h1-window").innerHTML = w ? `
      <h3>Teams of ${cutoff - 10}–${cutoff - 1}</h3>
      <p>${w.reunited} of ${w.pairs} pairs worked together again in ${cutoff}–${cutoff + 9}: <strong>${pct(w.observed_rate)}</strong>
        vs ${pct(w.null_mean)} by chance (${(w.observed_rate / w.null_mean).toFixed(1)}×).
        ${w.observed_rate > w.null_hi ? "Higher than 95% of the shuffles." : "Inside the shuffled range in this window."}</p>
      <p class="hint">${dots.length} shows: ${n.above} above chance, ${n.reunited} with a reunion within chance, ${n.none} with none.
        ${dots.filter(d => !d.theatre).length} have no known theatre and are not on the map.</p>` : "";
    const list = dots.filter(d => d.status !== "none").sort((a, b) => a.r.p_value - b.r.p_value);
    const ol = panel.querySelector(".h1-list");
    ol.innerHTML = list.map(d => `<li data-show="${d.id}" class="${d.status === "above" ? "reunion" : ""}">
      <span class="yr">${d.show?.year ?? ""}</span>
      <div><strong>${esc(d.show?.title ?? d.id)}</strong> <span class="roles">team of ${d.r.team_size}</span>
        <div class="where">${d.r.reunited_pairs} pair${d.r.reunited_pairs === 1 ? "" : "s"} reunited vs ${d.r.null_mean.toFixed(2)} by chance · p = ${d.r.p_value.toFixed(3)}</div>
      </div></li>`).join("") || `<li class="none">No team from this window reunited.</li>`;
    ol.querySelectorAll("li[data-show]").forEach(li => {
      li.addEventListener("pointerenter", () => highlight(li.dataset.show));
      li.addEventListener("pointerleave", () => highlight(null));
    });
  }

  function apply(year) {
    const T = cutoffFor(ctxRef.db, year);
    if (T === cutoff) return;
    cutoff = T;
    dots = windowShows(T);
    drawMap();
    updatePanel();
  }

  return {
    id: "chance", label: "Chance", caption: "H1: more than luck?", usesYear: true,

    enter(ctx) {
      ctxRef = ctx;
      cutoff = null;
      if (!ctx.db.h1) {
        ctx.panel.innerHTML = `<h2>More than chance?</h2><p class="hint">viz/data/h1.json is missing: run scripts/10_null_model.py.</p>`;
        return;
      }
      const cut = ctx.db.meta.network.cutoffs;
      ctx.setRange([cut[0] - 10, cut[cut.length - 1] - 1]);
      ctx.theatres.dots.attr("class", "t theatre faint").transition("mode").duration(500).attr("r", 2.5).attr("opacity", 0.3);
      root = ctx.map.layer("overlay").append("g").attr("class", "mode-chance");
      offZoom = ctx.map.onZoom(place);
      fillPanel();
      apply(ctx.state.year);
      const pts = dots.filter(d => d.theatre).map(d => [d.theatre.lat, d.theatre.lon]);
      if (pts.length) ctx.map.zoomTo(pts, { pad: 80, duration: 900 });
    },

    setYear(ctx, y) { if (root) apply(y); },

    exit() {
      offZoom?.();
      root?.transition().duration(250).attr("opacity", 0).remove();
      root = null;
      hideTooltip();
    },

    tip: t => `<div class="t-title">${esc(t.name)}</div>`,
  };
}
