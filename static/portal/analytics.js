(() => {
  'use strict';
  const hint = document.querySelector('[data-chart-hint]');
  document.querySelectorAll('[data-chart-label]').forEach(point => {
    const reveal = () => {
      if (hint) hint.textContent = point.dataset.chartLabel;
      const panel = point.closest('.analytics-panel');
      panel?.querySelectorAll('.is-selected').forEach(old => old.classList.remove('is-selected'));
      point.classList.add('is-selected');
    };
    const target = point.closest('a') || point;
    target.addEventListener('pointerenter', reveal);
    target.addEventListener('focus', reveal);
  });
  document.querySelector('[data-indicator-filter]')?.addEventListener('submit', event => {
    if (!event.target.checkValidity()) return;
    event.target.setAttribute('aria-busy', 'true');
    const submit = event.target.querySelector('button[type="submit"]');
    if (submit) { submit.textContent = 'Atualizando indicadores…'; submit.disabled = true; }
  });
})();
