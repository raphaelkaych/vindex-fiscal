# API própria Vindex Fiscal v1

**Estado da conta:** uma credencial existente não autentica enquanto seu Workspace estiver aguardando aprovação ou suspenso, mesmo se o proprietário estiver ativo. A reativação não dispensa validade, revogação e escopos. Revisão de 22/10/2026, com testes de leitura/escrita.

**Atualização de processamento:** documentos tipados expõem `validation_status` (`schema` ou `partial`), detalhes da validação e substituição. A listagem aceita o filtro `validation_status`. Importações parciais permanecem sinalizadas e não comprovam validade fiscal. O XML original continua privado; listas não carregam XML/PDF integralmente. As permissões e o escopo por Workspace permanecem iguais.

API própria independente, com contrato inicial de 20/10/2026 e atualização de documentação em 21/10/2026. Base: `http://127.0.0.1:8000/api/v1/` no desenvolvimento; HTTPS obrigatório em produção. Não exige conta Qive. A captura oficial SEFAZ funciona pelo portal e pelo worker, com consentimento por empresa. Disparar captura ou manifestações fiscais, DDA, execução de pagamentos, emissão de notas e DANFE não são operações desta API.

## Iniciar e autorizar outro sistema no Windows

1. Nesta pasta, execute `py iniciar.py --preparar` para instalar dependências e aplicar as migrações preservando o banco existente.
2. Execute `py iniciar.py` e abra `http://127.0.0.1:8000`.
3. Entre na sua conta e abra **Integrações e API > Criar credencial**. Informe o sistema, as empresas, permissões e uma validade futura.
4. Guarde a credencial completa apresentada nessa resposta no gerenciador de segredos do sistema integrado. O segredo não reaparece ao voltar à lista.
5. Use `Authorization: Bearer <credencial>` em cada requisição. O login do navegador não autentica a API.
6. Para encerrar o acesso, use **Revogar acesso** na mesma área. A próxima requisição será recusada. Para renovar, emita outra credencial, atualize o sistema e revogue a anterior.

A validade padrão é de 90 dias; a máxima é 365 dias. O responsável técnico pode configurar `API_CREDENTIAL_DEFAULT_DAYS` e `API_CREDENTIAL_MAX_DAYS`. Não existe credencial padrão, sem validade ou segredo de API derivado da chave dos certificados.

## Autenticação mantida

Credenciais opacas no formato `vfx_<prefixo público>.<segredo aleatório>`: prefixo de 16 caracteres hexadecimais e segredo `secrets.token_urlsafe(32)` (256 bits de entropia). O banco guarda o prefixo e somente o hash PBKDF2-SHA256 com sal gerado e verificado pelas funções mantidas do Django `make_password`/`check_password`; a verificação usa comparação em tempo constante. A resposta de criação usa `Cache-Control: no-store`, sem segredo em sessão, URL, auditoria ou listagem. Swagger não persiste autorização no navegador.

Cada credencial pertence a um Workspace e contém uma lista explícita de empresas. Nenhuma empresa selecionada significa nenhum acesso às empresas existentes. As consultas também verificam o Workspace da empresa. Usuários inativos, credenciais expiradas e revogadas são recusados. A gestão exige sessão do proprietário e CSRF; revogação é somente POST.

| Escopo | Operações |
|---|---|
| `read` | GET, HEAD e OPTIONS dos recursos autorizados; download privado |
| `write` | POST e PATCH implementados, sem pagamentos nem ações fiscais externas |

Selecione ambos para uma integração que consulta e importa. `write` permite criar uma empresa nova no Workspace da credencial; o servidor inclui explicitamente esse novo cadastro nas empresas da própria credencial. Isso não concede acesso a uma empresa existente: CNPJ já cadastrado produz erro. Nenhum corpo de escrita aceita `workspace`, `workspace_id`, ID arbitrário, segredo de certificado ou estado de pagamento.

Em produção use `DJANGO_DEBUG=0`, HTTPS e configuração confiável do proxy. Não envie o cabeçalho para logs do proxy, ferramentas de rastreamento ou relatórios externos. O filtro de erros remove `Authorization`; erros inesperados da API retornam JSON genérico e não mostram payloads nem tracebacks. CORS não foi habilitado: integração servidor a servidor não precisa de CORS.

## Endpoints implementados

URLs terminam com `/`. Todos os recursos de negócio exigem credencial. Downloads são privados, passam pelo mesmo escopo e não possuem URL pública de armazenamento.

| Método | Caminho relativo a `/api/v1/` | Comportamento |
|---|---|---|
| GET, POST | `empresas/` | Lista autorizadas / cadastra uma nova empresa |
| GET | `empresas/{id}/` | Dados de uma empresa autorizada |
| GET | `notas/` | Lista NF-e completas importadas, com origem e revisão |
| GET | `notas/{id}/` | Dados da nota, cobrança/pagamento declarados e parcelas |
| POST | `notas/importar/` | XML modelo 55, multipart campo `file`, até 2 MB |
| GET | `notas/{id}/xml/` | XML privado, `application/xml` |
| GET, POST | `parcelas/` | Lista previsões / informa uma previsão revisada |
| GET, PATCH | `parcelas/{id}/` | Consulta / corrige previsão, com motivo e auditoria |
| POST | `parcelas/{id}/conferir/` | Define somente a conferência dos dados |
| GET | `boletos/` | Lista cobranças locais |
| GET, PATCH | `boletos/{id}/` | Consulta com histórico / revisa dados declarados |
| POST | `boletos/importar/` | Dados estruturados JSON ou PDF multipart, até 5 MB e 10 páginas |
| GET | `boletos/{id}/arquivo/` | PDF privado; 404 se o registro não tem PDF |
| POST | `boletos/{id}/associar/` | Associa a parcela da mesma empresa; `null` desfaz vínculo |
| GET | `certificados/` | Metadados e validade; nenhum conteúdo criptográfico |
| GET | `certificados/{id}/` | Metadados de certificado autorizado |
| GET | `schema/`, `docs/`, `redoc/` | OpenAPI, Swagger UI e ReDoc públicos; sem dados dos clientes |

Importação XML retorna `201` e `created: true` quando cria; `200` e `created: false` quando empresa/chave já existe. Boletos têm idempotência por empresa+código normalizado e empresa+SHA256 do PDF. Não sobrescreva divergências reenviando o documento: revise o registro existente. PDF anexado em reenvio do mesmo código não cria nova obrigação.

Não há endpoint REST de habilitação, disparo ou acompanhamento da captura, nem de envio de manifestações. O conector oficial e o worker são serviços internos; configure e acompanhe a captura com a sessão do proprietário em **Captura de NF-e**. `py iniciar.py` inicia o portal e o worker; somente empresas com certificado compatível válido e leitura autorizada entram na fila. Credenciais `read`/`write` da API não autorizam consultas externas ou eventos fiscais. Não há download de A1/PFX/P12 nem upload de certificado por esta API. CT-e, NFS-e, eventos e resumos não entram no importador XML completo. Resumos e eventos recebidos na distribuição têm armazenamento e telas privadas próprios.

XMLs completos recebidos e importados pela captura ficam disponíveis em `notas/` e `notas/{id}/xml/` somente para credenciais com acesso à empresa e escopo de leitura. A mesma chave por empresa continua impedindo duplicidades entre importação manual, API e captura. Consulte [INTEGRACAO-SEFAZ.md](../INTEGRACAO-SEFAZ.md) para a configuração e as limitações da distribuição.

## Campos de escrita e exemplos fictícios

Empresa: `legal_name` e `cnpj` obrigatórios, `trade_name` opcional. CNPJ pode conter máscara, é normalizado e validado. A identidade por CNPJ é preservada; não há edição do CNPJ pela API.

```json
{"legal_name":"EMPRESA FICTÍCIA SEM VALOR FISCAL","trade_name":"Exemplo fictício","cnpj":"00000003000125"}
```

Previsão: `invoice`, `number`, `amount` e `review_note` obrigatórios na criação. `due_on` é opcional ou `null` quando desconhecido. No PATCH, envie somente `number`, `amount`, `due_on` e uma `review_note` obrigatória explicando a correção. `invoice` não pode ser alterada. Duplicar o identificador dentro da nota é rejeitado. Alterações de valor, data ou identificador com boleto associado exigem desfazer o vínculo e revisar a associação depois.

```json
{"invoice":123,"number":"ACORDO-01","amount":"250.30","due_on":null,"review_note":"EXEMPLO FICTÍCIO: condição comercial conferida no documento de origem."}
```

Conferência: `{"checked":true}` ou `{"checked":false}`. Não agenda, paga ou confirma liquidação.

Boleto: `company` obrigatório; envie `digitable_line` e/ou `barcode` validados ou um `file` PDF. Campos opcionais: `amount`, `due_on`, `beneficiary_name`, `beneficiary_document`, `payer_name`, `payer_document`, `reference`. O pagador declarado deve coincidir com o CNPJ da empresa. Não envie uma linha inventada: use os dados do documento que deseja analisar. PDF sem texto é armazenado como pendente com orientação para revisão; OCR não é executado nesta entrega.

No PATCH de boleto, são permitidos os mesmos campos de dados, sem `company` e `file`. A revisão registra antes/depois. Dados divergentes de uma parcela já vinculada exigem desfazer o vínculo antes da alteração.

Associação: `{"installment":456}`. Se valor, vencimento, pagador ou beneficiário não estiverem confirmados/compatíveis, inclua `review_reason` entre 10 e 1.000 caracteres. O motivo documenta a análise de cessão/intermediário quando aplicável. Não existe associação automática ambígua. Uma parcela só tem um boleto; associar não cria outra parcela. `{"installment":null}` desfaz o vínculo e registra auditoria.

## Filtros, ordenação e paginação

Filtros são combinados e restritos às empresas autorizadas. Empresa sem autorização produz 404; filtro desconhecido, valor inválido ou ordenação fora da lista produz 400.

Todos os recursos: `company` (ID), `cnpj` completo, `ordering`, `page` e `page_size`. Notas e empresas aceitam `q`. Notas, parcelas e boletos aceitam `supplier` (nome parcial ou CNPJ). `from` e `to` são datas inclusivas `AAAA-MM-DD`: emissão para notas, vencimento para parcelas/boletos. Previsões sem vencimento não aparecem em períodos de vencimento; use `state=undated` para consultá-las.

| Recurso | Filtros adicionais | Campos de ordenação |
|---|---|---|
| Empresas | `q` nome/CNPJ | `id`, `legal_name`, `cnpj`, `created_at` |
| Notas | `q`, `supplier`, `source=xml/api_xml/sefaz/demo`, `review=pending/clear` | `id`, `issued_on`, `total`, `number`, `imported_at` |
| Parcelas | `supplier`, `source=xml/manual`, `checked=true/false`, `invoice`, `state=past_due_date/upcoming/undated` | `id`, `due_on`, `amount`, `number` |
| Boletos | `supplier`, `source=pdf/manual/api`, `review=pending/clear`, `validation_state=validated/pending`, `linked=true/false`, `invoice` | `id`, `due_on`, `amount`, `imported_at` |
| Certificados | Somente filtros comuns | `id`, `valid_until`, `uploaded_at` |

`source=sefaz` identifica a importação pelo pipeline de distribuição oficial. O histórico da captura no portal registra as respostas oficiais e os intervalos; uma origem de nota não indica que o worker está conectado neste instante nem que a situação fiscal vigente foi novamente consultada. `review=clear` significa ausência de avisos locais, não autenticidade fiscal/bancária. `validation_state=validated` significa somente dígitos matematicamente conferidos. `past_due_date` descreve uma data passada, sem afirmar inadimplência.

Exemplo: `notas/?company=123&from=2026-10-01&to=2026-10-31&ordering=-issued_on&page_size=25`.

Paginação padrão 25, máximo 100. Resposta:

```json
{"count":0,"next":null,"previous":null,"results":[]}
```

Use `next` até `null`. `ordering=-amount,due_on` é aceito onde os dois campos forem permitidos. A ordenação adiciona o ID como desempate.

## Valores, datas e estados

Valores monetários são texto decimal com duas casas (`"1200.00"`), sem conversão para ponto flutuante. Na escrita, use texto decimal: floats JSON são recusados; não há arredondamento de três casas. Datas de emissão e vencimento são datas sem horário. Timestamps usam ISO 8601 com fuso.

`payment_details` e `billing_details` preservam o que foi declarado no XML. Não comprovam liquidação. Parcelas são `financial_status: "forecast"`; boletos são `financial_status: "unknown"`. `checked` registra revisão. Valores originais de duplicatas ficam em `original_data`, separados da revisão manual e do histórico. Nenhum vencimento, pagamento, linha digitável ou condição comercial ausente é inventado.

## Erros e limites

```json
{"error":{"code":"validation_error","message":"Confira os dados enviados.","details":{"amount":["Envie o valor como texto decimal, por exemplo \"123.45\"."]}}}
```

| HTTP | Uso |
|---|---|
| 400 | Dados/filtros inválidos, XML não suportado, escopo de relacionamento inválido, divergências que exigem revisão |
| 401 | Credencial ausente, inválida, expirada, revogada, usuário inativo ou HTTPS obrigatório |
| 403 | Escopo read/write insuficiente |
| 404 | Registro/empresa/arquivo indisponível para o acesso; endpoint desconhecido |
| 405 | Método não implementado |
| 409 | Conflito de unicidade concorrente |
| 413, 415 | Requisição grande demais ou tipo de conteúdo não aceito |
| 429 | Limite de requisições/autenticação; respeite `Retry-After` |
| 500 | Falha inesperada, mensagem genérica sem conteúdo privado |

Limites padrão: 120 requisições/minuto por credencial e 20 gravações/minuto por credencial; antes da verificação do hash, 180 autenticações/minuto por endereço e bloqueio após 30 falhas/minuto. Os controles DRF/cache são mitigação local e não substituem limites no proxy. O cache local não coordena múltiplos processos; configure cache compartilhado e proteção do proxy antes de publicar. Configurações do servidor/proxy podem impor limites menores de tamanho.

## OpenAPI, exemplos e verificação

Abra `/api/v1/docs/` ou `/api/v1/redoc/`. Os arquivos Swagger/ReDoc são servidos pelo sidecar local, sem CDN. A documentação é pública e só descreve estruturas; os botões de execução exigem sua própria credencial. Nunca coloque uma credencial real nos arquivos de exemplo.

Exemplos completos para um sistema externo: [PowerShell](api-examples.ps1), [cURL](api-examples.sh) e [coleção Postman](postman-vindex-v1.json). Configure `VINDEX_API_TOKEN` no ambiente do processo por um gerenciador de segredos, escolha um XML fictício ou autorizado e use os IDs retornados pela sua instalação. A coleção contém somente variáveis vazias e placeholders.

```powershell
py iniciar.py --testar
.\.venv\Scripts\python.exe manage.py spectacular --validate --fail-on-warn --file docs/openapi.yaml
.\docs\api-examples.ps1 -XmlPath "C:\caminho\exemplo-ficticio.xml"
```

`--testar` usa banco de teste e documentos sintéticos, sem contatar governo, banco ou fornecedor. A geração do OpenAPI é validada e as rotas reais são verificadas por testes. Este resultado não substitui homologação com certificados, infraestrutura e provedores reais.

Mudanças incompatíveis ganharão outro prefixo (por exemplo `/api/v2/`). Novos campos/endpoints compatíveis podem ser incluídos em v1; integrações devem tolerar campos adicionais nas respostas. Endpoints futuros só serão documentados quando disponíveis.

Fontes oficiais conferidas em 20/10/2026: [Django REST Framework 3.18.3 e requisitos](https://pypi.org/project/djangorestframework/3.18.3/), [drf-spectacular 0.30.0](https://pypi.org/project/drf-spectacular/0.30.0/), [sidecar e configuração](https://drf-spectacular.readthedocs.io/en/stable/readme.html), [autenticação customizada DRF](https://www.django-rest-framework.org/api-guide/authentication/), [hashes de senha Django 5.2](https://docs.djangoproject.com/en/5.2/topics/auth/passwords/). A compatibilidade do conjunto instalado foi conferida pelos testes locais e geração do esquema.
# Extensões de 21/10/2026

Novos recursos somente de leitura, sempre com a credencial e seus CNPJs autorizados: `/api/v1/documentos-fiscais/`, `/api/v1/documentos-fiscais/{id}/xml/`, `/api/v1/conectores/` e `/api/v1/capturas-nfe/`. Os documentos aceitam `service=nfse|cte`, `environment=1|2`, filtros de empresa/período e paginação. O contexto master não amplia o escopo da credencial. Detalhes de NF-e incluem `payment_evidence`; os novos documentos incluem `payment_data`, com fonte e método. Não há disparo de captura ou manifestação pela API. O OpenAPI atualizado em `docs/openapi.yaml` descreve as operações implementadas. Veja [MASTER-E-CONECTORES.md](MASTER-E-CONECTORES.md).

