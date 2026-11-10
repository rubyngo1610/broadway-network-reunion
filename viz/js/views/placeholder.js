export function renderPlaceholder(el, title, description) {
  el.innerHTML = `
    <section class="panel placeholder">
      <h2>${title}</h2>
      <p>${description}</p>
      <p><em>Not built yet.</em> See the plan in WORKLOG.md, "Next steps".</p>
    </section>`;
}
