// Cohort & Career: the cohort map on the left (its panel at the far left) and a career map on the
// right (its panel at the far right), on one shared timeline. Clicking a cohort member draws their
// career on the right map, up to the timeline year; the cohort side rings that person and dims
// everyone they never worked with again. The career side keeps all of Career mode: compare with
// up to three collaborators, remove people, search anyone.
//
// It runs the two existing modes side by side, each on its own map (ctx.split.left / right).
// URL: #cohort?from=1943&p=Q269094&year=1956  (old #career?p=… links open here too)
import { cohortMode } from "./cohort.js";
import { careerMode } from "./career.js";

export function cohortCareerMode() {
  let L = null, R = null;
  const cohort = cohortMode({ onPick: id => openCareer(id) });
  const career = careerMode({
    followTimeline: true,
    intro: "Click someone on the cohort map to draw their career here, or search for anyone.",
  });

  /** Put a person on the career side. Goes through the URL so Back and shared links work. */
  function openCareer(id) {
    const { from } = cohort.params();
    location.hash = `#cohort?from=${from}&p=${id}&year=${L.state.year}`;
  }

  /** Keep the ring on the cohort map on the career's first person (if they are in this cohort). */
  function syncPicked() {
    const anchor = career.params().p.split(",")[0] || null;
    if (anchor !== cohort.picked) cohort.setPicked(anchor);
  }

  return {
    id: "cohort", label: "Cohort & Career", caption: "teams scatter · follow one person", usesYear: true, split: true,

    enter(ctx) {
      ({ left: L, right: R } = ctx.split);
      cohort.enter(L);     // sets the timeline range and year
      career.enter(R);     // follows that year
      syncPicked();
    },

    onParams(ctx) {
      cohort.onParams(L);
      career.onParams(R);
      syncPicked();
    },

    setYear(ctx, y) {
      cohort.setYear(L, y);
      career.setYear(R, y);
    },

    exit() {
      cohort.exit(L);
      career.exit(R);
    },

    params: () => {
      const p = career.params().p;
      return { ...cohort.params(), ...(p ? { p } : {}) };
    },
    tip: t => cohort.tip(t),
    tipRight: t => career.tip(t),
  };
}
