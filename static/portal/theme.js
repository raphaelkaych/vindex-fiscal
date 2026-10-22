/* Síncrono e antes do CSS: a primeira pintura já usa a aparência escolhida. */
(() => {
 const root = document.documentElement;
 const key = 'vindex-fiscal-theme';
 const system = window.matchMedia('(prefers-color-scheme: dark)');
 const normalize = value => value === 'light' || value === 'dark' ? value : 'system';
 let preference = 'system';

 const persist = () => {
  try { window.localStorage.setItem(key, preference); }
  catch (_) { /* A escolha ainda funciona nesta página com armazenamento bloqueado. */ }
 };
 try {
  const saved = window.localStorage.getItem(key);
  preference = normalize(saved);
  // A ausência de preferência no controle anterior passa a ser a opção explícita.
  if (saved !== preference) persist();
 } catch (_) {}

 const apply = () => {
  const dark = preference === 'dark' || (preference === 'system' && system.matches);
  const label = dark ? 'Ativar modo claro' : 'Ativar modo escuro';
  root.dataset.theme = dark ? 'dark' : 'light';
  root.dataset.themePreference = preference;
  document.querySelectorAll('[data-theme-controls]').forEach(control => { control.hidden = false; });
  document.querySelectorAll('[data-theme-toggle]').forEach(button => {
   button.hidden = false;
   button.setAttribute('aria-pressed', String(dark));
   button.setAttribute('aria-label', label);
   button.title = label;
   button.querySelector('[data-theme-label]').textContent = label;
   button.querySelector('[data-theme-icon="moon"]').toggleAttribute('hidden', dark);
   button.querySelector('[data-theme-icon="sun"]').toggleAttribute('hidden', !dark);
  });
 };
 const choose = value => {
  preference = normalize(value);
  persist();
  apply();
 };
 const bindControls = () => {
  document.querySelectorAll('[data-theme-toggle]').forEach(button => {
   button.addEventListener('click', () => choose(root.dataset.theme === 'dark' ? 'light' : 'dark'));
  });
  apply();
 };

 apply();
 if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bindControls, {once: true});
 } else {
  bindControls();
 }
 const systemChanged = () => { if (preference === 'system') apply(); };
 if (system.addEventListener) system.addEventListener('change', systemChanged);
 else if (system.addListener) system.addListener(systemChanged);
 window.addEventListener('storage', event => {
  if (event.key === key || event.key === null) {
   preference = normalize(event.key === null ? null : event.newValue);
   apply();
  }
 });
})();
