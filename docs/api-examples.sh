#!/usr/bin/env sh
# Cliente externo com cURL. Segredo somente no ambiente; não use set -x.
set -eu
: "${VINDEX_API_TOKEN:?Configure VINDEX_API_TOKEN pelo gerenciador de segredos}"
: "${VINDEX_COMPANY_ID:?Informe um ID de empresa retornado pela listagem autorizada}"
: "${VINDEX_XML_PATH:?Informe o caminho de um XML fictício ou autorizado}"
VINDEX_API_BASE="${VINDEX_API_BASE:-http://127.0.0.1:8000/api/v1}"

case "$VINDEX_API_BASE" in
  https://*|http://127.0.0.1:*/api/v1|http://localhost:*/api/v1) ;;
  *) printf '%s\n' 'Use HTTPS fora do desenvolvimento local.' >&2; exit 1 ;;
esac

# Cada requisição é autenticada pelo cabeçalho Bearer; não há endpoint de senha/login da API.
curl --fail-with-body --silent --show-error \
  -H "Authorization: Bearer ${VINDEX_API_TOKEN}" \
  -H 'Accept: application/json' "${VINDEX_API_BASE}/empresas/"

curl --fail-with-body --silent --show-error \
  -H "Authorization: Bearer ${VINDEX_API_TOKEN}" \
  -H 'Accept: application/json' \
  "${VINDEX_API_BASE}/notas/?company=${VINDEX_COMPANY_ID}&ordering=-issued_on&page_size=25"

curl --fail-with-body --silent --show-error \
  -H "Authorization: Bearer ${VINDEX_API_TOKEN}" \
  -H 'Accept: application/json' \
  -F "file=@${VINDEX_XML_PATH};type=application/xml" "${VINDEX_API_BASE}/notas/importar/"
