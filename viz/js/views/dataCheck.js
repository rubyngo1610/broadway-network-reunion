// Data check: what the export contains, plus a first plot of every theatre on the Manhattan grid
// to confirm the coordinates (the start of the shared Theater District map).
import * as d3 from "https://cdn.jsdelivr.net/npm/d3@7.9.0/+esm";
import { toGrid, BROADWAY, AVENUES } from "../grid.js";
import { showTooltip, hideTooltip, esc } from "../tooltip.js";

const fmt = d3.format(",");

export function renderDataCheck(el, db) {
  const c = db.meta.counts;
  const pct = (a, b) => `${Math.round((100 * a) / b)}%`;
  const strictPairs = db.reunions.strict.length;
  const reunited = db.reunions.strict.filter(r => r.reunion_shows > 0).length;

  el.innerHTML = `
    <div class="grid-2">
      <section class="panel">
        <h2>What's loaded</h2>
        <p class="sub">From <code>viz/data/</code>, exported ${esc(db.meta.generated)}.</p>
        <table class="stats">
          <thead><tr><th>Table</th><th class="num">Rows</th><th>Coverage</th></tr></thead>
          <tbody>
            <tr><td>Shows (core set)</td><td class="num">${fmt(c.shows)}</td><td>${pct(c.shows_with_venue, c.shows)} with an opening theatre</td></tr>
            <tr><td>Theatres</td><td class="num">${fmt(c.theatres)}</td><td>all with coordinates</td></tr>
            <tr><td>People</td><td class="num">${fmt(c.people)}</td><td>${pct(c.people_with_birthplace, c.people)} with a birthplace</td></tr>
            <tr><td>Credits (person–show)</td><td class="num">${fmt(c.credits)}</td><td>core roles</td></tr>
            <tr><td>Pairs, strict mode</td><td class="num">${fmt(strictPairs)}</td><td>${pct(reunited, strictPairs)} reunite within ${db.meta.network.horizon_years} years</td></tr>
          </tbody>
        </table>
        <ul class="notes">${db.meta.notes.map(n => `<li>${esc(n)}</li>`).join("")}</ul>
      </section>

      <section class="panel">
        <h2>Theatres on the Manhattan grid</h2>
        <p class="sub">Every theatre at its Wikidata location, drawn in street-and-avenue units with north up.
          Avenues are spaced wider than true scale so the Theater District reads clearly.
          Dot size = number of shows that opened there.</p>
        <div class="controls">
          <label for="year">Year</label>
          <input id="year" type="range" min="1900" max="2025" step="1" value="1930">
          <output id="year-out" for="year">1930</output>
          <span id="year-count" class="sub" style="margin:0"></span>
        </div>
        <div id="theatre-map"></div>
      </section>
    </div>`;

  drawTheatreMap(el.querySelector("#theatre-map"), db, el);
}

function drawTheatreMap(container, db, root) {
  const STREET_MIN = 21, STREET_MAX = 67, AVE_MIN = 4.6, AVE_MAX = 9.8;
  const AVE_STRETCH = 8;   // one avenue block drawn as wide as 8 street blocks (true scale is ~4)
  const W = 560, H = Math.round(((STREET_MAX - STREET_MIN) / ((AVE_MAX - AVE_MIN) * AVE_STRETCH)) * W);
  const margin = { top: 24, right: 16, bottom: 12, left: 44 };

  // x: east to the right (lower avenue numbers are east); y: north up
  const x = d3.scaleLinear().domain([AVE_MAX, AVE_MIN]).range([margin.left, W - margin.right]);
  const y = d3.scaleLinear().domain([STREET_MIN, STREET_MAX]).range([H - margin.bottom, margin.top]);

  const svg = d3.select(container).append("svg")
    .attr("class", "chart").attr("viewBox", `0 0 ${W} ${H}`)
    .attr("role", "img").attr("aria-label", "Map of Broadway theatres on the Manhattan street grid");

  // streets: hairline every street, labels every 5
  const streets = d3.range(STREET_MIN + 1, STREET_MAX);
  svg.append("g").selectAll("line").data(streets).join("line")
    .attr("class", "street").attr("x1", margin.left).attr("x2", W - margin.right)
    .attr("y1", d => y(d)).attr("y2", d => y(d)).attr("stroke-opacity", d => (d % 5 === 0 ? 1 : 0.45));
  svg.append("g").selectAll("text").data(streets.filter(d => d % 5 === 0)).join("text")
    .attr("class", "street-label").attr("x", margin.left - 6).attr("y", d => y(d)).attr("dy", "0.32em")
    .attr("text-anchor", "end").text(d => `${d}th`);

  // avenues
  svg.append("g").selectAll("line").data(AVENUES).join("line")
    .attr("class", "street").attr("x1", d => x(d.avenue)).attr("x2", d => x(d.avenue))
    .attr("y1", y(STREET_MIN)).attr("y2", y(STREET_MAX)).attr("stroke-width", 2);
  svg.append("g").selectAll("text").data(AVENUES).join("text")
    .attr("class", "street-label").attr("x", d => x(d.avenue)).attr("y", margin.top - 8)
    .attr("text-anchor", "middle").text(d => d.name);

  // Broadway
  svg.append("path").datum(BROADWAY)
    .attr("fill", "none").attr("stroke", "var(--axis)").attr("stroke-width", 3)
    .attr("d", d3.line().x(d => x(d.avenue)).y(d => y(d.street)));
  svg.append("text").attr("class", "street-label").attr("transform", () => {
    const a = BROADWAY[1], b = BROADWAY[2];
    let ang = (Math.atan2(y(b.street) - y(a.street), x(b.avenue) - x(a.avenue)) * 180) / Math.PI;
    if (ang > 90) ang -= 180;          // keep the label upright
    if (ang < -90) ang += 180;
    return `translate(${x(6.45)},${y(39.5)}) rotate(${ang})`;
  }).attr("dy", "-0.5em").attr("text-anchor", "middle").text("Broadway");

  // theatres
  const pts = db.theatres.map(t => ({ ...t, ...toGrid(t.lat, t.lon) }));
  const g = svg.append("g");
  const dots = g.selectAll("circle.theatre").data(pts, d => d.id).join("circle")
    .attr("cx", d => x(d.avenue)).attr("cy", d => y(d.street))
    .attr("r", d => 3 + Math.sqrt(d.n_shows) * 0.9);
  // larger invisible hit targets
  g.selectAll("circle.hit").data(pts, d => d.id).join("circle")
    .attr("class", "hit").attr("cx", d => x(d.avenue)).attr("cy", d => y(d.street)).attr("r", 10)
    .on("pointermove", (ev, d) => {
      const opened = d.opened ?? (d.first_show != null ? `by ${d.first_show}` : "?");
      const span = `${opened}–${d.demolished ?? "today"}`;
      showTooltip(ev, `<div class="t-title">${esc(d.name)}</div>
        <div class="t-sub">${span} · ${d.n_shows} show${d.n_shows === 1 ? "" : "s"} opened here</div>
        <div class="t-sub">${d.street.toFixed(1)} St, ${d.avenue.toFixed(2)} Ave (grid)</div>`);
    })
    .on("pointerleave", hideTooltip);

  const slider = root.querySelector("#year"), out = root.querySelector("#year-out"), cnt = root.querySelector("#year-count");
  function update() {
    const year = +slider.value;
    out.value = year;
    let n = 0;
    dots.attr("class", d => {
      const up = db.standing(d, year);
      if (up) n++;
      return up ? "theatre" : "theatre gone";
    });
    cnt.textContent = `${n} theatres standing (filled); hollow = not yet built or demolished`;
  }
  slider.addEventListener("input", update);
  update();
}
