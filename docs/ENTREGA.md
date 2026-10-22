# Entrega de 20/10/2026

Este é um registro histórico. O estado atual da captura oficial e sua verificação estão em [INTEGRACAO-SEFAZ.md](../INTEGRACAO-SEFAZ.md); as afirmações abaixo sobre ausência de transporte e consultas reais se referem exclusivamente à entrega de 20/10/2026.

O diagnóstico foi registrado antes da implementação em [DIAGNOSTICO.md](DIAGNOSTICO.md) e na [matriz funcional com fontes](MATRIZ-FUNCIONAL.md). A plataforma continua independente da Qive, com o mesmo Django, banco existente, Workspaces e tema claro/escuro.

## Recursos entregues

| Área | Comportamento disponível |
|---|---|
| Boletos | Importação local de PDF/dados, extração textual limitada, revisão, DVs 44/47/48, origem, histórico e arquivo privado. Datas ambíguas permanecem candidatas; valor de cobrança exige declaração explícita. |
| Associações | Boleto e parcela da mesma empresa, com revisão de divergências e um vínculo por parcela. Importar/associar não cria segunda obrigação. |
| Previsões | Inclusão e correção com motivo, origem e histórico antes/depois. Dados originais e XML preservados. Conferência continua separada do pagamento. |
| XML | Campos de fatura e detalhes de pagamento declarados ficam separados das previsões. XML anterior permanece preservado; a nova extração vale para novas importações. |
| API v1 | Empresas, notas, parcelas, boletos, arquivos, associação e metadados de certificados. Credenciais opacas individuais, hash do segredo, empresas/escopos, validade e revogação. |
| Documentação | OpenAPI validado, Swagger/ReDoc locais, exemplos PowerShell/cURL e coleção Postman sem segredos. |
| SEFAZ local | Estado NSU, lease, intervalos, retentativas, resposta compactada e separação de XML completo/resumos/eventos, testados sinteticamente. Sem transporte ou worker real. |
| Produção | Configuração opcional para PostgreSQL e Redis; padrões locais preservados. Não houve implantação ou homologação nesses serviços. |

Nenhum pagamento, baixa, comprovante de liquidação, manifestação fiscal real, consulta DDA ou consulta SEFAZ foi executado. Estado financeiro da parcela é previsão; do boleto, pagamento não consultado. Certificado cadastrado continua sem indicar conexão governamental.

## Verificação realizada

Execução integrada por `.venv\Scripts\python.exe iniciar.py --testar`: **147 testes aprovados em 64,014 segundos** no Windows, Python 3.15, Django 5.2.18, DRF 3.18.3, drf-spectacular 0.30.0 e pypdf 6.21.1.

| Suíte | Testes |
|---|---:|
| Base anterior: acesso, XML, certificados e isolamento | 38 |
| API, escopos, credenciais, arquivos e esquema | 41 |
| Boletos, PDF, revisão, associação, precisão e privacidade | 35 |
| Revisão financeira e preservação da rota/painel | 8 |
| Distribuição SEFAZ local e controles de NSU | 25 |
| Total | 147 |

Após o ajuste final do formulário para aceitar exatamente R$ 0,01 sem comparação com float, os 8 testes financeiros foram repetidos e passaram. A sintaxe do exemplo PowerShell e o JSON da coleção Postman também foram verificados.

Também passaram: `manage.py check`; `manage.py makemigrations --check --dry-run` sem alterações; `manage.py spectacular --file docs/openapi.yaml --validate --fail-on-warn` sem erros/avisos. A migração aditiva `0002_api_boletos_previsoes_distribuicao` foi aplicada. Nenhuma conta padrão ou credencial de integração foi criada no banco existente. Os testes usam banco temporário e documentos fictícios em memória.

A revisão independente de segurança corrigiu duas incertezas: alertas de PDF agora sobrevivem à revisão com histórico; o valor usual de dez posições da cobrança não é mais tratado como valor definitivo diante da modalidade de valor alto que ocupa o fator. Não foram encontradas falhas concretas remanescentes nos fluxos revisados de Workspace, allowlist, relacionamentos ou downloads. Isso não é certificação de segurança nem homologação bancária/governamental.

Não houve inspeção visual completa em navegador, teste de carga, homologação com certificados/boletos reais, implantação pública ou teste em PostgreSQL/Redis. O limite de OCR e a ausência dos conectores estão explícitos nas telas.

## Como experimentar no Windows

Se o servidor estiver aberto, encerre-o com Ctrl+C e execute na pasta do projeto:

```powershell
py iniciar.py
```

Se o atalho `py` não existir:

```powershell
.\.venv\Scripts\python.exe iniciar.py
```

O inicializador instala as dependências quando necessário, aplica migrações e abre o servidor. Acesse `http://127.0.0.1:8000` e atualize com Ctrl+F5.

1. Em **Boletos**, importe um documento fictício/autorizado, confira os campos e revise as pendências. Para um scan, preencha manualmente os dados encontrados.
2. Abra uma nota e use **Informar previsão manual** ou **Revisar dados**; forneça a origem/motivo e confira a parcela.
3. Em **Associar parcela**, escolha a mesma empresa/obrigação. Divergências exigem análise e justificativa. Confira que o painel não soma novamente o boleto.
4. Em **Integrações e API**, crie uma credencial, escolha empresas/escopos/validade e guarde o segredo mostrado uma vez. Não o envie ao chat ou ao repositório.
5. Abra `http://127.0.0.1:8000/api/v1/docs/` ou `/api/v1/redoc/`; autorize usando sua credencial e teste os recursos locais. Revogue na aplicação quando terminar.

Para repetir a suíte: `py iniciar.py --testar` (ou use o Python da `.venv` acima). Para regenerar o contrato: `.\.venv\Scripts\python.exe manage.py spectacular --file docs/openapi.yaml --validate --fail-on-warn`.

## Dependências e próximos passos

- **SEFAZ:** implementar transporte mTLS e worker; obter autorização/certificado adequado; homologar TLS, sequência do CNPJ entre consumidores, regras de distribuição e manifestações. Veja [INTEGRACAO-SEFAZ.md](../INTEGRACAO-SEFAZ.md).
- **DDA:** selecionar instituição/provedor que ofereça consulta ao pagador, verificar contrato, adesão, consentimento, credenciais, custo e cobertura; implementar conector sem confundir com cobrança do beneficiário.
- **OCR:** escolher ferramenta/serviço e critério de confiança; manter revisão e arquivos privados.
- **CT-e, NFS-e e DANFE:** análise e implementação próprias; não suportados pelo importador atual.
- **Produção:** validar PostgreSQL, cache compartilhado, proxy HTTPS, logs, backup/restauração e carga, conforme [PRODUCAO.md](PRODUCAO.md).

Referências de uso: [API](API.md), [OpenAPI](openapi.yaml), [PowerShell](api-examples.ps1), [cURL](api-examples.sh), [Postman](postman-vindex-v1.json), [boletos e fontes oficiais](BOLETOS.md).
