// One shared tooltip element for every view.
const el = () => document.getElementById("tooltip");

export function showTooltip(event, html) {
  const t = el();
  t.innerHTML = html;
  t.hidden = false;
  const pad = 14;
  const { innerWidth: w, innerHeight: h } = window;
  const r = t.getBoundingClientRect();
  let x = event.clientX + pad, y = event.clientY + pad;
  if (x + r.width > w - 8) x = event.clientX - r.width - pad;
  if (y + r.height > h - 8) y = event.clientY - r.height - pad;
  t.style.left = `${Math.max(8, x)}px`;
  t.style.top = `${Math.max(8, y)}px`;
}

export function hideTooltip() {
  el().hidden = true;
}

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
