// Entry point: load the data once, build the one shared map (the stage), then switch modes as the
// URL hash changes. Hashes look like "#shows?year=1927" or "#career?p=Q269094". The map is never
// rebuilt: changing the hash only changes the mode, so zoom and year carry over.
// "#data" is the developer data check, shown in place of the stage.
import { loadData } from "./data.js";
import { createStage } from "./stage.js";
import { showsMode } from "./modes/shows.js";
import { careerMode } from "./modes/career.js";
import { cohortMode } from "./modes/cohort.js";
import { comingSoon } from "./modes/comingSoon.js";
import { renderDataCheck } from "./views/dataCheck.js";

const MODES = [
  showsMode(),
  careerMode(),
  cohortMode(),
  comingSoon({
    id: "birthplaces", label: "Birthplaces", caption: "where they came from", usesYear: true,
    title: "Birthplaces",
    text: "Where Broadway's creative people were born, filterable by role and decade. Covers people with a Wikidata entry.",
    mapNote: "the map zooms out from Manhattan to the US and the world, and back in when you leave.",
  }),
  comingSoon({
    id: "compare", label: "Compare", caption: "five-year panels", usesYear: true,
    title: "Small multiples",
    text: "The cohort view as static panels, one per five-year step from the year on the timeline. This is the baseline for the user study.",
    mapNote: "the single map splits into a grid of small maps.",
  }),
];
// old page names still work
const ALIASES = { showmap: "shows", trajectory: "career", multiples: "compare" };

const stageEl = document.getElementById("stage");
const dataEl = document.getElementById("data-view");
let db = null, stage = null;

function parseHash() {
  const [raw, query = ""] = location.hash.replace(/^#/, "").split("?");
  return { name: ALIASES[raw] || raw, params: new URLSearchParams(query) };
}

function route() {
  const { name, params } = parseHash();
  if (name === "data") {
    stageEl.hidden = true;
    dataEl.hidden = false;
    dataEl.innerHTML = `<p><a href="#${stage?.mode || "shows"}">← Back to the map</a></p><div></div>`;
    renderDataCheck(dataEl.lastElementChild, db, params);
    return;
  }
  dataEl.hidden = true;
  stageEl.hidden = false;
  if (!stage) stage = createStage(stageEl, db, MODES);  // built once, while visible, so its width is known
  stage.go(name, params);
}

async function start() {
  try {
    db = await loadData();
  } catch (err) {
    stageEl.innerHTML = `<p class="error">${err.message}. Serve this folder over HTTP (see viz/README.md); opening index.html directly from disk does not work.</p>`;
    return;
  }
  document.getElementById("meta-line").textContent = `Data exported ${db.meta.generated}`;
  window.addEventListener("hashchange", route);
  window.db = db;  // handy in the browser console while developing
  route();
}

start();
