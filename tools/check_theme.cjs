/* Verificações sem dependências: node tools/check_theme.cjs */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../static/portal/theme.js'), 'utf8');
const key = 'vindex-fiscal-theme';
let passed = 0;
function check(name, run) {
 run();
 passed += 1;
 process.stdout.write(`OK ${name}\n`);
}
function eventTarget() {
 const listeners = new Map();
 return {
  addEventListener(type, callback, options = {}) {
   if (!listeners.has(type)) listeners.set(type, []);
   listeners.get(type).push({callback, once: options.once});
  },
  emit(type, event = {}) {
   const current = [...(listeners.get(type) || [])];
   for (const listener of current) {
    listener.callback(event);
    if (listener.once) listeners.set(type, listeners.get(type).filter(item => item !== listener));
   }
  },
 };
}
function element() {
 const attributes = new Map();
 return Object.assign(eventTarget(), {
  hidden: false, value: '', textContent: '', dataset: {},
  setAttribute(name, value) { attributes.set(name, String(value)); },
  getAttribute(name) { return attributes.get(name) ?? null; },
  toggleAttribute(name, force) {
   if (force) attributes.set(name, '');
   else attributes.delete(name);
  },
  hasAttribute(name) { return attributes.has(name); },
 });
}
function setup({saved = null, dark = false, ready = 'complete', denied = false, legacyMedia = false, count = 1} = {}) {
 const storage = new Map(saved === null ? [] : [[key, saved]]);
 const root = element();
 const controls = Array.from({length: count}, () => {
  const wrapper = element(); wrapper.hidden = true;
  const button = element();
  const moon = element(); const sun = element();
  const label = element();
  button.querySelector = selector => ({
   '[data-theme-label]': label,
   '[data-theme-icon="moon"]': moon,
   '[data-theme-icon="sun"]': sun,
  })[selector] ?? null;
  return {wrapper, button, moon, sun, label};
 });
 let mounted = ready !== 'loading';
 const document = Object.assign(eventTarget(), {
  documentElement: root, readyState: ready,
  querySelectorAll(selector) {
   if (!mounted) return [];
   const property = {
    '[data-theme-controls]': 'wrapper', '[data-theme-toggle]': 'button',
   }[selector];
   assert.ok(property, `Seletor conhecido: ${selector}`);
   return controls.map(control => control[property]);
  },
 });
 const system = Object.assign(eventTarget(), {matches: dark});
 if (legacyMedia) {
  system.addListener = callback => { system.oldListener = callback; };
  delete system.addEventListener;
 }
 const localStorage = {
  getItem(name) { if (denied) throw Error('SecurityError'); return storage.get(name) ?? null; },
  setItem(name, value) { if (denied) throw Error('SecurityError'); storage.set(name, value); },
 };
 const window = Object.assign(eventTarget(), {matchMedia: () => system, localStorage});
 vm.runInNewContext(source, {document, window}, {filename: 'theme.js'});
 return {
  root, controls, storage, system,
  mount() { mounted = true; document.readyState = 'interactive'; document.emit('DOMContentLoaded'); },
  click(index = 0) { controls[index].button.emit('click'); },
  os(value) { system.matches = value; if (legacyMedia) system.oldListener(); else system.emit('change'); },
  external(newValue, name = key) { window.emit('storage', {key: name, newValue}); },
 };
}
function state(app, theme, preference) {
 assert.equal(app.root.dataset.theme, theme);
 assert.equal(app.root.dataset.themePreference, preference);
 for (const control of app.controls) {
  const dark = theme === 'dark';
  const label = dark ? 'Ativar modo claro' : 'Ativar modo escuro';
  assert.equal(control.wrapper.hidden, false);
  assert.equal(control.label.textContent, label);
  assert.equal(control.button.getAttribute('aria-label'), label);
  assert.equal(control.button.title, label);
  assert.equal(control.button.getAttribute('aria-pressed'), String(dark));
  assert.equal(control.moon.hasAttribute('hidden'), dark);
  assert.equal(control.sun.hasAttribute('hidden'), !dark);
 }
}

check('aplica preferência antes do DOM e liga o botão após DOMContentLoaded', () => {
 const app = setup({saved: 'dark', ready: 'loading'});
 assert.equal(app.root.dataset.theme, 'dark');
 assert.equal(app.controls[0].wrapper.hidden, true);
 app.mount(); state(app, 'dark', 'dark');
 app.click(); state(app, 'light', 'light');
});
check('funciona quando o DOM já está pronto', () => {
 const app = setup({saved: 'light', dark: true}); state(app, 'light', 'light');
 app.click(); state(app, 'dark', 'dark');
});
check('migra ausência de preferência para sistema', () => {
 const app = setup({dark: true}); state(app, 'dark', 'system');
 assert.equal(app.storage.get(key), 'system');
});
check('sistema → manual → sistema com mudanças do dispositivo', () => {
 const app = setup(); state(app, 'light', 'system');
 app.os(true); state(app, 'dark', 'system');
 app.click(); state(app, 'light', 'light');
 app.os(false); app.os(true); state(app, 'light', 'light');
 app.external('system'); state(app, 'dark', 'system');
 app.os(false); state(app, 'light', 'system');
});
check('botão mantém modos manuais independente do sistema', () => {
 const app = setup();
 app.click(); app.os(false); state(app, 'dark', 'dark');
 app.click(); app.os(true); state(app, 'light', 'light');
});
check('persiste para a próxima página e após recarregar', () => {
 const app = setup(); app.click();
 const reload = setup({saved: app.storage.get(key)}); state(reload, 'dark', 'dark');
 app.click();
 const next = setup({saved: app.storage.get(key), dark: true}); state(next, 'light', 'light');
});
check('atualiza todos os controles presentes em conjunto', () => {
 const app = setup({count: 2}); app.click(1); state(app, 'dark', 'dark');
 app.external('system'); state(app, 'light', 'system');
});
check('mudança em outra aba sincroniza texto e ícone', () => {
 const app = setup(); app.external('dark'); state(app, 'dark', 'dark');
 app.external('light'); state(app, 'light', 'light');
 app.external('system'); state(app, 'light', 'system');
});
check('ignora eventos de outras chaves', () => {
 const app = setup({saved: 'dark'}); app.external('light', 'outra-chave'); state(app, 'dark', 'dark');
});
check('remoção, limpeza e valores inválidos voltam ao sistema', () => {
 const app = setup({saved: 'dark'}); app.external(null); state(app, 'light', 'system');
 app.click(); app.external(null, null); state(app, 'light', 'system');
 app.external('invalido'); state(app, 'light', 'system');
 const invalid = setup({saved: 'invalido', dark: true}); state(invalid, 'dark', 'system');
});
check('armazenamento bloqueado preserva o funcionamento na página', () => {
 const app = setup({denied: true}); state(app, 'light', 'system');
 app.click(); state(app, 'dark', 'dark');
 app.external('system'); app.os(true); state(app, 'dark', 'system');
});
check('suporta listener de sistema legado', () => {
 const app = setup({legacyMedia: true}); app.os(true); state(app, 'dark', 'system');
});
check('DOMContentLoaded registra os ouvintes apenas uma vez', () => {
 const app = setup({ready: 'loading'}); app.mount(); app.mount();
 app.click(); state(app, 'dark', 'dark');
});
process.stdout.write(`${passed} verificações de tema passaram.\n`);
