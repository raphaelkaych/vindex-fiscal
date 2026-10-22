# Entrega — conectores, master e produção

**Complemento posterior:** [continuação da captura e PDFs de NFS-e](CONTINUACAO-CAPTURA-PDFS.md). As contagens desta página são históricas; a fila avançou e o complemento registra uma conferência mais recente.

**21/10/2026, conferência às 16:22:38, Brasília.** Projeto existente preservado. Nenhum banco, XML real, certificado, senha ou chave privada foi incluído nos arquivos da entrega. As contagens abaixo são um retrato desse horário; a captura continua e o painel privado é a referência atual.

## Resultado efetivamente observado na Alpha Pet

Empresa piloto: **Alpha Pet LTDA, 55.737.823/0001-96**. Os três serviços foram consultados em **produção**, usando o A1 cifrado já vinculado, com autenticação mútua e validação TLS. Não houve envio de manifestação fiscal, consulta bancária ou contratação de serviço.

| Serviço | Documentos recebidos | Completos recebidos | Notas importadas | Outros documentos |
|---|---:|---:|---:|---|
| NF-e | 5.500 | 4 | **4** | 29 resumos, 2.436 eventos, 3.031 resumos de eventos |
| NFS-e / ADN | 198 | 195 | **182** | 3 eventos; 13 completos com impedimento local de schema |
| CT-e | 5.750 | 4.916 | **4.916** | 834 eventos |

Documentos recebidos não são a mesma coisa que notas completas importadas. Resumos e eventos não geram notas ou parcelas artificiais. Os números do CT-e continuavam aumentando automaticamente durante a conferência.

### Retomada da NF-e depois de 656

A espera da rejeição de 14:42:23 foi preservada. A primeira retomada começou às **15:43:27**, após o horário permitido de 15:43:23, e recebeu resposta oficial de **15:43:29**, **138 — Documento(s) localizado(s)**. Houve seis lotes posteriores de 50 documentos, incluindo um lote recuperado localmente.

No último lote, a resposta oficial aceita foi preservada, mas uma falha local impediu o armazenamento naquele instante. Na investigação, XSD e parser passaram; foi reproduzido **OperationalError: database is locked** durante a recuperação no SQLite. O código usa agora transações IMMEDIATE e timeout de 30 segundos no ambiente local, além de diagnóstico por etapa/tipo de exceção sem imprimir o payload.

Os 50 documentos da resposta preservada foram armazenados **sem nova consulta HTTP**. O cursor passou exclusivamente ao **ultNSU dessa resposta aceita**, **000000000090267**, mantendo a espera já registrada até **16:44:29**. O máximo conhecido é **000000000133770**: a fila não terminou. Última resposta oficial registrada: **15:44:27, código 138, Documento(s) localizado(s)**. O erro local foi resolvido e consta a recuperação na auditoria.

Isso não comprova a causa da rejeição 656 anterior. A sequência auditada não mostrou sobreposição ou NSU enviado diferente da continuação registrada. Não foi atribuída a outro software nem foi usado maxNSU para adiantar/zerar progresso. A estabilidade de longo prazo e futuras emissões ainda precisam de acompanhamento operacional.

### NFS-e nacional / ADN

O transporte real usa a API **Contribuintes**, não a API de prefeituras. A primeira consulta recebeu documentos reais, e o worker continuou pelas páginas até o cursor **198**. Último resultado: **21/10/2026, 15:41:05**, **HTTP 404**, status **NENHUM_DOCUMENTO_LOCALIZADO**, código **E2220**, motivo:

> Nenhum documento localizado - não existem documentos fiscais para o Contribuinte a partir do NSU informado.

Essa combinação documentada no contrato é **espera normal sem novos documentos**, não erro de certificado. A classificação foi corrigida, com teste específico, e a próxima consulta permaneceu às **16:42:05**. Não houve consulta antecipada.

Das 195 NFS-e completas recebidas, 182 passaram pelos schemas e pelo vínculo de tomador e foram importadas. Treze documentos 1.00 ficaram preservados com erro visível: elementos **pAliq** (11) e **xOutInf** (2) incompatíveis com os pacotes oficiais conhecidos nesta implementação. Não foram modificados para forçar aprovação. O reprocessamento é local e não baixa novamente o mesmo lote. Essa pendência depende de ajuste validado de cobertura do leiaute, não de você enviar certificado ou senha.

### CT-e

Transporte oficial **CTeDistribuicaoDFe**, modelo 57 padrão, confirmado pelo WSDL e schemas oficiais. A UF SP/35 do autor foi conferida nos XMLs reais já recebidos da empresa. Última consulta desta conferência: **21/10/2026, 16:22:18**, **HTTP 200**, **138 — documento localizado.** Cursor **000000000062831**, máximo **000000000080950**. A fila continuava paginando; não houve conclusão de todo o histórico.

Foram importados 4.916 CT-e reais no CNPJ correto. Eventos são separados dos documentos completos; cancelamentos identificados exigem retorno aceito correspondente e não alteram pagamento ou parcelas automaticamente. CT-e OS, GTV-e e CT-e simplificado não são importados como CT-e 57 padrão.

## O que foi implementado

- **Gestão master própria em /gestao/**, permissão explícita no servidor, busca/filtro/paginação de clientes, situação das contas, CNPJs, certificados/vencimentos, documentos e atividades.
- **Supervisão em leitura por URL**, mantendo a identidade do administrador e o Workspace explícito. Abas de clientes diferentes não compartilham seleção global. Detalhes mostram dados de pagamento e downloads privados; controles de acesso web, API e captura são separados, com CSRF/permissão operacional e auditoria.
- **Comando interativo criar_admin_master**, sem senha padrão/argumento de senha, confirmação explícita para conta existente, hash e validação Django. Nenhum login master real foi criado automaticamente.
- **Cadastro configurável por aprovação**, preservando contas existentes, mais fechamento do cadastro público quando desejado. Recuperação por e-mail preparada para SMTP; recuperação local por comando interativo.
- **Conectores executáveis NFSe/CTe**, com autorização por empresa/ambiente, A1 próprio validado, estado/reserva/cursor/intervalo separados, preservação prévia de resposta, entrega privada e prevenção de duplicidades. Recuperação local de resposta aceita também foi implementada para os novos conectores.
- **Formulário de A1 com autorizações por serviço**, agendamento no vínculo/renovação e preservação do progresso. Novos serviços não são habilitados pelo certificado sozinho. O processo Windows existente foi mantido e atualizado para os três conectores.
- **Painel consolidado por CNPJ/tipo**, separando completos de resumos/eventos e mostrando emissão e captura. A captura específica exibe requisitos, última consulta/importação, cursor, contagens e próxima tentativa.
- **Extração de pagamento com fonte/método/revisão**, baseada em campos estruturados e texto explicitamente rotulado. Sem dedução de conta do fornecedor a partir de cartão/adquirente ou de números aleatórios. Não há consulta a URLs/Pix bancários nem confirmação de pagamento. As previsões NF-e existentes e os vínculos de boleto permanecem idempotentes.
- **XML e representações auxiliares:** DANFE preservado para NF-e; DACTE disponível para CT-e, com geração em memória. Um CT-e real foi conferido com PDF válido, chave presente e XML inalterado. DANFSe permanece pendente: o GET de documentação oficial do serviço retornou HTTP 503; o contrato de download não foi validado nesta etapa.
- **API estendida**, com documentos NFS-e/CT-e, XML privado, pagamento extraído e estados de captura, mantendo credenciais/escopos por empresa. OpenAPI validado. A permissão master do proprietário não amplia o token.
- **Demonstrações retiradas do fluxo normal**, sem apagar registros, auditoria ou banco. As exclusões operacionais usam marcadores/proveniência, sem classificar pelo nome. Fixtures continuam somente nos testes isolados.
- **Preparação de implantação** com Docker Compose/Linux, PostgreSQL/Redis, Gunicorn/Nginx, proxy HTTPS, processos supervisionados, healthchecks, ambiente de exemplo sem segredos, backup cifrado e carga transacional somente em banco vazio. Manifestos conferem contagens/IDs/vínculos e abertura dos certificados com a chave preservada.

## Histórico e documentos novos

Na amostra efetivamente importada, as quatro NF-e têm emissão de **20 a 27/07/2026**; as 182 NFS-e, de **14/03/2025 a 20/10/2026**. Os CT-e da conferência estavam no início da fila histórica, a partir de **21/07/2026**. Esses documentos anteriores à ativação foram recuperados de fato; isso não significa recuperação de todo o histórico.

A NF-e considera disponibilidade/geração de NSU e recepção nacional, não promete emissão retroativa universal. CT-e documenta até três meses após recepção. O manual ADN consultado não define uma única janela histórica universal para prometer a todos os municípios. Notas não compartilhadas com o ADN não podem ser obtidas por esse conector.

Foi observado processamento automático de páginas e importação sem cliques após a configuração. **Não foi observada nesta janela a emissão de uma nova nota posterior à ativação, seguida de sua disponibilização pela origem.** Esse acompanhamento contínuo de futuras emissões não foi declarado como já comprovado. A rotina periódica e seus estados estão implementados; o aparecimento depende da disponibilização e dos intervalos da origem.

## Verificações

- **300 testes da versão final aprovados**, por `py iniciar.py --testar`, incluindo autenticação/escopo, master/CSRF, duas abas por URL, API restrita mesmo com proprietário master, vínculo A1 e autorização sem HTTP no formulário, serviços independentes, reinício/leases, reimportação, resposta preservada, espera e classificação ADN 404/E2220, eventos, pagamento incompleto e ausência de pagamento inventado.
- **32 verificações de tema/interações/DOM/CSS aprovadas**. OpenAPI validado; nenhuma migração pendente. `check --deploy` com DEBUG=False passou nos settings locais; isso não é homologação da infraestrutura Docker/PostgreSQL.
- Exportação cifrada e restauração testadas em **banco isolado com dados sintéticos**, preservando usuário, permissões e vínculos. O diagnóstico real informou zero falhas de abertura dos certificados. Não houve restauração sobre os dados reais.
- Consulta real de produção e importação comprovadas nos três serviços; heartbeat e tarefa Windows em execução; portal/saúde responderam HTTP 200.
- PDF DACTE fictício renderizado e inspecionado visualmente; DANFE já possuía conferência de retrato/paisagem/paginação. Os documentos reais usados para verificar geração permaneceram em memória.

**Inspeção visual no navegador não concluída:** a ferramenta encerrou o controle por não conseguir determinar a URL atual com confiança suficiente para aplicar sua política. A automação foi interrompida, sem tentativa de contornar esse bloqueio. Testes de servidor/DOM não foram apresentados como inspeção visual do navegador.

Também não foram feitos: publicação externa, build/execução Docker, homologação PostgreSQL/Redis/SMTP, reinício real do Windows/servidor, consulta de uma segunda empresa real, teste real de envio de Ciência, validação criptográfica independente de todos os XMLs ou comprovação de cobertura universal. DDA e operações bancárias continuam fora da etapa.

## O que depende de você

1. **Criar seu master**, escolhendo seu e-mail/senha no terminal, e entrar em /gestao/. Não foi criada senha por nós.
2. **Para cada empresa nova**, cadastrar o CNPJ, vincular o A1 e concluir as autorizações dos conectores na aplicação. CT-e requer UF. Depois disso, não precisa pedir novas alterações de código nem executar uma consulta por vez.
3. **No uso local**, manter o computador ligado, internet e a conta Windows conectada. A tarefa já está configurada. Certificado vencido, autorização pendente e rejeições exigem a ação exibida; um resumo que dependa de manifestação exige decisão específica do responsável.
4. **Para publicar**, escolher/preparar servidor/domínio/HTTPS e SMTP, preencher a configuração privada, migrar com a chave original e homologar a infraestrutura. Nenhum serviço foi contratado ou publicado automaticamente.

As 13 NFS-e de leiaute pendente e o DANFSe dependem de evolução/validação do conector. Não são resolvidos enviando senha no chat. A fila NF-e e a fila CT-e ainda precisam terminar sua leitura e de acompanhamento operacional.

Comandos exatos e URLs de cada função: [MASTER-E-CONECTORES.md](MASTER-E-CONECTORES.md). Implantação/migração: [IMPLANTACAO.md](IMPLANTACAO.md). Schemas e compatibilidades: [proveniência](../portal/services/schemas/LEIA-ME-CONECTORES.md).

## Comandos principais no Windows

```powershell
py iniciar.py --preparar
.\.venv\Scripts\python.exe manage.py criar_admin_master
py iniciar.py
```

Entre em **http://127.0.0.1:8000/entrar/** e acesse **http://127.0.0.1:8000/gestao/**. Se o portal já estiver aberto, atualize a página após criar seu master. Em **Minhas empresas > Conectores**, confira os serviços; em **Documentos consolidados**, filtre NF-e/NFS-e/CT-e. Abra a nota para XML, dados de pagamento e DANFE/DACTE, conforme o tipo.

**Confirmação do fluxo:** com certificado válido, autorizações/configurações concluídas e processo ativo, o sistema inicia e mantém as consultas automaticamente, retomando o progresso após reinício. Não exige intervenção no código ou conversa com o desenvolvedor a cada certificado, lote ou nova nota disponibilizada. Rejeições, falta de documentos e decisões fiscais continuam visíveis e respeitam as regras da origem.
