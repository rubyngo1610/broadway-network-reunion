// NYC show map (explore mode): pick a year; theatres that opened a show that year are filled,
// other standing theatres are rings, theatres not standing are faint. Zoom and pan the map.
import * as d3 from "https://cdn.jsdelivr.net/npm/d3@7.9.0/+esm";
import { createManhattanMap, drawTheatres } from "../manhattanMap.js";
import { showTooltip, hideTooltip, esc } from "../tooltip.js";

export function renderShowMap(el, db, params) {
  const years = d3.extent(db.shows, s => s.year);
  const start = +params.get("year") || 1927;

  el.innerHTML = `
    <section class="panel">
      <h2>Broadway on the map</h2>
      <p class="sub">Where each year's new musicals opened. Drag to pan, scroll or use + / − to zoom.
        Theatres with no recorded opening date count from the year of their first show in our data.</p>
      <div class="controls">
        <label for="sm-year">Year</label>
        <input id="sm-year" type="range" min="${years[0]}" max="${years[1]}" step="1" value="${start}">
        <output id="sm-year-out" for="sm-year">${start}</output>
        <button type="button" id="sm-play" class="btn">▶ Play</button>
      </div>
      <div class="showmap-layout">
        <div>
          <div id="sm-map"></div>
          <div class="legend">
            <span><span class="key on"></span>a show opened here this year</span>
            <span><span class="key standing"></span>theatre standing</span>
            <span><span class="key gone"></span>not built yet or demolished</span>
          </div>
        </div>
        <div>
          <h3 id="sm-list-title" style="margin:0 0 6px;font-size:16px"></h3>
          <ul id="sm-list" class="show-list"></ul>
        </div>
      </div>
    </section>`;

  const mapEl = el.querySelector("#sm-map");
  const map = createManhattanMap(mapEl, db, { height: Math.min(680, Math.max(420, mapEl.clientWidth * 0.95)) });

  let year = start;
  const opensIn = (t, y) => (db.showsByTheatre.get(t.id) || []).filter(s => s.year === y);

  const { dots } = drawTheatres(map, db, {
    onHover: (ev, t) => {
      const now = opensIn(t, year);
      const span = `${t.opened ?? (t.first_show != null ? `by ${t.first_show}` : "?")}–${t.demolished ?? "today"}`;
      showTooltip(ev, `<div class="t-title">${esc(t.name)}</div>
        <div class="t-sub">${span} · ${t.n_shows} show${t.n_shows === 1 ? "" : "s"} in our data</div>
        ${now.length ? `<div>${year}: ${now.map(s => `<em>${esc(s.title)}</em>`).join(", ")}</div>` : ""}`);
    },
    onLeave: hideTooltip,
  });

  // labels for theatres with a show this year, shown when zoomed in
  const labelG = map.layer("top");

  const slider = el.querySelector("#sm-year"), out = el.querySelector("#sm-year-out");
  const list = el.querySelector("#sm-list"), listTitle = el.querySelector("#sm-list-title");

  function update() {
    out.value = year;
    slider.value = year;
    dots.attr("class", t => {
      if (opensIn(t, year).length) return "t theatre";
      return db.standing(t, year) ? "t theatre gone" : "t theatre faint";
    }).attr("r", t => (opensIn(t, year).length ? 6 : 3.5)).attr("opacity", t => (db.standing(t, year) || opensIn(t, year).length ? 1 : 0.35));
    dots.filter(t => opensIn(t, year).length).raise();

    const opening = db.shows.filter(s => s.year === year);
    listTitle.textContent = `${opening.length} new musical${opening.length === 1 ? "" : "s"} in ${year}`;
    list.innerHTML = opening.map(s => {
      const t = db.theatreById.get(s.venue);
      return `<li class="${t ? "" : "no-venue"}"><strong>${esc(s.title)}</strong>
        <div class="where">${t ? esc(t.name) : "theatre unknown"}</div></li>`;
    }).join("");

    const lit = db.theatres.filter(t => opensIn(t, year).length);
    labelG.selectAll("text").data(lit, d => d.id).join("text").attr("class", "theatre-label").attr("dx", 9).attr("dy", "0.35em")
      .text(d => d.name);
    placeLabels(map.transform);
  }
  function placeLabels(tr) {
    labelG.selectAll("text")
      .attr("x", d => map.xy(d.lat, d.lon)[0]).attr("y", d => map.xy(d.lat, d.lon)[1])
      .attr("display", tr.k >= 3 ? null : "none");
  }
  map.onZoom(placeLabels);

  slider.addEventListener("input", () => { year = +slider.value; update(); stop(); });

  // play through the years
  let timer = null;
  const playBtn = el.querySelector("#sm-play");
  function stop() { if (timer) { timer.stop(); timer = null; playBtn.textContent = "▶ Play"; } }
  playBtn.addEventListener("click", () => {
    if (timer) return stop();
    playBtn.textContent = "❚❚ Pause";
    let last = 0;
    timer = d3.timer(elapsed => {
      if (elapsed - last < 450) return;
      last = elapsed;
      year = year >= years[1] ? years[0] : year + 1;
      update();
    });
  });

  update();
}
