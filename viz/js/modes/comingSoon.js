// Stand-in for a mode that isn't built yet: it fills the panel with what the mode will do and
// fades the theatres back, so switching to it already shows the transition.
import { esc } from "../tooltip.js";

export function comingSoon({ id, label, caption, usesYear, title, text, mapNote }) {
  function fade(ctx, duration) {
    const { db, theatres: { dots }, state } = ctx;
    dots.attr("class", "t theatre faint");
    dots.transition("mode").duration(duration).attr("r", 3.5)
      .attr("opacity", t => (usesYear ? (db.standing(t, state.year) ? 0.85 : 0.25) : 0.6));
  }
  return {
    id, label, caption, usesYear,
    enter(ctx) {
      ctx.panel.innerHTML = `
        <h2>${esc(title)}</h2>
        <p class="sub">${esc(text)}</p>
        <p class="map-note"><strong>On the map:</strong> ${esc(mapNote)}</p>
        <p class="hint">Not built yet. See WORKLOG.md, "Next steps".</p>`;
      fade(ctx, 500);
    },
    setYear(ctx) { fade(ctx, 300); },
    exit() {},
    tip: t => `<div class="t-title">${esc(t.name)}</div>`,
  };
}
