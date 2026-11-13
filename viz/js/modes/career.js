// Career mode: up to four people's careers as transit lines from theatre to theatre, in opening
// order, on the shared map. Each person keeps one colour and dash pattern (slot) for as long as
// they are selected. Stations grow with the number of shows at a theatre; a gold halo marks a
// reunion (back with a collaborator after REUNION_GAP+ years apart). The timeline covers every
// year in the data: each line is drawn up to the chosen year, the rest of the route dotted.
//
// Starts blank. The first person chosen is the anchor: others can be added only if they worked
// with the anchor on PARTNER_MIN+ shows, so every comparison is between related people.
//
// URL: #career?p=Q269094,Q725828&year=1943  (no year = whole careers; p= empty = blank)
import * as d3 from "https://cdn.jsdelivr.net/npm/d3@7.9.0/+esm";
import { esc, showTooltip, hideTooltip } from "../tooltip.js";

const PARTNER_MIN = 2;  // shows together needed to be offered as a comparison with the anchor
const NETWORK = "strict";
const REUNION_GAP = 5;  // years apart before working together again counts as a reunion (the cutoff step)
const MAX_PEOPLE = 4;   // the palette has four validated slots (light and dark), see css --person-N
const lifespan = p => (p.born || p.died ? ` (${p.born ?? "?"}–${p.died ?? ""})` : "");
const roleText = roles => roles.map(r => r.replace(/_/g, " ")).join(", ");
const curve = d3.line().curve(d3.curveCatmullRom.alpha(0.5));

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
  const stations = d3.groups(shows.filter(s => s.theatre), s => s.theatre.id).map(([, list]) => ({
    theatre: list[0].theatre, shows: list,
  }));
  const path = [];   // { theatre, year } per stop, skipping back-to-back repeats
  for (const s of shows) if (s.theatre && path[path.length - 1]?.theatre !== s.theatre) path.push({ theatre: s.theatre, year: s.year });
  const span = shows.length ? [shows[0].year, shows[shows.length - 1].year] : null;
  return { shows, stations, path, span };
}

/** People who worked with personId on PARTNER_MIN+ shows: Map id -> shows together, most first. */
const partnerCache = new Map();
function partnersOf(db, personId) {
  if (partnerCache.has(personId)) return partnerCache.get(personId);
  const n = new Map();
  for (const c of db.career(personId, NETWORK))
    for (const m of new Set((db.creditsByShow.get(c.show) || []).filter(m => m[NETWORK]).map(m => m.person)))
      if (m !== personId) n.set(m, (n.get(m) || 0) + 1);
  const out = new Map([...n].filter(([, k]) => k >= PARTNER_MIN).sort((a, b) => b[1] - a[1]));
  partnerCache.set(personId, out);
  return out;
}

export function careerMode() {
  let root = null, offZoom = null, ctxRef = null;
  let people = [];            // [{ id, slot, career, g, grow, done, current }] in selection order
  let year = Infinity;        // the timeline year
  let hovered = null;         // theatre id under the pointer (map or list)
  let lastSelection = [];     // remembered when leaving the mode and coming back via the mode bar

  const ids = () => people.map(p => p.id);
  /** Reunions that count for the gold marks: with one person, every reunion; with two or more,
   *  only reunions between the people selected (so Rodgers + Hammerstein hides Rodgers-Hart). */
  const reunions = s => people.length > 1 ? s.reunited.filter(m => ids().includes(m)) : s.reunited;
  const hrefFor = list => `#career?p=${list.join(",")}`;
  const stationR = d => 4 + 2.2 * Math.sqrt(d.shows.length);
  /** Surname for compact labels, skipping suffixes ("Oscar Hammerstein II" -> "Hammerstein"). */
  const shortName = id => {
    const parts = (ctxRef.db.personById.get(id)?.name ?? id).replace(/,/g, "").split(" ");
    while (parts.length > 1 && /^(II|III|IV|Jr\.?|Sr\.?)$/i.test(parts[parts.length - 1])) parts.pop();
    return parts[parts.length - 1];
  };

  // --- map ------------------------------------------------------------------------------------

  /** Pixel offset per person so lines sharing a street run side by side, transit-map style. */
  function offset(i) {
    const k = (i - (people.length - 1) / 2) * 3.5;
    return [k, k];
  }

  function lineD(person) {
    const xy = t => ctxRef.map.xy(t.lat, t.lon);
    let pts = person.career.path.filter(p => p.year <= year).map(p => xy(p.theatre));
    if (person.grow < 1 && pts.length > 1) {   // drawing animation: a growing prefix of the line
      const t = person.grow * (pts.length - 1), k = Math.floor(t);
      const cut = pts.slice(0, k + 1);
      if (k < pts.length - 1) cut.push(d3.interpolate(pts[k], pts[k + 1])(t - k));
      pts = cut;
    }
    return curve(pts);
  }

  function place() {
    if (!root) return;
    const tr = ctxRef.map.transform;
    const xy = t => ctxRef.map.xy(t.lat, t.lon);
    people.forEach((p, i) => {
      const [dx, dy] = offset(i);
      p.g.attr("transform", `translate(${dx},${dy})`);
      p.g.select("path.career-route").attr("d", curve(p.career.path.map(q => xy(q.theatre))));
      p.g.select("path.career-line").attr("d", lineD(p));
      p.g.selectAll("circle.station, circle.halo").attr("cx", d => xy(d.theatre)[0]).attr("cy", d => xy(d.theatre)[1]);
      p.g.selectAll("text.station-label")
        .attr("x", d => xy(d.theatre)[0]).attr("y", d => xy(d.theatre)[1])
        .attr("display", d => {
          if (p.labelOwner && !p.labelOwner(d.theatre.id)) return "none";
          const nowHere = people.some(q => q.current === d.theatre);
          return d.theatre.id === hovered || nowHere || tr.k >= 4 ? null : "none";
        });
    });
  }

  function drawPerson(person, animate) {
    const g = person.g;
    g.selectAll("*").interrupt().remove();
    g.attr("class", `person s${person.slot}`);
    g.append("path").attr("class", "career-route");
    const line = g.append("path").attr("class", "career-line");
    const st = g.selectAll("g.stop").data(person.career.stations, d => d.theatre.id).join("g").attr("class", "stop");
    st.append("circle").attr("class", "halo").attr("r", d => stationR(d) + 3.5);
    st.append("circle").attr("class", "station").attr("r", animate ? 0 : stationR)
      .on("pointerenter", (ev, d) => highlight(d.theatre.id))
      .on("pointermove", (ev, d) => showTooltip(ev, tipHtml(d.theatre)))
      .on("pointerleave", () => { highlight(null); hideTooltip(); });
    st.append("text").attr("class", "station-label").attr("dx", d => stationR(d) + 5).attr("dy", "0.35em");

    person.grow = animate ? 0 : 1;
    if (animate) {
      line.transition().duration(Math.min(2200, 400 + 70 * person.career.path.length)).ease(d3.easeCubicInOut)
        .tween("grow", () => t => { person.grow = t; line.attr("d", lineD(person)); })
        .on("end interrupt", () => { person.grow = 1; line.attr("d", lineD(person)); });
      g.selectAll("circle.station").transition().delay((d, i) => 200 + i * 60).duration(300).attr("r", stationR);
    }
  }

  /** Show every career up to year y. */
  function applyYear(y, { scroll = true } = {}) {
    year = y;
    for (const p of people) {
      const done = p.career.shows.filter(s => s.year <= y);
      p.done = done.length;
      p.current = [...done].reverse().find(s => s.theatre)?.theatre ?? null;
      p.g.selectAll("g.stop")
        .classed("future", d => d.shows[0].year > y)
        .classed("reunion", d => d.shows.some(s => s.year <= y && reunions(s).length))
        .classed("current", d => d.theatre === p.current);
      p.g.selectAll("g.stop").filter(d => d.theatre === p.current).raise();
    }
    // one label per theatre: drawn by the first selected person with a stop there; at someone's
    // current stop it names everyone currently there ("Rodgers, Hammerstein · St. James Theatre")
    const owner = new Map(), hereNow = new Map();
    for (const p of people) {
      for (const st of p.career.stations) if (!owner.has(st.theatre.id)) owner.set(st.theatre.id, p);
      if (p.current) hereNow.set(p.current.id, [...(hereNow.get(p.current.id) || []), shortName(p.id)]);
    }
    for (const p of people) {
      p.labelOwner = id => owner.get(id) === p;
      p.g.selectAll("text.station-label").text(d => {
        const names = hereNow.get(d.theatre.id);
        return people.length > 1 && names ? `${names.join(", ")} · ${d.theatre.name}` : d.theatre.name;
      });
    }
    place();
    updatePanelYear(scroll);
  }

  function highlight(theatreId) {
    hovered = theatreId;
    root?.selectAll("g.stop").classed("active", d => d.theatre.id === theatreId);
    place();
    ctxRef.panel.querySelectorAll(".career-list li").forEach(li =>
      li.classList.toggle("active", theatreId != null && li.dataset.theatre === theatreId));
  }

  function tipHtml(t) {
    const rows = people.flatMap(p => p.career.shows.filter(s => s.theatre?.id === t.id)
      .map(s => `<div><span class="swatch s${p.slot}"></span>${s.year} · <em>${esc(s.showObj?.title)}</em>${people.length > 1 ? ` · ${esc(shortName(p.id))}` : ""}${reunions(s).length ? " · reunion" : ""}</div>`));
    return `<div class="t-title">${esc(t.name)}</div>` + (rows.length ? rows.join("") : `<div class="t-sub">No show here by the people selected</div>`);
  }

  // --- panel ----------------------------------------------------------------------------------

  function fillPanel(ctx) {
    const { db, panel } = ctx;
    const nameOf = id => db.personById.get(id)?.name ?? id;
    const multi = people.length > 1;
    // collaborator names add that person when they worked with the anchor on PARTNER_MIN+ shows
    const partners = people.length ? partnersOf(db, people[0].id) : new Map();
    const full = people.length >= MAX_PEOPLE;
    const linkTo = id => {
      if (ids().includes(id)) return `<span class="selected">${esc(nameOf(id))}</span>`;
      if (!partners.has(id) || full) return esc(nameOf(id));
      return `<a href="${hrefFor([...ids(), id])}" title="Add to the comparison">${esc(nameOf(id))}</a>`;
    };
    const names = (list, extra = () => "", max = 5) => list.slice(0, max).map(id => linkTo(id) + extra(id)).join(", ")
      + (list.length > max ? ` and ${list.length - max} more` : "");

    // pairs of selected people who share shows
    const together = [];
    for (let i = 0; i < people.length; i++) for (let j = i + 1; j < people.length; j++) {
      const a = new Set(people[i].career.shows.map(s => s.show));
      const n = people[j].career.shows.filter(s => a.has(s.show)).length;
      if (n) together.push(`${esc(shortName(people[i].id))} and ${esc(shortName(people[j].id))}: <strong>${n}</strong> show${n === 1 ? "" : "s"} together`);
    }

    // one row per show, listing every selected person on it
    const rows = d3.groups(people.flatMap(p => p.career.shows.map(s => ({ p, s }))), d => d.s.show)
      .map(([, list]) => list)
      .sort((a, b) => a[0].s.year - b[0].s.year || people.indexOf(a[0].p) - people.indexOf(b[0].p));

    if (!people.length) return fillBlank(ctx);
    const anchor = shortName(people[0].id);
    const reunitedWith = new Set(people[0].career.shows.flatMap(s => s.reunited));
    const choices = [...partners].filter(([id]) => !ids().includes(id));
    const compare = !partners.size
      ? `<p class="hint">${esc(nameOf(people[0].id))} never worked with anyone on ${PARTNER_MIN}+ shows in our data, so there is no one to compare with.</p>`
      : `<label class="picker"><span>Compare with</span>
          <select ${full || !choices.length ? "disabled" : ""}>
            <option value="">${full ? `Up to ${MAX_PEOPLE} people: remove someone first`
              : choices.length ? `Add a collaborator (${choices.length})` : "Everyone is already on the map"}</option>
            ${choices.map(([id, k]) => `<option value="${id}">${esc(nameOf(id))} · ${k} shows together${reunitedWith.has(id) ? " · reunion" : ""}</option>`).join("")}
          </select>
        </label>
        <p class="hint">People ${esc(anchor)} worked with on ${PARTNER_MIN}+ shows, most shows first.</p>`;
    panel.innerHTML = `
      <div class="people-chips">
        ${people.map(p => {
          const q = db.personById.get(p.id), c = p.career;
          const nRe = c.shows.filter(s => reunions(s).length).length;
          return `<div class="chip s${p.slot}">
            <svg class="chip-line" width="28" height="8" aria-hidden="true"><line x1="1" y1="4" x2="27" y2="4"></line></svg>
            <div class="chip-body">
              <div class="chip-name">${esc(q?.name ?? p.id)}</div>
              <div class="chip-sub">${q?.born ? `${q.born}–${q.died ?? ""}` : ""}${q?.birthplace ? ` · born in ${esc(q.birthplace)}` : ""}${q?.wiki ? ` · <a href="${esc(q.wiki)}" target="_blank" rel="noopener">Wikipedia</a>` : ""}</div>
              <div class="chip-stats">${c.shows.length} shows · ${c.stations.length} theatres · ${nRe} reunion${nRe === 1 ? "" : "s"}
                <span class="career-progress" data-id="${p.id}"></span></div>
            </div>
            <a class="chip-remove" href="${hrefFor(ids().filter(x => x !== p.id))}" aria-label="Remove ${esc(q?.name ?? p.id)}" title="Remove">×</a>
          </div>`;
        }).join("")}
      </div>
      ${compare}
      ${together.length ? `<p class="together">${together.join("<br>")}</p>` : ""}
      <div class="legend">
        <span><span class="key station"></span>theatre</span>
        <span><span class="key current"></span>latest show by the timeline year</span>
        <span><span class="key reunion"></span>reunion: back with ${multi ? "someone selected" : "a collaborator"} after ${REUNION_GAP}+ years apart</span>
      </div>
      <ol class="career-list">
        ${rows.map(list => {
          const { s } = list[0];
          return `<li data-theatre="${s.theatre?.id ?? ""}" data-year="${s.year}" class="${list.some(d => reunions(d.s).length) ? "reunion" : ""} ${s.theatre ? "" : "no-venue"}">
            <span class="yr">${s.year}</span>
            <div><strong>${esc(s.showObj?.title ?? s.show)}</strong>${multi ? "" : ` <span class="roles">${esc(roleText(s.roles))}</span>`}
              <div class="where">${s.theatre ? esc(s.theatre.name) : "theatre unknown"}</div>
              ${list.map(({ p, s: c }) => `
                ${multi ? `<div class="who"><span class="swatch s${p.slot}"></span>${esc(shortName(p.id))} <span class="roles">${esc(roleText(c.roles))}</span></div>` : ""}
                ${reunions(c).length ? `<div class="again">reunited with ${names(reunions(c), m => ` after ${c.gaps.get(m)} yrs`)}</div>` : ""}
                ${!multi && c.continuing.length ? `<div class="still">still with ${names(c.continuing)}</div>` : ""}`).join("")}
            </div>
          </li>`;
        }).join("")}
      </ol>
      ${rows.length ? "" : `<p class="hint">No credits in the ${NETWORK} network for this selection.</p>`}`;

    panel.querySelector(".picker select")?.addEventListener("change", ev => {
      if (ev.target.value) location.hash = hrefFor([...ids(), ev.target.value]);
    });
    panel.querySelectorAll(".career-list li").forEach(li => {
      li.addEventListener("pointerenter", () => li.dataset.theatre && highlight(li.dataset.theatre));
      li.addEventListener("pointerleave", () => highlight(null));
    });
  }

  /** Blank state: search everyone with credits, plus a few prolific people to start from. */
  function fillBlank(ctx) {
    const { db, panel } = ctx;
    const withCredits = db.people.filter(q => db.career(q.id, NETWORK).length);
    const top = [...withCredits].sort((a, b) => db.career(b.id, NETWORK).length - db.career(a.id, NETWORK).length).slice(0, 8);
    panel.innerHTML = `
      <h2>Career paths</h2>
      <p class="sub">Choose a person to draw their career from theatre to theatre. Then compare it with
        up to ${MAX_PEOPLE - 1} people they worked with again (${PARTNER_MIN}+ shows together).</p>
      <label class="picker"><span>Person</span>
        <input type="search" list="career-people" placeholder="Type a name…" autocomplete="off">
      </label>
      <datalist id="career-people">${withCredits.map(q => `<option value="${esc(q.name + lifespan(q))}"></option>`).join("")}</datalist>
      <p class="hint">Or start with one of the most prolific:</p>
      <ul class="suggestions">${top.map(q => `<li><a href="${hrefFor([q.id])}">${esc(q.name)}</a>
        <span class="roles">${db.career(q.id, NETWORK).length} shows</span></li>`).join("")}</ul>`;
    const byLabel = new Map(withCredits.map(q => [q.name + lifespan(q), q.id]));
    const input = panel.querySelector(".picker input");
    input.addEventListener("change", () => {
      const id = byLabel.get(input.value) ?? withCredits.find(q => q.name.toLowerCase() === input.value.trim().toLowerCase())?.id;
      if (id) location.hash = hrefFor([id]);
    });
  }

  function updatePanelYear(scroll) {
    const panel = ctxRef.panel;
    for (const p of people) {
      const el = panel.querySelector(`.career-progress[data-id="${p.id}"]`);
      if (el) el.textContent = p.career.span && year < p.career.span[1] ? `By ${year}: ${p.done} of ${p.career.shows.length}` : "";
    }
    const atEnd = people.every(p => !p.career.span || year >= p.career.span[1]);
    const latest = d3.max(people.flatMap(p => p.career.shows.filter(s => s.year <= year).map(s => s.year)));
    let first = null;
    panel.querySelectorAll(".career-list li").forEach(li => {
      const ly = +li.dataset.year;
      li.classList.toggle("future", ly > year);
      const cur = !atEnd && ly === latest;
      li.classList.toggle("current", cur);
      if (cur && !first) first = li;
    });
    // scroll only the panel (scrollIntoView would also move the page)
    if (scroll && first) panel.scrollTo({ top: first.offsetTop - panel.clientHeight / 2 + first.offsetHeight / 2, behavior: "smooth" });
  }

  // --- selection ------------------------------------------------------------------------------

  /** Make the selection match `wanted` (list of ids): keep existing people (and their colours),
   *  add new ones in free slots with a drawing animation, fade out the rest. */
  function select(ctx, wanted, { keepYear = false } = {}) {
    const before = people;
    const keep = before.filter(p => wanted.includes(p.id));
    for (const p of before) if (!keep.includes(p)) p.g.transition().duration(250).attr("opacity", 0).remove();
    const added = [];
    for (const id of wanted) {
      if (keep.some(p => p.id === id)) continue;
      const used = new Set(keep.map(p => p.slot));
      const slot = [0, 1, 2, 3].find(s => !used.has(s));
      const person = { id, slot, career: buildCareer(ctx.db, id), g: root.append("g") };
      keep.push(person);
      added.push(person);
    }
    // if the timeline was showing whole careers, keep doing so for the new selection
    const endOf = list => d3.max(list, p => p.career.span?.[1]);
    // (from a blank slate, a newly chosen person also starts with their whole career)
    const wasAtEnd = before.length ? year >= endOf(before) : !keepYear;
    people = wanted.map(id => keep.find(p => p.id === id));
    if (wasAtEnd && endOf(people) > year) { year = endOf(people); ctx.state.year = year; ctx.setYear(year); }
    for (const p of added) drawPerson(p, true);
    fillPanel(ctx);
    applyYear(year, { scroll: false });
    const pts = people.flatMap(p => p.career.stations.map(s => [s.theatre.lat, s.theatre.lon]));
    ctx.map.zoomTo(pts, { pad: 120, duration: 900 });
    lastSelection = ids();
    if (before.length) ctx.panel.animate([{ opacity: 0.4 }, { opacity: 1 }], { duration: 250 });
  }

  /** The selection named in the URL: the first person is the anchor; anyone else who isn't one
   *  of the anchor's partners is dropped (e.g. after the anchor was removed). No p = last time. */
  function wantedFromUrl(ctx) {
    if (!ctx.state.params.has("p")) return lastSelection;
    const raw = ctx.state.params.get("p").split(",").map(s => s.trim()).filter(id => ctx.db.personById.has(id));
    const [anchor, ...rest] = [...new Set(raw)];
    if (!anchor) return [];
    const partners = partnersOf(ctx.db, anchor);
    return [anchor, ...rest.filter(id => partners.has(id))].slice(0, MAX_PEOPLE);
  }

  return {
    id: "career", label: "Career", caption: "compare careers", usesYear: true,

    enter(ctx) {
      ctxRef = ctx;
      ctx.theatres.dots.attr("class", "t theatre faint")
        .transition("mode").duration(500).attr("r", 3).attr("opacity", 0.35);
      root = ctx.map.layer("overlay").append("g").attr("class", "mode-career");
      offZoom = ctx.map.onZoom(place);
      people = [];
      const wanted = wantedFromUrl(ctx);
      // whole careers unless the link names a year
      if (!ctx.state.params.get("year")) {
        const end = d3.max(wanted, id => d3.max(ctx.db.career(id, NETWORK), c => c.year));
        if (end) ctx.setYear(end);
      }
      year = ctx.state.year;
      select(ctx, wanted, { keepYear: true });
    },

    /** Same mode, new URL: people added or removed, or the year changed (back/forward). */
    onParams(ctx) {
      const wanted = wantedFromUrl(ctx);
      if (wanted.join() !== ids().join()) select(ctx, wanted);
      else applyYear(ctx.state.year);
    },

    setYear(ctx, y) { if (root) applyYear(y); },

    exit() {
      offZoom?.();
      root?.transition().duration(250).attr("opacity", 0).remove();
      root = null;
      people = [];
    },

    params: () => ({ p: ids().join(",") }),
    tip: t => tipHtml(t),
  };
}
