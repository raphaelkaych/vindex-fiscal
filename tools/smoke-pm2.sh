#!/usr/bin/env bash
# Exclusivo CI/ambiente vazio: nunca usar com a carteira real.
set -euo pipefail
export DJANGO_SETTINGS_MODULE=config.production
.venv/bin/python - <<'PY'
import django
django.setup()
from portal.models import Company,DigitalCertificate
assert not Company.objects.exists() and not DigitalCertificate.objects.exists(), 'Smoke PM2 exige banco vazio, sem clientes/certificados.'
PY
pm2 start ecosystem.config.js
trap 'pm2 delete ecosystem.config.js' EXIT
for i in $(seq 1 30); do
  if curl --fail --silent http://127.0.0.1:8000/saude/; then break; fi
  sleep 1
done
curl --fail http://127.0.0.1:8000/saude/
old_pid="$(pm2 pid vindex-captura)"
test "$old_pid" -gt 1
kill -KILL "$old_pid"
new_pid=0
for i in $(seq 1 30); do
  sleep 1
  new_pid="$(pm2 pid vindex-captura)"
  if [[ "$new_pid" =~ ^[0-9]+$ ]] && test "$new_pid" -gt 1 && test "$new_pid" != "$old_pid"; then break; fi
done
test "$new_pid" -gt 1
test "$new_pid" != "$old_pid"
pm2 restart vindex-web
for i in $(seq 1 30); do
  if curl --fail --silent http://127.0.0.1:8000/saude/; then break; fi
  sleep 1
done
curl --fail http://127.0.0.1:8000/saude/
.venv/bin/python manage.py verificar_captura
pm2 save
echo 'PM2: web acessível, captura recuperada após queda e fila vazia preservada. Boot real requer startup no servidor.'
