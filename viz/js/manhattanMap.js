// Shared zoomable Manhattan map (D3 vector basemap from scripts/14_build_basemap.py).
// Used by the show map, the trajectory view and the cohort view.
//
//   const map = createManhattanMap(container, db, { height: 640 });
//   map.layer("overlay")          -> a <g> above the theatres, for a view's own marks
//   map.xy(lat, lon)              -> [x, y] on screen under the current zoom
//   map.onZoom(fn)                -> fn(transform) after every zoom/pan: re-place your marks there
//   map.zoomTo(latLons, padding)  -> animate to fit a set of points
//
// Basemap paths are scaled by the zoom transform with non-scaling strokes; points are re-placed
// instead of scaled, so dots keep their size and spread apart as you zoom in.
import * as d3 from "https://cdn.jsdelivr.net/npm/d3@7.9.0/+esm";

// Manhattan's street grid runs about 29° east of true north. Rotating the projection by that much
// makes the avenues vertical ("grid north", as on most NYC maps).
const GRID_ANGLE = 29;
// Default view: Union Square (14th St) to Lincoln Center (66th St)
const HOME = [[40.7330, -74.0060], [40.7760, -73.9700]];

export function createManhattanMap(container, db, { height = 640, home = HOME, maxZoom = 16 } = {}) {
  const basemap = db.basemap;
  const width = container.clientWidth || 800;
  const wrap = d3.select(container).append("div").attr("class", "map-wrap");
  const svg = wrap.append("svg")
    .attr("class", "chart map").attr("viewBox", `0 0 ${width} ${height}`)
    .attr("role", "img").attr("aria-label", "Zoomable map of Manhattan");

  const projection = d3.geoMercator().angle(GRID_ANGLE);
  fit(home);
  const path = d3.geoPath(projection);

  function fit(latLons, pad = 24) {
    const pts = { type: "MultiPoint", coordinates: latLons.map(([lat, lon]) => [lon, lat]) };
    projection.fitExtent([[pad, pad], [width - pad, height - pad]], pts);
  }

  // --- basemap layers (scaled with the zoom) ---
  svg.append("rect").attr("class", "water").attr("width", width).attr("height", height);
  const base = svg.append("g").attr("class", "basemap");
  const ring = rings => ({ type: "MultiPolygon", coordinates: rings.map(r => [r]) });

  base.selectAll("path.land").data(basemap.land).join("path")
    .attr("class", d => `land ${d.name === "Manhattan" ? "manhattan" : "other"}`)
    .attr("d", d => path(ring(d.rings)));
  base.append("path").attr("class", "parks")
    .attr("d", path(ring(basemap.parks.flatMap(p => p.rings))));
  const line = lines => ({ type: "MultiLineString", coordinates: lines });
  base.append("path").attr("class", "street minor").attr("d", path(line(basemap.streets.minor)));
  base.append("path").attr("class", "street major").attr("d", path(line(basemap.streets.major)));

  // --- point layers (re-placed on zoom, not scaled) ---
  const labelLayer = svg.append("g").attr("class", "map-labels");
  const layers = {
    theatres: svg.append("g").attr("class", "theatres"),
    overlay: svg.append("g").attr("class", "overlay"),
    top: svg.append("g").attr("class", "top"),
  };

  let transform = d3.zoomIdentity;
  const listeners = [];
  const xy = (lat, lon) => transform.apply(projection([lon, lat]));

  const labels = labelLayer.selectAll("text").data(basemap.labels).join("text")
    .attr("class", d => `map-label ${d.kind}`).attr("text-anchor", "middle").text(d => d.name);

  function placeLabels() {
    labels.attr("transform", d => {
      const [x, y] = xy(d.lat, d.lon);
      return `translate(${x},${y})`;
    }).attr("display", d => (d.kind === "water" || transform.k < 9 ? null : "none"));
  }

  const zoom = d3.zoom().scaleExtent([1, maxZoom])
    .translateExtent([[-width, -height], [2 * width, 2 * height]])
    .on("zoom", ev => {
      transform = ev.transform;
      base.attr("transform", transform);
      placeLabels();
      for (const fn of listeners) fn(transform);
    });
  svg.call(zoom).on("dblclick.zoom", null);

  // zoom buttons (keyboard and touch friendly)
  const controls = wrap.append("div").attr("class", "map-controls");
  controls.append("button").attr("type", "button").attr("aria-label", "Zoom in").text("+")
    .on("click", () => svg.transition().duration(300).call(zoom.scaleBy, 1.6));
  controls.append("button").attr("type", "button").attr("aria-label", "Zoom out").text("−")
    .on("click", () => svg.transition().duration(300).call(zoom.scaleBy, 1 / 1.6));
  controls.append("button").attr("type", "button").attr("aria-label", "Reset view").attr("class", "home").text("⌂")
    .on("click", () => svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity));
  wrap.append("div").attr("class", "map-attribution").text(basemap.attribution);

  placeLabels();

  return {
    svg, projection, width, height,
    layer: name => layers[name],
    xy,
    get transform() { return transform; },
    /** Call fn(transform) now and after every zoom/pan. Returns a function that removes it. */
    onZoom(fn) {
      listeners.push(fn);
      fn(transform);
      return () => { const i = listeners.indexOf(fn); if (i >= 0) listeners.splice(i, 1); };
    },
    /** Animate to fit a set of [lat, lon] points, keeping at least `minSpan` degrees of context. */
    zoomTo(latLons, { pad = 60, duration = 750 } = {}) {
      if (!latLons.length) return;
      const px = latLons.map(([lat, lon]) => projection([lon, lat]));
      const [x0, x1] = d3.extent(px, p => p[0]), [y0, y1] = d3.extent(px, p => p[1]);
      const k = Math.min(maxZoom, 0.9 / Math.max((x1 - x0 + pad) / width, (y1 - y0 + pad) / height, 1 / maxZoom));
      const t = d3.zoomIdentity.translate(width / 2, height / 2).scale(Math.max(1, k))
        .translate(-(x0 + x1) / 2, -(y0 + y1) / 2);
      svg.transition().duration(duration).call(zoom.transform, t);
    },
  };
}

/** Draw every theatre as a small dot; returns the selection so views can restyle it. */
export function drawTheatres(map, db, { onHover, onLeave, className = "theatre faint", r = 3.5 } = {}) {
  const g = map.layer("theatres");
  const dots = g.selectAll("circle.t").data(db.theatres, d => d.id).join("circle")
    .attr("class", `t ${className}`).attr("r", r);
  const hits = g.selectAll("circle.hit").data(db.theatres, d => d.id).join("circle")
    .attr("class", "hit").attr("r", 9);
  if (onHover) hits.on("pointermove", onHover);
  if (onLeave) hits.on("pointerleave", onLeave);
  map.onZoom(() => {
    dots.attr("cx", d => map.xy(d.lat, d.lon)[0]).attr("cy", d => map.xy(d.lat, d.lon)[1]);
    hits.attr("cx", d => map.xy(d.lat, d.lon)[0]).attr("cy", d => map.xy(d.lat, d.lon)[1]);
  });
  return { dots, hits };
}
