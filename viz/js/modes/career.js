// Career mode: one person's career as a transit line from theatre to theatre, in opening order.
// Each theatre is a station (bigger for more shows there); gold stations are reunions, where the
// person worked again with someone from an earlier show. The panel lists the shows; collaborator
// names switch the map to that person's career.
import * as d3 from "https://cdn.jsdelivr.net/npm/d3@7.9.0/+esm";
import { esc, showTooltip, hideTooltip } from "../tooltip.js";

const DEFAULT_PERSON = "Q269094";  // Richard Rodgers
const NETWORK = "strict";
const REUNION_GAP = 5;  // years apart before working together again counts as a reunion (the cutoff step)
const lifespan = p => (p.born || p.died ? ` (${p.born ?? "?"}–${p.died ?? ""})` : "");
const roleText = roles => roles.map(r => r.replace(/_/g, " ")).join(", ");

/** The person's shows in order, each with its theatre and its earlier collaborators, split into
 *  reunions (back together after REUNION_GAP or more years apart) and continuing partners. */
function buildCareer(db, personId) {
  const credits = db.career(personId, NETWORK);
  const last = new Map();   // collaborator id -> year of the most recent shared show
  const shows = [];
  for (const [year, group] of d3.groups(credits, c => c.year)) {
    const thisYear = [];
    for (const c of group) {
      const mates = [...new Set((db.creditsByShow.get(c.show) || [])
        .filter(m => m.person !== personId && m[NETWORK]).map(m => m.person))];
      const before = mates.filter(m => last.has(m) && last.get(m) < year);
      const reunited = before.filter(m => year - last.get(m) >= REUNION_GAP);
      const continuing = before.filter(m => year - last.get(m) < REUNION_GAP);
      shows.push({ ...c, showObj: db.showById.get(c.show), theatre: db.theatreOf(c.show), reunited, continuing,
        gaps: new Map(reunited.map(m => [m, year - last.get(m)])) });
      thisYear.push(...mates);
    }
    for (const m of thisYear) last.set(m, year);
  }
  // stations: one per theatre, in order of first visit
  const stations = d3.groups(shows.filter(s => s.theatre), s => s.theatre.id).map(([, list]) => ({
    theatre: list[0].theatre, shows: list, reunion: list.some(s => s.reunited.length > 0),
  }));
  // the line: theatres in show order, skipping repeats of the same theatre back to back
  const path = [];   // { theatre, year } for each stop, year = first show of that stop
  for (const s of shows) if (s.theatre && path[path.length - 1]?.theatre !== s.theatre) path.push({ theatre: s.theatre, year: s.year });
  const span = shows.length ? [shows[0].year, shows[shows.length - 1].year] : null;
  return { shows, stations, path, span };
}

export function careerMode() {
  let g = null, offZoom = null, career = null, personId = null, ctxRef = null;
  let year = Infinity;          // the timeline year: the career is drawn up to here
  let currentTheatre = null;    // where the latest show by `year` opened
  const curve = d3.line().curve(d3.curveCatmullRom.alpha(0.5));

  function place(tr = ctxRef.map.transform) {
    if (!g || !career) return;
    const xy = t => ctxRef.map.xy(t.lat, t.lon);
    g.select("path.career-route").attr("d", curve(career.path.map(p => xy(p.theatre))));
    g.select("path.career-line").attr("d", curve(career.path.filter(p => p.year <= year).map(p => xy(p.theatre))));
    g.selectAll("circle.station").attr("cx", d => xy(d.theatre)[0]).attr("cy", d => xy(d.theatre)[1]);
    g.selectAll("text.station-label")
      .attr("x", d => xy(d.theatre)[0]).attr("y", d => xy(d.theatre)[1])
      .attr("display", d => (tr.k >= 4 || d.theatre === currentTheatre ? null : "none"));
  }

  /** Show the career up to year y: travelled line, reached stations, current stop, list state. */
  function applyYear(y, { scroll = true } = {}) {
    year = y;
    const done = career.shows.filter(s => s.year <= y);
    const latest = done.length ? done[done.length - 1].year : null;
    currentTheatre = [...done].reverse().find(s => s.theatre)?.theatre ?? null;
    g.select("path.career-line").interrupt().attr("stroke-dasharray", null).attr("stroke-dashoffset", null);
    g.selectAll("circle.station")
      .classed("future", d => d.shows[0].year > y)
      .classed("reunion", d => d.shows.some(s => s.year <= y && s.reunited.length))
      .classed("current", d => d.theatre === currentTheatre);
    g.selectAll("circle.station").filter(d => d.theatre === currentTheatre).raise();
    place();

    const atEnd = !career.span || y >= career.span[1];
    const prog = ctxRef.panel.querySelector(".career-progress");
    if (prog) prog.textContent = atEnd ? "" : `By ${y}: ${done.length} of ${career.shows.length} shows`;
    let first = null;
    ctxRef.panel.querySelectorAll(".career-list li").forEach(li => {
      const ly = +li.dataset.year;
      li.classList.toggle("future", ly > y);
      const cur = !atEnd && ly === latest;
      li.classList.toggle("current", cur);
      if (cur && !first) first = li;
    });
    // scroll only the panel (scrollIntoView would also move the page)
    if (scroll && first) {
      const panel = ctxRef.panel;
      panel.scrollTo({ top: first.offsetTop - panel.clientHeight / 2 + first.offsetHeight / 2, behavior: "smooth" });
    }
  }

  function draw(ctx) {
    const { db, map } = ctx;
    career = buildCareer(db, personId);
    g.selectAll("*").interrupt().remove();

    // the timeline covers this career; show all of it unless the link names a year
    const urlYear = +ctx.state.params.get("year");
    ctx.setRange(career.span);
    if (career.span) {
      const y = urlYear >= career.span[0] && urlYear <= career.span[1] ? urlYear : career.span[1];
      ctx.state.year = y;
      ctx.setRange(career.span);   // refreshes the slider with the new year
    }
    year = career.span ? ctx.state.year : Infinity;

    g.append("path").attr("class", "career-route");
    const line = g.append("path").attr("class", "career-line");
    const r = d => 4 + 2.2 * Math.sqrt(d.shows.length);
    g.selectAll("circle.station").data(career.stations, d => d.theatre.id).join("circle")
      .attr("class", d => `station${d.reunion ? " reunion" : ""}`).attr("r", 0)
      .on("pointerenter", (ev, d) => highlight(d.theatre.id))
      .on("pointermove", (ev, d) => showTooltip(ev, tipHtml(d.theatre)))
      .on("pointerleave", () => { highlight(null); hideTooltip(); });
    g.selectAll("text.station-label").data(career.stations, d => d.theatre.id).join("text")
      .attr("class", "station-label").attr("dx", d => r(d) + 4).attr("dy", "0.35em")
      .text(d => d.theatre.name);
    fillPanel(ctx);
    applyYear(year, { scroll: false });

    // draw the line, then pop the stations in along it
    const len = line.node().getTotalLength();
    line.attr("stroke-dasharray", `${len} ${len}`).attr("stroke-dashoffset", len)
      .transition().duration(Math.min(2200, 400 + 60 * career.path.length)).ease(d3.easeCubicInOut)
      .attr("stroke-dashoffset", 0)
      .on("end", () => line.attr("stroke-dasharray", null).attr("stroke-dashoffset", null));
    g.selectAll("circle.station").transition().delay((d, i) => 200 + i * 60).duration(300).attr("r", r);

    map.zoomTo(career.stations.map(s => [s.theatre.lat, s.theatre.lon]), { pad: 120, duration: 900 });
  }

  function highlight(theatreId) {
    g?.selectAll("circle.station").classed("active", d => d.theatre.id === theatreId);
    g?.selectAll("text.station-label").attr("display", d =>
      d.theatre.id === theatreId || ctxRef.map.transform.k >= 4 ? null : "none");
    ctxRef.panel.querySelectorAll(".career-list li").forEach(li =>
      li.classList.toggle("active", theatreId != null && li.dataset.theatre === theatreId));
  }

  function fillPanel(ctx) {
    const { db, panel } = ctx;
    const p = db.personById.get(personId);
    const nTheatres = career.stations.length, nReunion = career.shows.filter(s => s.reunited.length).length;
    const options = db.people.map(q => `<option value="${esc(q.name + lifespan(q))}"></option>`).join("");
    const nameOf = id => db.personById.get(id)?.name ?? id;
    const people = (ids, extra = () => "", max = 5) => ids.slice(0, max)
      .map(id => `<a href="#career?p=${id}">${esc(nameOf(id))}</a>${extra(id)}`).join(", ")
      + (ids.length > max ? ` and ${ids.length - max} more` : "");

    panel.innerHTML = `
      <label class="picker"><span>Person</span>
        <input type="search" list="career-people" placeholder="Type a name…" value="${esc(p ? p.name + lifespan(p) : "")}">
      </label>
      <datalist id="career-people">${options}</datalist>
      <h2>${esc(p?.name ?? personId)}</h2>
      <p class="sub">${p?.born ? `${p.born}–${p.died ?? ""}` : ""}${p?.birthplace ? ` · born in ${esc(p.birthplace)}` : ""}
        ${p?.wiki ? ` · <a href="${esc(p.wiki)}" target="_blank" rel="noopener">Wikipedia</a>` : ""}</p>
      <p class="career-stats"><strong>${career.shows.length}</strong> shows ·
        <strong>${nTheatres}</strong> theatre${nTheatres === 1 ? "" : "s"} ·
        <strong>${nReunion}</strong> reunion${nReunion === 1 ? "" : "s"}
        <span class="career-progress"></span></p>
      <div class="legend">
        <span><span class="key line"></span>career, in order</span>
        <span><span class="key station"></span>theatre</span>
        <span><span class="key current"></span>latest show by the timeline year</span>
        <span><span class="key reunion"></span>reunion: back with a collaborator after ${REUNION_GAP}+ years apart</span>
      </div>
      <ol class="career-list">
        ${career.shows.map(s => `
          <li data-theatre="${s.theatre?.id ?? ""}" data-year="${s.year}" class="${s.reunited.length ? "reunion" : ""} ${s.theatre ? "" : "no-venue"}">
            <span class="yr">${s.year}</span>
            <div><strong>${esc(s.showObj?.title ?? s.show)}</strong> <span class="roles">${esc(roleText(s.roles))}</span>
              <div class="where">${s.theatre ? esc(s.theatre.name) : "theatre unknown"}</div>
              ${s.reunited.length ? `<div class="again">reunited with ${people(s.reunited, m => ` after ${s.gaps.get(m)} yrs`)}</div>` : ""}
              ${s.continuing.length ? `<div class="still">still with ${people(s.continuing)}</div>` : ""}
            </div>
          </li>`).join("")}
      </ol>
      ${career.shows.length ? "" : `<p class="hint">No credits in the ${NETWORK} network for this person.</p>`}`;

    const byLabel = new Map(db.people.map(q => [q.name + lifespan(q), q.id]));
    const input = panel.querySelector(".picker input");
    input.addEventListener("change", () => {
      const id = byLabel.get(input.value) ?? db.people.find(q => q.name.toLowerCase() === input.value.trim().toLowerCase())?.id;
      if (id && id !== personId) location.hash = `#career?p=${id}`;
    });
    panel.querySelectorAll(".career-list li").forEach(li => {
      li.addEventListener("pointerenter", () => li.dataset.theatre && highlight(li.dataset.theatre));
      li.addEventListener("pointerleave", () => highlight(null));
    });
  }

  function tipHtml(t) {
    const here = career?.shows.filter(s => s.theatre?.id === t.id) || [];
    return `<div class="t-title">${esc(t.name)}</div>` + (here.length
      ? here.map(s => `<div>${s.year} · <em>${esc(s.showObj?.title)}</em>${s.reunited.length ? " · reunion" : ""}</div>`).join("")
      : `<div class="t-sub">${esc(ctxRef.db.personById.get(personId)?.name)} has no show here</div>`);
  }

  function fadeTheatres(ctx) {
    ctx.theatres.dots.attr("class", "t theatre faint")
      .transition("mode").duration(500).attr("r", 3).attr("opacity", 0.35);
  }

  return {
    id: "career", label: "Career", caption: "one person's path", usesYear: true,

    enter(ctx) {
      ctxRef = ctx;
      personId = ctx.state.params.get("p") || personId || DEFAULT_PERSON;
      if (!ctx.db.personById.has(personId)) personId = DEFAULT_PERSON;
      fadeTheatres(ctx);
      g = ctx.map.layer("overlay").append("g").attr("class", "mode-career");
      offZoom = ctx.map.onZoom(place);
      draw(ctx);
    },

    /** Same mode, new URL parameters: another person. */
    onParams(ctx) {
      const next = ctx.state.params.get("p");
      if (!next || next === personId || !ctx.db.personById.has(next)) {
        if (career?.span) applyYear(ctx.state.year);
        return;
      }
      personId = next;
      draw(ctx);
      ctx.panel.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 250 });
    },

    exit(ctx) {
      offZoom?.();
      g?.transition().duration(250).attr("opacity", 0).remove();
      g = null;
    },

    setYear(ctx, y) { if (career?.span) applyYear(y); },

    params: () => ({ p: personId }),

    tip: t => tipHtml(t),
  };
}
