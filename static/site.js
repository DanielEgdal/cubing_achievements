document.querySelectorAll('form[data-confirm]').forEach(form => {
  form.addEventListener('submit', event => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});

document.querySelectorAll('[data-print]').forEach(button => {
  button.addEventListener('click', () => window.print());
});

document.querySelectorAll('.filters select').forEach(select => {
  select.addEventListener('change', () => {
    if (select.hasAttribute('data-category-filter')) {
      select.form.elements.achievement.value = '';
    }
    select.form.requestSubmit();
  });
});

const panel = document.querySelector('[data-status-url]');
if (panel && panel.dataset.running === 'true') {
  const poll = async () => {
    try {
      const response = await fetch(panel.dataset.statusUrl);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const job = await response.json();
      document.getElementById('poll-error').textContent = '';
      document.getElementById('job-status').textContent = job.label;
      document.getElementById('job-output').textContent =
        [...job.output, ...(job.error ? [job.error] : [])].join('\n');
      document.querySelectorAll('[data-run-control]').forEach(control => {
        control.disabled = job.status === 'running';
      });
      const guidance = document.getElementById('job-guidance');
      if (job.status === 'succeeded') {
        guidance.textContent = job.operation === 'refresh'
          ? 'WCA-data er opdateret. Start nu beregningen af bedrifter.'
          : 'Beregningen er afsluttet. Datasiderne er tilgængelige igen.';
      } else if (job.status === 'failed' || job.status === 'interrupted') {
        guidance.textContent = 'Kørslen blev ikke gennemført. Se de tekniske detaljer nedenfor. Allerede afsluttede beregninger kan være gemt.';
        panel.querySelector('details').open = true;
      }
      if (job.status === 'running') window.setTimeout(poll, 1500);
    } catch (error) {
      document.getElementById('poll-error').textContent =
        'Status kunne ikke hentes. Kontrollér at serveren kører. Prøver igen…';
      window.setTimeout(poll, 5000);
    }
  };
  poll();
}
