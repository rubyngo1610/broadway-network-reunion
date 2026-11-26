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
//     onParams(ctx)         optional: the URL changed while this mode is active (e.g. another person)
//     params()              optional: extra URL parameters to keep in the hash, as an object
//     split                 optional: true = two maps side by side (panel | map | map | panel);
//                           ctx.split = { left, right } holds a ctx per side (own map, panel and
//                           theatre dots; the timeline and URL stay shared). The page widens. }
//
// A mode can narrow the timeline with ctx.setRange([from, to]) (e.g. one person's career); the
// range resets to all years whenever the mode changes.
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
      <div class="split-area" hidden>
        <aside class="stage-panel split-panel split-panel-l panel"></aside>
        <div class="split-map split-map-l"></div>
        <div class="split-map split-map-r"></div>
        <aside class="stage-panel split-panel split-panel-r panel"></aside>
      </div>
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
  const ctx = { db, map, panel, theatres, state, years, setYear, setRange };
  // not enumerable, so the per-side contexts below can copy ctx with {...ctx}
  Object.defineProperty(ctx, "split", { get: () => ensureSplit() });

  // --- split layout: built the first time a split mode opens (it must be visible to be measured) ---
  const splitEl = el.querySelector(".split-area");
  let split = null;
  function ensureSplit() {
    if (split) return split;
    const side = (mapBox, panelEl, isRight) => {
      const w = mapBox.clientWidth || 480;
      // fill the screen below the timeline (no gap under the maps); the panels match this height
      const h = Math.round(Math.max(520, Math.min(1000, window.innerHeight - mapBox.getBoundingClientRect().top - 24)));
      splitEl.style.setProperty("--split-h", `${h}px`);
      const m = createManhattanMap(mapBox, db, { height: h });
      const th = drawTheatres(m, db, {
        onHover: (ev, t) => { const html = (isRight ? current?.tipRight : current?.tip)?.(t, ctx); if (html) showTooltip(ev, html); },
        onLeave: hideTooltip,
      });
      return { map: m, panel: panelEl, theatres: th };
    };
    const l = side(splitEl.querySelector(".split-map-l"), splitEl.querySelector(".split-panel-l"), false);
    const r = side(splitEl.querySelector(".split-map-r"), splitEl.querySelector(".split-panel-r"), true);
    split = {
      // left side drives the shared timeline; the right side follows it
      left: { ...ctx, ...l },
      right: { ...ctx, ...r, setYear: () => {}, setRange: () => {} },
    };
    return split;
  }
  function setLayout(isSplit) {
    el.querySelector(".stage").classList.toggle("is-split", isSplit);
    el.closest(".view")?.classList.toggle("wide", isSplit);
    splitEl.hidden = !isSplit;
    mapEl.hidden = panel.hidden = isSplit;
    if (isSplit) ensureSplit();
  }
  let range = years;
  const clamp = y => Math.max(range[0], Math.min(range[1], y));

  /** Limit the timeline to [from, to] (null = all years) and keep the year inside it. */
  function setRange(r) {
    range = r || years;
    slider.min = range[0];
    slider.max = range[1];
    state.year = clamp(state.year);
    slider.value = out.value = state.year;
  }

  function syncUrl() {
    const p = new URLSearchParams(current.params?.() || {});
    if (current.usesYear) p.set("year", state.year);
    const q = p.toString();
    const hash = `#${current.id}${q ? `?${q}` : ""}`;
    history.replaceState(null, "", hash);
    // the tab returns to this view as it was left (cohort year, people, score, …)
    el.querySelector(`.mode-bar a[data-mode="${current.id}"]`)?.setAttribute("href", hash);
  }

  function setYear(y) {
    state.year = clamp(y);
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
      setRange(null);
      el.querySelectorAll(".mode-bar a").forEach(a =>
        a.dataset.mode === next.id ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
      timeline.classList.toggle("off", !next.usesYear);
      if (!next.usesYear) stop();
      slider.disabled = playBtn.disabled = !next.usesYear;
      setLayout(!!next.split);
      next.enter(ctx);
      (next.split ? [split.left.panel, split.right.panel] : [panel]).forEach(p => p.animate([{ opacity: 0, transform: "translateY(6px)" }, { opacity: 1, transform: "none" }],
        { duration: 280, easing: "ease-out" }));
    } else if (current.onParams) {
      current.onParams(ctx);
    } else {
      current.setYear?.(ctx, state.year);
    }
    syncUrl();
  }

  slider.addEventListener("input", () => { stop(); setYear(+slider.value); });

  // play through the years
  const YEAR_MS = 1000;   // play speed: one year per second
  let timer = null;
  function stop() { if (timer) { timer.stop(); timer = null; playBtn.textContent = "▶ Play"; } }
  playBtn.addEventListener("click", () => {
    if (timer) return stop();
    playBtn.textContent = "❚❚ Pause";
    let last = 0;
    timer = d3.timer(elapsed => {
      if (elapsed - last < YEAR_MS) return;
      last = elapsed;
      setYear(state.year >= range[1] ? range[0] : state.year + 1);
    });
  });

  return { go, ctx, get mode() { return current?.id; } };
}
