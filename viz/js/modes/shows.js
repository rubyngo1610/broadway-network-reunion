// Shows mode: where each year's new musicals opened. Theatres with an opening that year are filled
// and labelled (labels appear once zoomed in); other standing theatres are rings.
import { esc } from "../tooltip.js";

export function showsMode() {
  let labelG = null, offZoom = null, ctxRef = null;
  const opensIn = (db, t, y) => (db.showsByTheatre.get(t.id) || []).filter(s => s.year === y);

  function placeLabels(tr) {
    if (!labelG) return;
    labelG.selectAll("text")
      .attr("x", d => ctxRef.map.xy(d.lat, d.lon)[0]).attr("y", d => ctxRef.map.xy(d.lat, d.lon)[1])
      .attr("display", tr.k >= 3 ? null : "none");
  }

  function update(ctx, year, duration = 350) {
    const { db, theatres: { dots }, panel } = ctx;
    const lit = t => opensIn(db, t, year).length > 0;
    dots.attr("class", t => (lit(t) ? "t theatre" : db.standing(t, year) ? "t theatre gone" : "t theatre faint"));
    dots.filter(lit).raise();
    dots.transition("mode").duration(duration)
      .attr("r", t => (lit(t) ? 6 : 3.5))
      .attr("opacity", t => (lit(t) || db.standing(t, year) ? 1 : 0.35));

    const opening = db.shows.filter(s => s.year === year);
    panel.querySelector(".list-title").textContent =
      `${opening.length} new musical${opening.length === 1 ? "" : "s"} in ${year}`;
    panel.querySelector(".show-list").innerHTML = opening.map(s => {
      const t = db.theatreById.get(s.venue);
      return `<li class="${t ? "" : "no-venue"}"><strong>${esc(s.title)}</strong>
        <div class="where">${t ? esc(t.name) : "theatre unknown"}</div></li>`;
    }).join("");

    labelG.selectAll("text").data(db.theatres.filter(lit), d => d.id).join("text")
      .attr("class", "theatre-label").attr("dx", 9).attr("dy", "0.35em").text(d => d.name);
    placeLabels(ctx.map.transform);
  }

  return {
    id: "shows", label: "Shows", caption: "where musicals opened", usesYear: true,

    enter(ctx) {
      ctxRef = ctx;
      ctx.panel.innerHTML = `
        <h2>Broadway on the map</h2>
        <p class="sub">Where each year's new musicals opened. Move the timeline or press play.
          Theatres with no recorded opening date count from their first show in our data.</p>
        <div class="legend">
          <span><span class="key on"></span>a show opened here</span>
          <span><span class="key standing"></span>standing</span>
          <span><span class="key gone"></span>not built yet or demolished</span>
        </div>
        <h3 class="list-title"></h3>
        <ul class="show-list"></ul>`;
      labelG = ctx.map.layer("top").append("g").attr("class", "mode-shows");
      offZoom = ctx.map.onZoom(placeLabels);
      update(ctx, ctx.state.year, 500);
    },

    setYear(ctx, year) { update(ctx, year); },

    exit() {
      offZoom?.();
      labelG?.transition().duration(250).attr("opacity", 0).remove();
      labelG = null;
    },

    tip(t, ctx) {
      const now = opensIn(ctx.db, t, ctx.state.year);
      const span = `${t.opened ?? (t.first_show != null ? `by ${t.first_show}` : "?")}–${t.demolished ?? "today"}`;
      return `<div class="t-title">${esc(t.name)}</div>
        <div class="t-sub">${span} · ${t.n_shows} show${t.n_shows === 1 ? "" : "s"} in our data</div>
        ${now.length ? `<div>${ctx.state.year}: ${now.map(s => `<em>${esc(s.title)}</em>`).join(", ")}</div>` : ""}`;
    },
  };
}
