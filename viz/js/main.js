// Entry point: load the data once, then render the view named in the URL hash.
// Hashes look like "#showmap" or "#trajectory?p=Q269094"; the part after "?" is passed to the view.
import { loadData } from "./data.js";
import { renderDataCheck } from "./views/dataCheck.js";
import { renderShowMap } from "./views/showMap.js";
import { renderPlaceholder } from "./views/placeholder.js";

const VIEWS = {
  data: renderDataCheck,
  showmap: renderShowMap,
  trajectory: (el) => renderPlaceholder(el, "Trajectory view",
    "One person's career as a path between theatres over time, each show and role labelled. Earlier collaborators appear faintly where they reunite."),
  birthplaces: (el) => renderPlaceholder(el, "Birthplace map",
    "Where Broadway's creative people were born, filterable by role and decade. Covers people with a Wikidata entry."),
  cohort: (el) => renderPlaceholder(el, "Cohort view",
    "Pick a start year; everyone working on a show then is a dot in that show's colour, clustered at its theatre. Move through time to watch teams disperse and reunite."),
  multiples: (el) => renderPlaceholder(el, "Small multiples",
    "The cohort view as static panels, one per five-year step: the baseline for the user study."),
};

const viewEl = document.getElementById("view");
let db = null;

function parseHash() {
  const [name, query = ""] = location.hash.replace(/^#/, "").split("?");
  return { name: VIEWS[name] ? name : "showmap", params: new URLSearchParams(query) };
}

function route() {
  const { name, params } = parseHash();
  document.querySelectorAll(".views a").forEach(a => {
    if (a.dataset.view === name) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  viewEl.innerHTML = "";
  VIEWS[name](viewEl, db, params);
}

async function start() {
  try {
    db = await loadData();
  } catch (err) {
    viewEl.innerHTML = `<p class="error">${err.message}. Serve this folder over HTTP (see viz/README.md); opening index.html directly from disk does not work.</p>`;
    return;
  }
  document.getElementById("meta-line").textContent = `Data exported ${db.meta.generated}`;
  window.addEventListener("hashchange", route);
  window.db = db;  // handy in the browser console while developing
  route();
}

start();
