// Collaboration graph tab (prototype, Trang): Broadway's collaboration network over time, without
// the map. People are nodes; a line joins two people who shared a show. Strict credits, like the
// other views.
//
// The timeline year Y shows the 10-year window [Y-9, Y] (W = 10, the models' window), or every
// show up to Y ("everything so far"). Playing moves one year at a time: people already on screen
// keep their place, newcomers appear next to a collaborator who is already there.
//
// Encodings (what decides the sizes):
//   node area   "shows" (default): the person's shows in the window, so big = prolific.
//               "lines": the person's distinct collaborators in the window. A 15-person team gives
//               everyone 14 lines from one show, so this mostly measures team size.
//               radius = 2.5 + 2.2 * sqrt(shows)  or  2.5 + 2.2 * sqrt(lines / 2)
//   line width  shows the pair did together inside the window: 0.9 px for one, +1.4 px per extra
//               show (+0.8 px if gold).
//   line colour gold when the pair had done 2+ shows together by year Y (also counting shows
//               before the window): repeat collaborators. Grey otherwise.
//   dashed ring the person's first Broadway credit (in our data) is in year Y.
//   node colour none, or the person's strongest BigCLAM community in the model window nearest to
//               [Y-9, Y] (db.models, step 11); the 7 largest communities get colours, the rest grey.
//
// Position: a force layout (linked people attract, everyone repels), so teams form clusters and
// people who bridge teams sit between them. Distances are only roughly meaningful, and the motion
// after a change is the layout settling.
//
// Focus view: clicking a person (or a line) pauses the layout and glides, without bounce, the
// selection to the centre and their collaborators to evenly spaced spots on a ring around it.
// Everyone else stays where they were but fades almost out and can't be hovered or clicked, and
// only the selection's own lines are drawn. From there the user can only (1) hover or click one
// of those lines, (2) click someone on the ring to re-centre on them, or (3) click anywhere else
// to glide everyone back to where they were in the full graph.
//
// Clicking a line lists both careers (shared shows in bold) with a link that opens both on the
// Cohort & Career maps; clicking a person lists their career.
//
// Big bunch: the panel shows the share of people in the largest connected piece, and a small line
// of that share for every 10-year window (scripts/18_network_fragmentation.py has the same measure
// and who glues the network together). Clicking the line moves the timeline there.
//
// URL: #graph?year=1959&span=window|all&size=shows|lines&colour=none|comm&pair=Q1,Q2&person=Q1
import * as d3 from "https://cdn.jsdelivr.net/npm/d3@7.9.0/+esm";
import { esc, showTooltip, hideTooltip } from "../tooltip.js";

const NETWORK = "strict";
const W = 10;
const CAT = 7;   // categorical colours --cat-1..7; the rest grey
const RING = 130;   // focus view: radius of the collaborators ring (px)
const GLIDE = 650;  // focus view: ms to glide into or out of it

export function graphMode() {
  let ctxRef = null, host = null, svg = null, zoomG = null, zoom = null, sim = null;
  let lay = null, lastSelKey = "";                   // focus view: anchors, ring, target spots
  let home = null, tween = null;                     // positions before the focus view; the running glide
  let data = null;                                   // built once from db
  let span = "window", sizeBy = "shows", colourBy = "none", selected = null;
  const nodeById = new Map();                        // persistent nodes: positions survive between years

  // --- data (once) ---------------------------------------------------------------------------

  function build(db) {
    const strict = db.credits.filter(c => c[NETWORK]);
    const teams = d3.rollup(strict, cs => ({ year: cs[0].year, people: [...new Set(cs.map(c => c.person))].sort() }), c => c.show);
    const careerOf = d3.group(strict, c => c.person);
    for (const list of careerOf.values()) list.sort((a, b) => a.year - b.year || d3.ascending(a.show, b.show));
    const debut = new Map([...careerOf].map(([p, cs]) => [p, cs[0].year]));
    // BigCLAM: each person's strongest community per cutoff T (window [T-10, T))
    const comm = new Map();
    for (const [T, rows] of d3.group(db.models?.communities.bigclam ?? [], r => r.cutoff)) {
      const best = new Map();
      for (const r of rows) if (!best.has(r.person_id) || best.get(r.person_id).strength < r.strength) best.set(r.person_id, r);
      const sizes = d3.rollup([...best.values()], v => v.length, r => r.community_id);
      const order = [...sizes].sort((a, b) => b[1] - a[1]).map(d => d[0]);
      comm.set(T, { of: new Map([...best].map(([p, r]) => [p, r.community_id])), slot: new Map(order.map((c, i) => [c, i])) });
    }
    return { teams: [...teams], careerOf, debut, comm, cutoffs: [...comm.keys()].sort(d3.ascending) };
  }

  const nameOf = id => ctxRef.db.personById.get(id)?.name ?? id;
  const lastName = id => {   // "Oscar Hammerstein II" -> "Hammerstein"
    const p = nameOf(id).replace(/,/g, "").split(" ");
    while (p.length > 1 && /^(II|III|IV|Jr\.?|Sr\.?)$/i.test(p.at(-1))) p.pop();
    return p.at(-1);
  };

  /** The graph for the timeline year: links (with shows inside the window) and per-person counts. */
  function graphFor(year) {
    const lo = span === "all" ? 0 : year - W + 1;
    const inWin = data.teams.filter(([, t]) => t.year >= lo && t.year <= year);
    const links = new Map(), showsIn = new Map();
    for (const [show, t] of inWin) {
      for (const p of t.people) showsIn.set(p, (showsIn.get(p) || 0) + 1);
      for (let i = 0; i < t.people.length; i++) for (let j = i + 1; j < t.people.length; j++) {
        const k = `${t.people[i]}|${t.people[j]}`;
        if (!links.has(k)) links.set(k, { a: t.people[i], b: t.people[j], shows: [] });
        links.get(k).shows.push(show);
      }
    }
    for (const l of links.values()) {   // shows together by `year`, including before the window
      const mine = new Set(data.careerOf.get(l.a).filter(c => c.year <= year).map(c => c.show));
      l.byNow = data.careerOf.get(l.b).filter(c => c.year <= year && mine.has(c.show)).length;
    }
    const lines = new Map();
    for (const l of links.values()) for (const p of [l.a, l.b]) lines.set(p, (lines.get(p) || 0) + 1);
    return { links: [...links.values()], showsIn, lines, nShows: inWin.length, lo };
  }

  // --- graph ---------------------------------------------------------------------------------

  function setup(ctx) {
    const box = ctx.map.svg.node().closest(".stage-map");
    [...box.children].forEach(c => { c.dataset.graphHidden = c.hidden ? "1" : ""; c.hidden = true; });
    host = document.createElement("div");
    host.className = "graph-host";
    host.style.height = `${ctx.map.height}px`;
    box.appendChild(host);
    svg = d3.select(host).append("svg").attr("class", "graph-svg").attr("role", "img")
      .attr("aria-label", "Collaboration graph: people linked by shared shows");
    zoomG = svg.append("g");
    ["edges", "hits", "nodes", "labels"].forEach(c => zoomG.append("g").attr("class", `g-${c}`));
    zoom = d3.zoom().scaleExtent([0.3, 6]).on("zoom", e => zoomG.attr("transform", e.transform));
    svg.call(zoom);
    svg.on("click", e => { if (e.target === svg.node()) select(null); });
    // Layout: linked people pull together, everyone pushes everyone apart, so a show's team ends up
    // as a tight cluster and people who bridge teams sit between clusters. The motion after a change
    // is only the layout settling; alphaDecay makes it settle in about 2 s. Paused in the focus view.
    sim = d3.forceSimulation()
      .alphaDecay(0.035).velocityDecay(0.45)
      .force("link", d3.forceLink().id(d => d.id).distance(34).strength(0.6))
      .force("charge", d3.forceManyBody().strength(-45).distanceMax(260))
      .force("x", d3.forceX().strength(0.05)).force("y", d3.forceY().strength(0.05))
      .force("collide", d3.forceCollide(d => d.r + 1.5))
      .on("tick", ticked);
  }

  /** Glide the people in `targets` (id -> [x, y]) to their spots with an ease-in-out, no bounce. */
  function glide(targets, ms, done) {
    tween?.stop();
    const moving = sim.nodes().filter(n => targets.has(n.id)).map(n => ({ n, x0: n.x, y0: n.y, to: targets.get(n.id) }));
    tween = d3.timer(elapsed => {
      const k = d3.easeCubicInOut(Math.min(1, elapsed / ms));
      for (const m of moving) {
        m.n.x = m.x0 + (m.to[0] - m.x0) * k;
        m.n.y = m.y0 + (m.to[1] - m.y0) * k;
        m.n.vx = m.n.vy = 0;
      }
      ticked();
      if (elapsed >= ms) { tween.stop(); tween = null; done?.(); }
    });
  }

  function render() {
    if (!host) return;
    const year = ctxRef.state.year;
    const g = graphFor(year);
    const w = host.clientWidth || 600, h = host.clientHeight || 500;
    svg.attr("viewBox", [-w / 2, -h / 2, w, h]);

    const nodes = [...g.showsIn.keys()].map(id => {
      let n = nodeById.get(id);
      if (!n) {
        const l = g.links.find(l => (l.a === id && nodeById.has(l.b)) || (l.b === id && nodeById.has(l.a)));
        const at = l ? nodeById.get(l.a === id ? l.b : l.a) : null;
        n = { id, x: (at?.x ?? (Math.random() - 0.5) * w * 0.5) + (Math.random() - 0.5) * 20,
                  y: (at?.y ?? (Math.random() - 0.5) * h * 0.5) + (Math.random() - 0.5) * 20 };
        nodeById.set(id, n);
      }
      n.shows = g.showsIn.get(id);
      n.lines = g.lines.get(id) || 0;
      n.r = 2.5 + 2.2 * Math.sqrt(sizeBy === "shows" ? n.shows : n.lines / 2);
      n.isNew = data.debut.get(id) === year;
      return n;
    });
    const links = g.links.map(l => ({ ...l, source: l.a, target: l.b }));

    const T = nearestCutoff(year);
    const comm = colourBy === "comm" ? data.comm.get(T) : null;
    const fill = d => {
      if (!comm) return "var(--text-secondary)";
      const c = comm.of.get(d.id), s = c == null ? null : comm.slot.get(c);
      return s != null && s < CAT ? `var(--cat-${s + 1})` : "var(--map-theatre)";
    };

    // focus view for a selected person or line: they go to the centre, their collaborators to a ring
    const anchorIds = (selected?.pair ?? (selected ? [selected.person] : [])).filter(id => g.showsIn.has(id));
    const anchors = new Map(anchorIds.length === 2 ? [[anchorIds[0], [-45, 0]], [anchorIds[1], [45, 0]]]
      : anchorIds.map(id => [id, [0, 0]]));
    const ring = new Set(g.links.filter(l => anchors.has(l.a) || anchors.has(l.b)).flatMap(l => [l.a, l.b]).filter(id => !anchors.has(id)));
    lay = null;
    if (anchors.size) {
      // ring spots: evenly spaced angles, in the order people already sit around the centre (so
      // nobody crosses over); a big ring alternates between two radii so neighbours don't touch
      const R = RING + (anchors.size === 2 ? 30 : 0) + Math.max(0, ring.size - 24) * 2;
      const around = [...ring].sort((a, b) => {
        const pa = nodeById.get(a), pb = nodeById.get(b);
        return Math.atan2(pa?.y ?? 0, pa?.x ?? 0) - Math.atan2(pb?.y ?? 0, pb?.x ?? 0);
      });
      const targets = new Map(anchors);
      around.forEach((id, i) => {
        const a = (2 * Math.PI * i) / around.length - Math.PI / 2, r = R + (around.length > 24 && i % 2 ? 40 : 0);
        targets.set(id, [r * Math.cos(a), r * Math.sin(a)]);
      });
      lay = { anchors, ring, targets };
    }
    const focus = lay ? new Set([...anchors.keys(), ...ring]) : null;
    const key = l => `${l.a}|${l.b}`;
    const isSel = l => selected?.pair && key(l) === selected.pair.join("|");
    const live = d => !focus || focus.has(d.id);                       // in the focus view: drawn and clickable
    const liveLine = l => !lay || anchors.has(l.a) || anchors.has(l.b); // only the selection's own lines

    // Colours are also set as SVG attributes (resolved from the theme tokens), so the graph draws
    // even where the stylesheet's graph rules don't apply: a line with no stroke is invisible.
    // The CSS rules in style.css set the same values and win where they apply.
    const css = getComputedStyle(document.documentElement), tok = n => css.getPropertyValue(n).trim();
    const C = { muted: tok("--text-muted"), accent: tok("--accent"), red: tok("--series-1"), ink: tok("--text-primary"), bg: tok("--surface-1") };
    host.style.background = C.bg;
    zoomG.select(".g-edges").selectAll("line").data(links, key).join("line")
      .attr("class", l => `g-edge${l.byNow >= 2 ? " repeat" : ""}${isSel(l) ? " sel" : ""}`)
      .attr("stroke", l => (isSel(l) ? C.red : l.byNow >= 2 ? C.accent : C.muted))
      .attr("stroke-opacity", l => (isSel(l) || l.byNow >= 2 ? 1 : 0.55))
      .attr("opacity", l => (liveLine(l) ? 1 : 0))
      .attr("stroke-width", l => 0.9 + 1.4 * (l.shows.length - 1) + (l.byNow >= 2 ? 0.8 : 0));
    zoomG.select(".g-hits").selectAll("line").data(links, key).join("line").attr("class", "g-hit")
      .attr("stroke", "transparent").attr("stroke-width", 9).style("cursor", "pointer")
      .style("pointer-events", l => (liveLine(l) ? "stroke" : "none"))
      .on("pointermove", (e, l) => showTooltip(e, `<div class="t-title">${esc(nameOf(l.a))} &amp; ${esc(nameOf(l.b))}</div>
        <div>${l.shows.length} show${l.shows.length > 1 ? "s" : ""} together in this window; ${l.byNow} by ${year}</div>`))
      .on("pointerleave", hideTooltip)
      .on("click", (e, l) => { e.stopPropagation(); select({ pair: [l.a, l.b] }); });
    zoomG.select(".g-nodes").selectAll("circle").data(nodes, d => d.id).join(
        enter => enter.append("circle").attr("r", 0).call(s => s.transition().duration(500).attr("r", d => d.r)),
        update => update.call(s => s.transition().duration(300).attr("r", d => d.r)))
      .attr("class", d => `g-node${d.isNew ? " new" : ""}${selected?.person === d.id || selected?.pair?.includes(d.id) ? " sel" : ""}`)
      .attr("fill", fill)
      .attr("stroke", d => (selected?.person === d.id || selected?.pair?.includes(d.id) ? C.red : d.isNew ? C.ink : C.bg))
      .attr("stroke-width", d => (selected?.person === d.id || selected?.pair?.includes(d.id) ? 3 : d.isNew ? 1.8 : 1))
      .attr("stroke-dasharray", d => (d.isNew ? "2 1.5" : null))
      .attr("opacity", d => (live(d) ? 1 : 0.06))
      .style("pointer-events", d => (live(d) ? null : "none"))
      .on("pointermove", (e, d) => showTooltip(e, `<div class="t-title">${esc(nameOf(d.id))}</div>
        <div>${d.shows} show${d.shows > 1 ? "s" : ""}, ${d.lines} collaborator${d.lines === 1 ? "" : "s"} in this window</div>
        ${d.isNew ? "<div>first Broadway credit this year</div>" : ""}`))
      .on("pointerleave", hideTooltip)
      .on("click", (e, d) => { e.stopPropagation(); if (!anchors.has(d.id)) select({ person: d.id }); })
      .call(d3.drag().filter(e => !lay && !e.ctrlKey && !e.button)   // no dragging in the focus view
        .on("start", (e, d) => { if (!e.active) sim.alphaTarget(0.2).restart(); d.fx = d.x; d.fy = d.y; })
        .on("drag", (e, d) => { d.fx = e.x; d.fy = e.y; })
        .on("end", (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = d.fy = null; }));

    // labels: the 8 people with the most shows in the window; in the focus view, the selection and
    // (when it fits) the whole ring instead
    const named = lay ? new Set([...anchors.keys(), ...(ring.size <= 30 ? ring : [])])
      : new Set(nodes.slice().sort((a, b) => b.shows - a.shows).slice(0, 8).map(d => d.id));
    zoomG.select(".g-labels").selectAll("text").data(nodes.filter(d => named.has(d.id)), d => d.id).join("text")
      .attr("class", "g-label").attr("dy", d => -d.r - 3).attr("text-anchor", "middle")
      .attr("font-size", 11).attr("fill", C.ink).attr("stroke", C.bg).attr("stroke-width", 3).attr("paint-order", "stroke")
      .style("pointer-events", "none").text(d => lastName(d.id));

    sim.nodes(nodes);
    sim.force("link").links(links);
    const selKey = anchorIds.join(","), changed = selKey !== lastSelKey;
    lastSelKey = selKey;
    if (changed) svg.transition().duration(GLIDE).call(zoom.transform, d3.zoomIdentity);   // centre in view
    if (lay) {
      // into (or within) the focus view: remember where everyone was, pause the layout, glide
      home ??= new Map(nodes.map(n => [n.id, [n.x, n.y]]));
      sim.stop();
      glide(lay.targets, changed ? GLIDE : 400);
    } else if (home) {
      // out of the focus view: glide everyone back, then let the layout settle anyone new
      const back = home, fresh = nodes.some(n => !back.has(n.id));   // anyone who arrived during the focus view
      home = null;
      sim.stop();
      glide(back, GLIDE, () => { if (fresh) sim.alpha(0.08).restart(); });
    } else {
      sim.alpha(nodes.length > 600 ? 0.2 : 0.3).restart();
    }
    panel(g, nodes, T);
  }

  function ticked() {
    zoomG.selectAll(".g-edges line, .g-hits line")
      .attr("x1", l => l.source.x).attr("y1", l => l.source.y).attr("x2", l => l.target.x).attr("y2", l => l.target.y);
    zoomG.selectAll(".g-nodes circle").attr("cx", d => d.x).attr("cy", d => d.y);
    zoomG.selectAll(".g-labels text").attr("x", d => d.x).attr("y", d => d.y);
  }

  /** Share of `people` in the largest connected piece, given links as [a, b] pairs (union-find). */
  function giantShare(people, pairs) {
    const parent = new Map(people.map(p => [p, p]));
    const root = p => { while (parent.get(p) !== p) { parent.set(p, parent.get(parent.get(p))); p = parent.get(p); } return p; };
    for (const [a, b] of pairs) parent.set(root(a), root(b));
    const sizes = d3.rollup(people, v => v.length, root);
    return people.length ? d3.max(sizes.values()) / people.length : 0;
  }

  /** "Big bunch" series: giant share of every 10-year window [Y-9, Y], computed once (same measure
   *  as scripts/18_network_fragmentation.py, which also lists the people who glue it together). */
  function bunchSeries() {
    if (data.bunch) return data.bunch;
    const years = d3.range(d3.min(data.teams, ([, t]) => t.year) + W - 1, d3.max(data.teams, ([, t]) => t.year) + 1);
    data.bunch = years.map(Y => {
      const inWin = data.teams.filter(([, t]) => t.year > Y - W && t.year <= Y).map(([, t]) => t.people);
      const people = [...new Set(inWin.flat())];
      return { year: Y, share: giantShare(people, inWin.flatMap(t => t.slice(1).map(p => [t[0], p]))) };
    });
    return data.bunch;
  }

  function drawBunch(el, year) {
    const rows = bunchSeries(), w = el.clientWidth || 300, h = 64, m = { t: 6, r: 8, b: 16, l: 30 };
    const x = d3.scaleLinear().domain(d3.extent(rows, r => r.year)).range([m.l, w - m.r]);
    const y = d3.scaleLinear().domain([0, 1]).range([h - m.b, m.t]);
    const css = getComputedStyle(document.documentElement), tok = n => css.getPropertyValue(n).trim();
    const svgB = d3.select(el).append("svg").attr("width", w).attr("height", h).style("cursor", "pointer")
      .attr("role", "img").attr("aria-label", "Share of people in the largest connected piece, every 10-year window");
    for (const v of [0, 0.5, 1]) {
      svgB.append("line").attr("x1", m.l).attr("x2", w - m.r).attr("y1", y(v)).attr("y2", y(v)).attr("stroke", tok("--grid"));
      svgB.append("text").attr("x", m.l - 4).attr("y", y(v) + 3).attr("text-anchor", "end").attr("font-size", 10)
        .attr("fill", tok("--text-muted")).text(d3.format(".0%")(v));
    }
    for (const t of x.ticks(5)) svgB.append("text").attr("x", x(t)).attr("y", h - 3).attr("text-anchor", "middle")
      .attr("font-size", 10).attr("fill", tok("--text-muted")).text(t);
    svgB.append("path").datum(rows).attr("fill", "none").attr("stroke", tok("--text-secondary")).attr("stroke-width", 1.5)
      .attr("d", d3.line().x(r => x(r.year)).y(r => y(r.share)));
    const now = rows.find(r => r.year === year);
    if (now) svgB.append("circle").attr("cx", x(year)).attr("cy", y(now.share)).attr("r", 4)
      .attr("fill", tok("--accent")).attr("stroke", tok("--surface-1")).attr("stroke-width", 1.5);
    // click to jump the timeline to that window
    svgB.on("click", e => ctxRef.setYear(Math.round(x.invert(d3.pointer(e)[0]))));
  }

  const nearestCutoff = year => data.cutoffs.length
    ? data.cutoffs.reduce((b, c) => (Math.abs(c - (year + 1)) < Math.abs(b - (year + 1)) ? c : b)) : null;

  function select(s) { selected = s; ctxRef.setYear(ctxRef.state.year); }   // re-renders and updates the URL

  // --- panel ---------------------------------------------------------------------------------

  const seg = (name, value, options) => `<div class="seg" data-ctl="${name}" style="justify-self:start">${options.map(([v, label]) =>
    `<button type="button" data-v="${v}" aria-pressed="${v === value}">${label}</button>`).join("")}</div>`;

  function careerList(p, shared, year) {
    return `<ol class="g-career">${data.careerOf.get(p).map(c => {
      const s = ctxRef.db.showById.get(c.show);
      return `<li class="${shared.has(c.show) ? "shared" : ""}${c.year > year ? " future" : ""}">${c.year} · <em>${esc(s?.title ?? c.show)}</em></li>`;
    }).join("")}</ol>`;
  }

  function panel(g, nodes, T) {
    const year = ctxRef.state.year;
    const el = ctxRef.panel;
    const repeat = g.links.filter(l => l.byNow >= 2).length;
    const debuts = nodes.filter(d => d.isNew).length;
    let detail = "";
    if (selected?.pair) {
      const [a, b] = selected.pair;
      const mine = new Set(data.careerOf.get(a).map(c => c.show));
      const sharedCredits = data.careerOf.get(b).filter(c => mine.has(c.show));
      const shared = new Set(sharedCredits.map(c => c.show));
      const byNow = sharedCredits.filter(c => c.year <= year).length;
      detail = `<h3 class="list-title">${esc(nameOf(a))} &amp; ${esc(nameOf(b))}</h3>
        <p>${shared.size} show${shared.size > 1 ? "s" : ""} together in their careers, ${byNow} by ${year}. On the graph they sit in the centre with everyone either of them worked with in a ring around them; click empty space to go back to the full graph. Shared shows in bold; faded = after ${year}.</p>
        <p><a href="#cohort?from=${sharedCredits[0].year}&p=${a},${b}&year=${year}">Open both careers on the map →</a>
          · <button type="button" class="link-btn g-clear">clear</button></p>
        ${[a, b].map(p => `<h4>${esc(nameOf(p))}</h4>${careerList(p, shared, year)}`).join("")}`;
    } else if (selected?.person) {
      const p = selected.person;
      const mates = g.links.filter(l => l.a === p || l.b === p).length;
      detail = `<h3 class="list-title">${esc(nameOf(p))}</h3>
        <p>${mates} collaborator${mates === 1 ? "" : "s"} in this window, in the ring around them on the graph. Hover or click one of their lines to compare two careers, click someone on the ring to centre on them, or click empty space to go back to the full graph.</p>
        <p><a href="#cohort?from=${data.debut.get(p)}&p=${p}&year=${year}">Open their career on the map →</a>
          · <button type="button" class="link-btn g-clear">clear</button></p>
        ${careerList(p, new Set(), year)}`;
    }
    el.innerHTML = `
      <h2>Who worked with whom, ${span === "all" ? `up to ${year}` : `${g.lo}–${year}`}</h2>
      <p class="hint">Prototype. Each dot is a person, each line a show they shared. ${nodes.length} people,
        ${g.links.length} pairs, ${g.nShows} shows; ${repeat} pairs (${d3.format(".0%")(repeat / Math.max(1, g.links.length))})
        are repeat collaborators (gold). ${debuts} debut${debuts === 1 ? "" : "s"} in ${year} (dashed rings).</p>
      <div class="g-bunch" style="margin:10px 0 4px">
        <p style="margin:0 0 4px"><strong>${d3.format(".0%")(giantShare([...g.showsIn.keys()], g.links.map(l => [l.a, l.b])))}</strong>
          of these people are in one big bunch: connected to each other through some chain of collaborators.</p>
        <div class="g-bunch-chart"></div>
        <p class="hint" style="margin:2px 0 0">Big bunch in every 10-year window (dot: ${span === "all" ? "the window ending " : ""}${year};
          click to jump). Play from 1940 to 2010: what happens to the big bunch?</p>
      </div>
      <div class="g-controls" style="display:grid;grid-template-columns:max-content max-content;align-items:center;gap:8px 12px;margin:10px 0">
        <span>Years</span>${seg("span", span, [["window", "last 10 years"], ["all", "everything so far"]])}
        <span>Dot size</span>${seg("size", sizeBy, [["shows", "shows"], ["lines", "collaborators"]])}
        ${data.cutoffs.length ? `<span>Colour</span>${seg("colour", colourBy, [["none", "none"], ["comm", "BigCLAM community"]])}` : ""}
      </div>
      <div class="legend">
        <span><i class="g-key"></i>shared a show (thicker = more shows in these years)</span>
        <span><i class="g-key repeat"></i>2+ shows together by ${year}</span>
        <span><i class="g-key-ring"></i>first Broadway credit in ${year}</span>
      </div>
      <p class="hint">${sizeBy === "shows" ? "Dot size: shows in these years (big = prolific)."
        : "Dot size: distinct collaborators in these years. One big team gives everyone on it many lines, so this mostly measures team size."}
        ${colourBy === "comm" && T ? ` Colours: BigCLAM communities for ${T - 10}–${T - 1}, the nearest model window. Each colour is mostly one show's team.` : ""}</p>
      ${detail || `<p class="hint">Hover for names. Click a line to see how two people ended up working together, or a person for their
        career. Drag to rearrange, scroll to zoom. Labels mark the 8 people with the most shows.</p>`}`;
    drawBunch(el.querySelector(".g-bunch-chart"), year);
    el.querySelectorAll(".seg[data-ctl] button").forEach(b => b.addEventListener("click", () => {
      const v = b.dataset.v, ctl = b.parentElement.dataset.ctl;
      if (ctl === "span") span = v; else if (ctl === "size") sizeBy = v; else colourBy = v;
      ctxRef.setYear(year);
    }));
    el.querySelector(".g-clear")?.addEventListener("click", () => select(null));
  }

  // --- mode ----------------------------------------------------------------------------------

  function readParams(ctx) {
    const p = ctx.state.params;
    span = p.get("span") === "all" ? "all" : "window";
    sizeBy = p.get("size") === "lines" ? "lines" : "shows";
    colourBy = p.get("colour") === "comm" ? "comm" : "none";
    const pair = p.get("pair")?.split(",").filter(id => data.careerOf.has(id));
    const person = p.get("person");
    selected = pair?.length === 2 ? { pair } : data.careerOf.has(person) ? { person } : null;
  }

  return {
    id: "graph", label: "Collaboration graph", caption: "who worked with whom · no map", usesYear: true,

    enter(ctx) {
      ctxRef = ctx;
      data ??= build(ctx.db);
      readParams(ctx);
      setup(ctx);
      render();
    },
    setYear() { render(); },
    onParams(ctx) { readParams(ctx); render(); },
    params() {
      const p = {};
      if (span !== "window") p.span = span;
      if (sizeBy !== "shows") p.size = sizeBy;
      if (colourBy !== "none") p.colour = colourBy;
      if (selected?.pair) p.pair = selected.pair.join(",");
      else if (selected?.person) p.person = selected.person;
      return p;
    },
    exit(ctx) {
      sim?.stop();
      hideTooltip();
      const box = host?.parentElement;
      host?.remove();
      tween?.stop();
      host = svg = zoomG = sim = tween = null;
      lay = home = null; lastSelKey = "";
      box && [...box.children].forEach(c => { c.hidden = c.dataset.graphHidden === "1"; delete c.dataset.graphHidden; });
    },
  };
}
