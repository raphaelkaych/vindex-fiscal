/* PM2 supervisiona; Django conserva fila, NSU, consentimentos e intervalos. */
const path = require('path');
const root = __dirname;
const runtime = process.env.VINDEX_RUNTIME_DIR || '/var/lib/vindex/runtime';
const common = {
  cwd: root, interpreter: path.join(root, '.venv/bin/python'),
  instances: 1, exec_mode: 'fork', watch: false, autorestart: true,
  min_uptime: '30s', max_restarts: 20, exp_backoff_restart_delay: 2000,
  kill_timeout: 180000, time: true, merge_logs: true,
  env: { DJANGO_SETTINGS_MODULE: 'config.production',
    VINDEX_ENV_FILE: process.env.VINDEX_ENV_FILE || '/etc/vindex/vindex.env',
    PYTHONUNBUFFERED: '1', PYTHONDONTWRITEBYTECODE: '1',
    LD_LIBRARY_PATH: process.env.VINDEX_SQLITE_LIB_DIR || '/opt/vindex/sqlite/lib' }
};
module.exports = { apps: [
  { ...common, name: 'vindex-web', script: 'tools/production_web.py',
    out_file: path.join(runtime, 'web-out.log'), error_file: path.join(runtime, 'web-error.log') },
  { ...common, name: 'vindex-captura', script: 'manage.py', args: 'capturar_sefaz --aguardar-instancia',
    out_file: path.join(runtime, 'captura-out.log'), error_file: path.join(runtime, 'captura-error.log') },
  { ...common, name: 'vindex-backup', script: 'tools/production_backup.py',
    out_file: path.join(runtime, 'backup-out.log'), error_file: path.join(runtime, 'backup-error.log') }
] };
