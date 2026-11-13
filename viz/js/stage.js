// The stage: one map that stays on screen for every view. Views are "modes" that restyle the
// shared theatre dots, add their own layers and fill the side panel. Switching modes animates
// the map instead of loading a new page, and the zoom and the year carry over.
//
// A mode is an object:
//   { id, label, caption, usesYear,
//     enter(ctx)            set up: fill ctx.panel, add layers, restyle ctx.theatres.dots
//     setYear(ctx, year)    the timeline moved (only called while the mode is active)
//     exit(ctx)             remove its layers and listeners (fade them out if you like)
//     tip(t, ctx)           optional: tooltip HTML for theatre t
//     params()              optional: extra URL parameters to keep in the hash, as an object }
//
// ctx = { db, map, panel, theatres: { dots, hits }, state: { year, params }, years, setYear }
import * as d3 from "https://cdn.jsdelivr.net/npm/d3@7.9.0/+esm";
import { createManhattanMap, drawTheatres } from "./manhattanMap.js";
import { showTooltip, hideTooltip } from "./tooltip.js";

export function createStage(el, db, modes, { startYear = 1927 } = {}) {
  const years = d3.extent(db.shows, s => s.year);

  el.innerHTML = `
    <div class="stage">
      <nav class="mode-bar" aria-label="Views">
        ${modes.map(m => `<a href="#${m.id}" data-mode="${m.id}">
          <span class="mode-label">${m.label}</span><span class="mode-cap">${m.caption}</span></a>`).join("")}
      </nav>
      <div class="stage-map"></div>
      <div class="timeline">
        <label for="tl-year">Year</label>
        <input id="tl-year" type="range" min="${years[0]}" max="${years[1]}" step="1" value="${startYear}">
        <output id="tl-year-out" for="tl-year">${startYear}</output>
        <button type="button" id="tl-play" class="btn">▶ Play</button>
      </div>
      <aside class="stage-panel panel"></aside>
    </div>`;

  const mapEl = el.querySelector(".stage-map");
  const map = createManhattanMap(mapEl, db, { height: Math.min(680, Math.max(420, mapEl.clientWidth * 0.9)) });
  const panel = el.querySelector(".stage-panel");
  const timeline = el.querySelector(".timeline");
  const slider = el.querySelector("#tl-year"), out = el.querySelector("#tl-year-out");
  const playBtn = el.querySelector("#tl-play");

  let current = null;
  const state = { year: startYear, params: new URLSearchParams() };
  const theatres = drawTheatres(map, db, {
    onHover: (ev, t) => { const html = current?.tip?.(t, ctx); if (html) showTooltip(ev, html); },
    onLeave: hideTooltip,
  });
  const ctx = { db, map, panel, theatres, state, years, setYear };

  function syncUrl() {
    const p = new URLSearchParams(current.params?.() || {});
    if (current.usesYear) p.set("year", state.year);
    const q = p.toString();
    history.replaceState(null, "", `#${current.id}${q ? `?${q}` : ""}`);
  }

  function setYear(y) {
    state.year = Math.max(years[0], Math.min(years[1], y));
    slider.value = out.value = state.year;
    current?.setYear?.(ctx, state.year);
    if (current) syncUrl();
  }

  /** Switch to a mode (or just apply new parameters if it is already active). */
  function go(id, params = new URLSearchParams()) {
    const next = modes.find(m => m.id === id) || modes[0];
    state.params = params;
    const y = +params.get("year");
    if (y) { state.year = Math.max(years[0], Math.min(years[1], y)); slider.value = out.value = state.year; }

    if (next !== current) {
      hideTooltip();
      current?.exit?.(ctx);
      current = next;
      el.querySelectorAll(".mode-bar a").forEach(a =>
        a.dataset.mode === next.id ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
      timeline.classList.toggle("off", !next.usesYear);
      if (!next.usesYear) stop();
      slider.disabled = playBtn.disabled = !next.usesYear;
      next.enter(ctx);
      panel.animate([{ opacity: 0, transform: "translateY(6px)" }, { opacity: 1, transform: "none" }],
        { duration: 280, easing: "ease-out" });
    } else {
      current.setYear?.(ctx, state.year);
    }
    syncUrl();
  }

  slider.addEventListener("input", () => { stop(); setYear(+slider.value); });

  // play through the years
  let timer = null;
  function stop() { if (timer) { timer.stop(); timer = null; playBtn.textContent = "▶ Play"; } }
  playBtn.addEventListener("click", () => {
    if (timer) return stop();
    playBtn.textContent = "❚❚ Pause";
    let last = 0;
    timer = d3.timer(elapsed => {
      if (elapsed - last < 450) return;
      last = elapsed;
      setYear(state.year >= years[1] ? years[0] : state.year + 1);
    });
  });

  return { go, ctx, get mode() { return current?.id; } };
}
