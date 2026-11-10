// Manhattan grid coordinates: lat/lon -> (avenue, street). Avenues run about 29° east of true north,
// so plotting in grid units gives a map with straight avenues and streets, the "lightly stylized
// Theater District map" of the proposal. Calibrated on Seventh Avenue between 34th and 59th Streets
// and on 42nd Street between Seventh and Eighth Avenues; good to roughly half a block in Midtown.

const ORIGIN = { lat: 40.7560, lon: -73.9868 };      // Seventh Avenue at 42nd Street
const STREET = { lat: 0.000602, lon: 0.000464 };     // one street north along an avenue
const AVENUE = { lat: 0.001570, lon: -0.003300 };    // one avenue west (Seventh -> Eighth) along a street

const det = STREET.lat * AVENUE.lon - STREET.lon * AVENUE.lat;

/** {street, avenue}: street number (42 = 42nd St) and avenue number (7 = Seventh, 8 = Eighth, ...). */
export function toGrid(lat, lon) {
  const dLat = lat - ORIGIN.lat, dLon = lon - ORIGIN.lon;
  const u = (dLat * AVENUE.lon - dLon * AVENUE.lat) / det;   // streets north of 42nd
  const v = (STREET.lat * dLon - STREET.lon * dLat) / det;   // avenues west of Seventh
  return { street: 42 + u, avenue: 7 + v };
}

/** Broadway's diagonal through the grid, as (avenue, street) points. */
export const BROADWAY = [
  { avenue: 5, street: 23 },    // Madison Square
  { avenue: 6, street: 34 },    // Herald Square
  { avenue: 7, street: 45 },    // Times Square
  { avenue: 8, street: 59 },    // Columbus Circle
  { avenue: 9.2, street: 66 },  // Lincoln Square
];

export const AVENUES = [
  { avenue: 5, name: "Fifth Ave" },
  { avenue: 6, name: "Sixth Ave" },
  { avenue: 7, name: "Seventh Ave" },
  { avenue: 8, name: "Eighth Ave" },
  { avenue: 9, name: "Ninth Ave" },
];
