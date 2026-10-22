# Vindex Fiscal — encerramento da fase local e preparação para hospedagem

Revisão de **22/10/2026**, fuso **America/Sao_Paulo (UTC−3)**. Documento de passagem para a próxima sessão/desenvolvedor. As contagens são um retrato, não um indicador em tempo real. Substitui os relatórios anteriores como referência de situação; eles permanecem como evidência histórica.

**Conclusão:** aplicação funcional localmente, com consultas reais comprovadas, isolamento e migração preparados em código. **Ainda não liberada para publicação pública.** A captura de NF-e do piloto continua com rejeição 656; PostgreSQL, infraestrutura, restauração do volume real e operação no servidor ainda precisam de homologação. NFS-e e CT-e funcionando não resolvem a NF-e.

Nesta revisão **não foram disparadas consultas fiscais, manifestações, recuperação remota de XML/PDF ou capturas manuais**. Foram usados dados existentes, logs, consultas locais e documentação pública. Não foram alterados NSUs, intervalos, autorizações, certificados, tarefas Windows ou arquitetura do worker; não houve reinício manual do consumidor, migração de banco, publicação ou abertura de portas. O worker existente permaneceu com sua agenda normal.

## Parte A — explicação simples e operacional

### A1. Finalidade e funcionamento

O Vindex Fiscal reúne documentos fiscais de empresas, organiza os XMLs e permite consultar notas, representações em PDF, previsões financeiras e indicadores. Cada cliente tem seu painel; dentro dele pode cadastrar várias empresas por CNPJ. O sistema é próprio, sem integração com a Qive.

A plataforma não emite notas, não movimenta dinheiro e não confirma pagamento bancário. Duplicatas, parcelas previstas, revisão humana e situação fiscal são informações separadas. Um evento recebido não é outra nota nem comprovação de pagamento.

Para uma empresa começar:

1. Criar sua conta/cliente, sujeito à política de aprovação da instalação.
2. Cadastrar razão social e CNPJ corretamente.
3. Vincular o certificado A1 válido e informar a senha **na aplicação**.
4. Autorizar a leitura das fontes desejadas e preencher a configuração exigida, como UF para CT-e.
5. Manter o processo de captura disponível. O navegador pode ser fechado quando o worker independente estiver ativo.

Vincular um A1 não autoriza todos os serviços ou eventos automaticamente. Depois de concluir requisitos e consentimentos, a primeira consulta é agendada e a rotina continua periodicamente, sem mudança de código a cada certificado. O que aparece depende do que a fonte efetivamente disponibiliza ao CNPJ.

O A1 autentica a empresa nos serviços fiscais. Ele e a senha ficam cifrados; não devem ser enviados por chat, incluídos no repositório ou publicados junto ao código. Certificado renovado substitui a credencial, não a identidade do histórico: notas e progresso continuam vinculados ao CNPJ/serviço/ambiente.

### A2. Documentos e consultas disponíveis

| Recurso | Situação e limite |
|---|---|
| NF-e de produtos, modelo 55 | XML completo importado; resumos e eventos preservados separadamente. O transporte real existe. A NF-e do piloto está atualmente sem avanço por rejeição 656. |
| NFS-e nacional/ADN | Consulta real e importação de notas emitidas/tomadas quando disponibilizadas ao CNPJ. Não equivale a integração com todos os municípios/provedores. |
| CT-e, modelo 57 | Distribuição real, XML completo e eventos. Outros modelos de transporte não são automaticamente suportados. |
| XML original | Download privado; preservado mesmo quando o processamento fica pendente. |
| DANFE/DACTE | Representações geradas localmente do XML compatível, sob validações próprias. |
| PDF de NFS-e | PDF de conferência próprio e link de consulta pública oficial. Nenhum adaptador de recuperação automática de DANFSe oficial está habilitado. |
| Parcelas e boletos | Importação/conferência do que existe no documento ou é informado explicitamente. Sem DDA, conexão bancária ou confirmação automática de pagamento. |
| Indicadores | Dados armazenados, filtros e separação por serviço/ambiente; parciais/cancelamentos/substituições não entram como valores elegíveis. |
| API própria | Acesso por credencial e empresas autorizadas. Não concede leitura geral porque o usuário é master. |

Na navegação, use **Notas fiscais** para NF-e, **Documentos consolidados** para a listagem conjunta, **Pendências fiscais** para XMLs com restrição e **Indicadores fiscais** para análises. Filtros e paginação atuam no servidor. Abra o documento para ver detalhes e baixar o XML ou a representação em PDF disponível.

### A3. Gestão master

O master é uma permissão explícita, não uma senha padrão. Em `/gestao/`, vê a carteira de clientes e sua operação. **Ver painel** abre as mesmas telas do cliente em supervisão, com faixa de contexto e endereço próprio. Não muda o usuário autenticado e não transforma o cliente em uma seleção global de sessão. Duas abas podem supervisionar clientes diferentes.

A supervisão é de leitura, auditada. Ações operacionais de aprovação, suspensão ou pausa da captura exigem a permissão adicional correspondente. O administrador não recebe autorização implícita para enviar eventos fiscais.

### A4. Situação real da captura

Retrato local coletado às **09:43:34 de 22/10/2026**, produção, CNPJ **55.737.823/0001-96**. Há dois cadastros autorizados desse mesmo CNPJ: empresa 5/Workspace 1 (Alpha Pet) e empresa 6/Workspace 3 (VINDEX - TESTE 2). São caixas privadas distintas que compartilham a sequência interna de consulta.

| Serviço | Dados em cada um desses acessos | Último resultado persistido | Próxima consulta permitida na agenda local |
|---|---|---|---|
| NF-e | 278 notas | 22/10 às 09:33:01, código 656 | 22/10 às 11:33:01 |
| NFS-e | 183 com schema validado e 13 parciais | 22/10 às 09:33:49, E2220/sem documentos novos | 22/10 às 11:33:49 |
| CT-e | 20.177 com schema validado | 22/10 às 09:35:57, código 138/documento localizado | 22/10 às 11:35:57 |

Não somar essas duas caixas como se fossem empresas/CNPJs independentes. A cópia por cliente preserva o isolamento e não comprova uma segunda homologação de CNPJ diferente.

**NF-e:** cursor processado **123317**, máximo da última resposta aceita **133839**, NSU informado na última rejeição **134134**. A última consulta aceita registrada ocorreu em **21/10 às 19:28:24 no horário oficial**. Não há evidência de normalização posterior da NF-e. A causa específica da divergência ainda não está comprovada; não foi atribuído o problema a outro programa externo sem evidência.

**NFS-e:** cursor **199**, última consulta aceita sem documentos novos. O HTTP 404 combinado com E2220 explícito é o fim de fila previsto nesse contrato, não uma falha genérica de acesso. Há 199 envelopes preservados: 196 notas identificadas e três eventos. A emissão mais recente armazenada é de **21/10 às 16:32:02**. A nova emissão após a autorização de leitura e sua importação automática já foram observadas na etapa anterior. Ausência de novidade agora não comprova cobertura municipal universal ou todo o passado do CNPJ.

**CT-e:** cursor e máximo **81152** na última resposta aceita. A emissão mais recente armazenada é de **22/10 às 01:43:36**. Portanto, o conector avançou além de setembro e alcançou o máximo que a fonte informou nessa consulta. Isso comprova o estado dessa sequência, não todos os documentos fiscais que possam existir fora dela.

O sinal do worker estava recente e a tarefa Windows estava **Running**. Isso comprova atividade do processo, não saúde fiscal dos três serviços. O computador local precisa estar ligado, conectado e com o usuário Windows conectado para a tarefa atual. Um servidor deverá manter o worker independente de login interativo.

### A5. O erro 656 e o que foi corrigido na tela

656 é uma rejeição oficial por uso indevido do serviço **NFeDistribuicaoDFe**, não consequência automática de baixar muitas notas ou de uma chamada demorada. A regra envolve continuidade pelo `ultNSU` e esperas em situações previstas. A mensagem observada foi:

> Rejeicao: Consumo Indevido (Deve ser utilizado o ultNSU nas solicitacoes subsequentes. Tente apos 1 hora)

O aplicativo já usa duas horas de espera. O histórico contém rejeições após essa margem, inclusive 21/10 às 22:29, 22/10 às 00:29 e 09:33. Logo, não é correto prometer que apenas aguardar mais corrige essa ocorrência. Consultas por chave/NSU individual têm limites próprios; não se deve aplicar indistintamente a regra de 20 consultas/hora a toda paginação `distNSU`.

O **656 deve permanecer como última rejeição conhecida, ainda não superada**, até existir evidência posterior de aceitação. Sem nova consulta não é possível afirmar o estado atual do bloqueio remoto. Outro serviço funcionando não o transforma em ocorrência histórica.

O “Ainda não executada” era um erro de apresentação no segundo acesso do mesmo CNPJ: a resposta e o intervalo eram espelhados da fila comum, mas `last_attempt_at` da caixa privada continuava vazio. A tela agora observa o metadado autorizado da fila compartilhada, **sem gravar correções ou mudar a agenda**. Separa:

- Última tentativa de consulta, que pode ser da fila comum do mesmo CNPJ/ambiente.
- Última consulta aceita **registrada neste acesso**. Se esse histórico privado não contém a consulta original, o painel informa a ausência desse registro, sem inventar uma data ou ler o histórico de outro cliente.
- Última NF-e importada neste acesso, distinta da consulta e da emissão.
- Erro atual e aviso histórico quando há consulta aceita posterior que o supera.
- Espera obrigatória e processamento em andamento.

Também aparece o NSU informado na rejeição, sem substituição automática do cursor. Nenhum NSU foi zerado ou saltado. A investigação futura deve confrontar lotes já preservados e regras de recuperação; avançar cegamente poderia esconder um intervalo não entregue ao Vindex.

Fontes: [informe oficial do Portal NF-e](https://www.nfe.fazenda.gov.br/portal/informe.aspx?AspxAutoDetectCookieSupport=1&Informe=0cu%2FyBLKrCs%3D&ehCTG=false) e [NT de distribuição publicada no Portal](https://www.nfe.fazenda.gov.br/Portal/exibirArquivo.aspx?conteudo=U0LlsYVGBRU%3D). O buscador retornou o conteúdo indexado; a abertura direta desses endereços nesta revisão encontrou laço de redirecionamento. Isso não foi contornado com chamadas fiscais.

### A6. NFS-e parcial e DANFSe oficial

As 13 notas incompatíveis recuperadas continuam **parciais**, com originais preservados e excluídas dos valores elegíveis. A análise encontrou ordem de `pAliq`, extensão `xOutInf` e restrições na verificação da assinatura original. Não foi confirmada validade fiscal. Detalhamento por NSU em [NFSE-RECUPERACAO-PRODUCAO.md](NFSE-RECUPERACAO-PRODUCAO.md).

As chaves nacionais armazenadas identificam as notas e permitem construir o link da consulta pública oficial. Isso não garante que um PDF possa ser baixado automaticamente sem autenticação adicional.

Conferência local: as 196 NFS-e desse acesso têm chave de 50 posições; existem **zero PDFs oficiais armazenados**. Não foi exposta nenhuma dessas chaves neste relatório.

A publicação oficial de **03/08/2026** registra a desativação da antiga API ADN de DANFSe v1 e a geração atual pelo portal/consulta pública. A página de APIs ainda lista um endereço de documentação DANFSe; uma única abertura dessa documentação nesta revisão retornou HTTP 502. Não foram testadas operações fiscais nem presumido um novo contrato operacional.

**No cenário atual não há obtenção automática de DANFSe oficial homologada.** Não foi implementado um novo conector nesta revisão, pois isso exigiria comprovar contrato vigente, cobertura e autorização. Mantidos XML, link oficial e PDF próprio identificado como conferência. Fontes: [atualizações oficiais](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/atualizacoes-e-implantacoes) e [diretório oficial de APIs](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/apis-prod-restrita-e-producao).

Para ampliar futuramente: identificar município/provedor e API oficial vigente; confirmar quem pode obter o PDF (A1, conta do portal ou credencial municipal, conforme contrato); obter essas autorizações privadamente; testar uma amostra autorizada; validar associação pela chave e guardar origem. Vale a pena como conveniência documental, mas não deve bloquear captura do XML nem justificar scraping/CAPTCHA, consultas em massa ou nova dependência comercial sem decisão específica.

### A7. O que falta da sua parte

Não precisa reenviar certificado/senha nem repetir comandos por consulta. Antes da publicação, será necessário escolher infraestrutura/domínio, disponibilizar configurações privadas e autorizar a etapa de migração. Também é necessário decidir a cobertura inicial divulgada aos clientes, revisar as pendências fiscais e obter a homologação real da NF-e antes de prometer captura integral dessa fonte.

Para abrir localmente quando a aplicação estiver encerrada:

```powershell
cd C:\Users\user\Downloads\vindex-fiscal
py iniciar.py
```

Para conferir sem disparar consulta fiscal:

```powershell
.\.venv\Scripts\python.exe manage.py verificar_captura
.\.venv\Scripts\python.exe manage.py verificar_producao
Get-ScheduledTask -TaskName 'Vindex Fiscal - Captura'
```

A tarefa já existe; não é necessário recriá-la. Para novo master, use `manage.py criar_admin_master`, interativo, e acesse `/gestao/`. Não há senha padrão. Nesta revisão basta atualizar as páginas; nenhuma dependência ou migração nova foi acrescentada.

## Parte B — documentação técnica e diagnóstico

### B1. Tecnologias e organização

Ambiente inspecionado: **Python 3.15.0, Django 5.2.18**, SQLite local. Receita Docker existente: Python 3.13, Gunicorn, PostgreSQL 17, Redis 7 e Nginx. Essa diferença de ambiente ainda exige homologação da imagem; o funcionamento no Windows não prova o Linux.

Frontend renderizado por templates Django; CSS e JavaScript próprios, sem SPA ou framework novo. Temas claro/escuro mantêm os tokens Vindex, escolha inicial do sistema e persistência local da preferência manual. Os arquivos próprios em `static/portal/` totalizavam aproximadamente **75 KB**; não foi identificado ganho que justificasse reescrever o frontend ou adicionar bibliotecas. Gráficos locais e tabelas acessíveis não enviam dados a serviços de visualização.

Dependências principais: DRF, drf-spectacular/sidecar para API/OpenAPI; cryptography/Fernet e PKCS#12; lxml/defusedxml para XML; SignXML para verificação limitada de assinaturas; pypdf, fpdf2 e BrazilFiscalReport para documentos. `requirements.txt` e `requirements-production.txt` são a fonte das versões; preservar avisos de licença conforme [TERCEIROS.md](TERCEIROS.md).

| Caminho | Responsabilidade |
|---|---|
| `iniciar.py` | Preparação local, testes e supervisão do portal/worker no Windows |
| `config/` | Settings, URL raiz, WSGI/ASGI |
| `portal/models.py` e `*_models.py` | Domínio, isolamento, certificados, captura, API e auditoria |
| `portal/views.py`, `capture_views.py`, `fiscal_views.py` | Portal e observação/configuração dos conectores |
| `portal/master_views.py`, `supervision.py`, `account_middleware.py` | Gestão, contexto de supervisão e estado da conta |
| `portal/api/` | Autenticação, escopos, serializers, recursos e erros da API |
| `portal/services/capture.py`, `sefaz_transport.py` | Fila NF-e, transporte oficial, persistência e entrega privada |
| `portal/services/fiscal_capture.py`, `fiscal_transport.py`, `fiscal_import.py` | Filas e parsers tipados NFS-e/CT-e |
| `portal/services/schemas/` | XSDs públicos locais e manifests; não contêm documentos de cliente |
| `portal/services/nfse_compat.py` | Identificação de formatos e recuperação parcial estritamente delimitada |
| `portal/services/*pdf.py`, `danfe.py`, `dacte.py` | Representações privadas e contrato de PDF oficial |
| `portal/analytics_views.py`, `pagination.py` | Indicadores e paginação |
| `portal/management/commands/` | Captura contínua, diagnósticos, master e migração protegida |
| `templates/`, `static/` | Interface e identidade visual |
| `portal/test*.py`, `tools/ui-checks/` | Testes Django e verificações locais de interface |
| `deploy/` | Receita de servidor, exemplo de ambiente e Nginx |
| `docs/` | Operação, integração, API e implantação |
| `tmp/` | Sinal do worker, locks e diagnósticos locais ignorados no repositório |

Não copiar `.env`, SQLite, A1, XML/PDF reais, backups ou `.venv` para Git, ZIP ou imagem. `.gitignore` e `.dockerignore` ajudam, mas não substituem conferir o material que será transferido.

### B2. Modelos e isolamento

| Modelo/grupo | Papel e regra importante |
|---|---|
| `Workspace` | Dono, aprovação/suspensão e pausa operacional; permissões `admin_master` e `operate_clients` |
| `Company` | Empresa de um Workspace, unicidade `(workspace, cnpj)` |
| `DigitalCertificate` | A1 renovável por empresa; arquivo/senha cifrados e metadados de vigência |
| `Invoice`, `Installment`, `InstallmentRevision` | NF-e 55, previsões de parcelas e conferência auditada; chave única por empresa |
| `Boleto`, `BoletoEvent` | Evidência/documento de cobrança privado, sem integração bancária |
| `SefazCaptureConfig` | Autorização de leitura e configuração por empresa |
| `SefazDistributionStream` | Cursor, máximo, retorno, lease e espera únicos por CNPJ/ambiente/origem |
| `SefazConsultation`, `SefazStreamDocument` | Respostas duráveis e envelopes de distribuição |
| `SefazSyncState`, `SefazDocument` | Estado e entrega privada por empresa/acesso, com tratamento separado de resumo/evento/XML |
| `SefazScienceRequest` | Consentimento e resultado específico de Ciência da Emissão |
| `FiscalConnector`, `FiscalStream` | Configuração privada e coordenação por CNPJ/serviço/ambiente de NFS-e/CT-e |
| `FiscalConsultation`, `FiscalEnvelope`, `FiscalDelivery` | Respostas, original/hash e resultado da interpretação por cliente |
| `FiscalDocument` | Documento tipado, chave única por empresa/serviço/ambiente, parcialidade e PDF oficial opcional |
| `ApiCredential`, `CredentialCompany` | Hash da credencial, validade, escopos e empresas explícitas |
| `AuditEntry`, `MasterAudit` | Operação do cliente e supervisão/ações administrativas |

Todas as páginas e ações privadas partem do Workspace autenticado ou do contexto explícito de supervisão autorizado. A mesma raiz de certificado não concede acesso a outro Workspace. A fila fiscal coordena a identidade legal compartilhada, mas a entrega a cada caixa exige seu próprio consentimento e prova do A1. Metadados mínimos da fila, como tentativa/lease, não expõem XML ou histórico privado de outro cliente.

A API restringe simultaneamente o Workspace e as empresas da credencial. Seleção vazia não equivale a acesso geral. Tokens são opacos, têm prefixo público e hash do segredo; nunca derivados da chave de cifra. Há expiração, revogação, HTTPS em produção e limites por credencial/endereço. A supervisão master não amplia os escopos da API.

**Correção de segurança desta revisão:** credencial já emitida agora é recusada se o Workspace estiver `pending` ou `suspended`, assim como já era para usuário inativo. A situação do portal não podia ser contornada via API. A credencial não é apagada; ao reativar o cliente, continua sujeita a validade/revogação/escopos. Testes cobrem leitura, escrita e ausência de atualização de uso durante o bloqueio.

### B3. Certificados, transporte e parsers

Fernet protege arquivo PKCS#12 e senha com `CERTIFICATE_ENCRYPTION_KEY`. A chave original é imprescindível para restaurar o histórico utilizável. O banco cifrado e a chave juntos permitem acesso: devem ter controles e backups separados. Não há KMS/HSM implementado nem chave individual por cliente.

O uso revalida vigência e compatibilidade da raiz CNPJ. O contexto TLS usa certificado cliente, valida servidor/hostname e remove material temporário privado; a chave PEM temporária exigida pelo SSL fica protegida por senha efêmera e permissões locais. Nunca desativar TLS para contornar falha de certificado. `SEFAZ_EXTRA_CA_FILE` aceita autoridades adicionais verificadas, não “ignorar validação”.

- **NF-e:** SOAP 1.2 `nfeDistDFeInteresse`, `distDFeInt` 1.01, endpoint oficial de produção `www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx`. Ambiente de homologação em `hom1`. Distribuição por último NSU, sem evento fiscal automático.
- **CT-e:** SOAP 1.2 no serviço nacional de distribuição, schema tipado de CT-e 57/processado e eventos suportados. Não usar parser NF-e para CT-e.
- **NFS-e:** REST mTLS ADN Contribuintes, distribuição por NSU no contrato preservado `adn-contribuintes-openapi.json`. XML nacional 1.00/1.01 e eventos reconhecidos. Padrões ABRASF/desconhecidos são identificados/preservados como pendência, sem inventar integração municipal.

XML passa por limites de tamanho/descompressão e bloqueio de DTD/entidades/rede. XSDs ficam locais. O perfil de compatibilidade NFS-e valida uma cópia em memória para recuperação parcial; não modifica XML/XSD original. “Schema validado” não certifica cadeia ICP-Brasil, revogação, situação fiscal ou pagamento. SignXML no caminho parcial verifica a assinatura original com a chave embutida sob limites documentados, sem declarar homologação fiscal.

### B4. Worker, persistência e concorrência

`manage.py capturar_sefaz` executa a fila contínua das empresas habilitadas e autorizadas; `--once` executa uma volta. Esses comandos **não foram usados para investigar o 656 nesta revisão**. O polling local padrão é de 15 segundos e só lê a elegibilidade; não significa uma chamada fiscal a cada 15 segundos.

A política atual permanece: duas horas após fim da fila/bloqueio, mínimo configurável efetivo de 61 minutos, intervalo curto entre lotes de histórico permitido. Retentativa local de XML é outra agenda. Não há Redis/Celery como fila de captura: a fila e sua elegibilidade são persistidas no banco. Redis em produção é para cache compartilhado/limites.

Leases por identidade fiscal, reserva condicional de trabalho e transações protegem a coordenação. Um lock de sistema operacional impede dois consumidores contínuos nesta instalação/volume; não substitui as reservas no banco. Em hosts distintos, só uma base coordenadora e leases compartilhados podem regular o CNPJ. Não operar instalação antiga e nova como consumidores independentes durante migração.

Respostas e envelopes são preservados para recuperar processamento local sem repetir HTTP desnecessário. Hashes, NSU e chaves únicas evitam duplicidades. Um resultado de execução interrompida pode impor espera conservadora, não reinício do progresso. Renovação de A1 e reinício retomam a identidade persistida.

O worker trata falhas operacionais de banco aguardando nova volta da fila; não transforma erro em sucesso. No Windows, `tools/capture_background.py` é iniciado pela tarefa de logon `Vindex Fiscal - Captura`; `iniciar.py` reaproveita sinal existente e mantém fallback local. As reservas e heartbeat ficam em `tmp/`. Na receita Linux, um serviço `capture` separado usa o mesmo banco/chave/volume de runtime. Não há alterações de arquitetura nesta rodada.

### B5. XML, PDF, logs e auditoria

Os XMLs, respostas e envelopes são campos privados no banco. PDFs de boleto e eventual PDF oficial recuperado também podem estar no banco. DANFE/DACTE/PDF de conferência são gerados sob demanda em memória, com verificação de escopo; não são um diretório público de arquivos.

O contrato de adaptadores de DANFSe tem registro vazio. Quando houver um adaptador homologado, o código existente prevê consentimento, validação do PDF/chave/tamanho/páginas, origem, horário e armazenamento privado. Essa preparação não é prova de integração executada. Nenhum PDF oficial foi obtido nesta revisão.

Históricos de consulta guardam códigos, motivos, horários e evidências privadas; auditorias registram supervisão e operações. Logs de processo não devem imprimir PKCS#12, senhas, chave de cifra ou XML. Filtro de exceção remove variáveis sensíveis dos serviços. Não ativar SQL com parâmetros ou dumps de corpos HTTP em produção. Logs precisam retenção e controle de acesso; heartbeat recente não substitui alerta de erro fiscal persistente.

### B6. Otimizações realizadas e medição

Sem migração, índice novo, cache de documentos, mudança de framework ou mudança no worker:

1. Listagem da captura não carrega XML dos envelopes nem o XML da nota vinculada. Histórico de 20 consultas não carrega `response_xml` SOAP oculto. Campos cifrados do A1 também ficam fora dessa leitura de metadados.
2. Tabela de documentos nos conectores não busca XML do envelope para exibir apenas tipo/NSU/erro/link.
3. Visão geral calcula os totais e faixas de vencimento em agregações conjuntas e não carrega XML/cifra para cartões. Mantidos os mesmos limites de datas, valores decimais, filtros e isolamento.
4. Notas reutilizam o total já calculado pelo paginador, removendo um `COUNT` repetido. A validação de disponibilidade do DANFE continua sendo feita onde o botão depende do XML.
5. Documentos consolidados usam `UNION ALL`: as duas origens são disjuntas por tipo/ID; o `DISTINCT` global repetia trabalho em todo o histórico antes da paginação. Não altera chaves, número de registros ou deduplicação da captura.

Medição sobre a base real, usuário master e contextos supervisionados. **Renderização da view com RequestFactory**, três execuções por rota, primeira descartada e mediana das duas restantes. Não inclui rede, middleware, login, auditoria de supervisão ou pintura no navegador. Portanto não é benchmark de infraestrutura nem prova de latência HTTP total. Cache de processo/SO e carga concorrente podem influenciar.

| View/contexto | Antes (ms) | Depois (ms) | Consultas antes → depois | SELECTs com XML/SOAP/cifra antes → depois |
|---|---:|---:|---|---|
| Visão geral, Workspace 3 | 41,05 | 33,05 | 17 → 9 | 2 → 0 |
| Captura NF-e, empresa 6 | 758,35 | 409,60 | 10 → 12 | 3 → 0 |
| Captura NF-e, empresa 5 | 1.339,45 | 445,30 | 10 → 12 | 3 → 0 |
| Documentos consolidados, Workspace 3 | 1.482,55 | 743,80 | 3 → 3 | 0 → 0 |
| Notas, Workspace 3 | 85,30 | 53,50 | 5 → 4 | 1 → 1 |

A captura ganhou consultas pequenas para separar corretamente as datas/ocorrências, mas eliminou payloads grandes e mostrou menor tempo nessa amostra. Não se declara redução do número de consultas em todas as telas.

**Contenção real observada:** uma tentativa inicial de medição autenticada falhou ao gravar sessão com `sqlite3.OperationalError: database is locked`. Não foi presumida causa única nem declarado que as otimizações eliminam esse risco. A repetição posterior das verificações HTTP autenticadas funcionou. SQLite com portal/worker concorrentes é um impedimento para homologar a publicação com essa carga; migrar para PostgreSQL e medir no servidor é obrigatório na receita proposta. Não foi alterado PRAGMA, journal, timeout ou modo transacional, nem reiniciado worker para produzir números melhores.

Melhorias maiores ficam para homologação: planos de consulta e índices sobre PostgreSQL, paginação de listas muito extensas, custo de indicadores em períodos grandes, retenção e crescimento dos envelopes. Materializar indicadores, mover XML para armazenamento de objetos ou trocar a arquitetura da fila não foi feito.

### B7. Configuração sem segredos

| Variável/grupo | Finalidade |
|---|---|
| `DJANGO_SECRET_KEY` | Segredo forte da aplicação; privado; não fornecer por chat |
| `DJANGO_DEBUG` | `0` em produção; debug atual é local |
| `DJANGO_ALLOWED_HOSTS` | Domínios explícitos, sem curinga/exemplo |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Origens HTTPS autorizadas |
| `VINDEX_TRUST_PROXY` | Somente com proxy confiável que substitui cabeçalhos de origem |
| `CERTIFICATE_ENCRYPTION_KEY` | Chave original dos certificados e backups protegidos; preservar |
| `VINDEX_DB_ENGINE`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `PGHOST`, `PGPORT`, `PGSSLMODE` | PostgreSQL; transporte protegido quando externo à rede privada |
| `POSTGRES_PASSWORD` | Inicialização do serviço da receita Compose; coerente com PGPASSWORD |
| `VINDEX_REDIS_URL` | Cache compartilhado para limites em múltiplos processos |
| `VINDEX_REGISTRATION_MODE` | `approval` ou `closed` antes de abertura pública |
| `DJANGO_EMAIL_HOST/PORT/USER/PASSWORD/TLS`, `DJANGO_DEFAULT_FROM_EMAIL` | SMTP e recuperação de senha; testar entrega real |
| `SEFAZ_EXTRA_CA_FILE` | CA adicional verificada, quando necessária; sem ignorar TLS |
| `FISCAL_IDLE_INTERVAL_MINUTES` | Política existente, padrão 120; não alterada nesta revisão |

O ambiente de produção está exemplificado sem valores privados em `deploy/.env.production.example`. As variáveis locais não foram copiadas para este documento. Configuração presente não comprova conectividade/entrega/segurança da infraestrutura.

### B8. Testes e limites da verificação

Os testes usam banco descartável, certificados e respostas sintéticos, sem chamadas fiscais reais. A suite cobre autenticação/API, escopo/mesmo CNPJ em clientes distintos, supervisão, certificados, importação, duplicidade, schemas/TLS, manifestação com autorização, eventos, recuperação parcial, PDF, indicadores, backup/restore e retomada do worker.

**Resultado final: 345 testes Django aprovados**, em 240,2 segundos, com `py iniciar.py --testar`; **32 verificações de DOM/CSS/tema aprovadas**. Nenhuma falha pendente na suite. A primeira medição HTTP encontrou o bloqueio SQLite relatado em B6; isso é uma falha operacional observada, não uma falha da suite e não foi omitida da avaliação de prontidão.

Testes novos desta rodada: tentativa compartilhada sem alterar cursor/espera; não leitura do histórico de outro cliente; rejeição histórica somente após aceitação posterior; listagem sem payload e XML original ainda baixável; totais financeiros em limites de datas/parcelas sem vencimento/outro Workspace; API bloqueada para conta pendente/suspensa.

Verificações reais realizadas com a base local, sem transporte fiscal: páginas autenticadas de visão geral, captura, documentos, notas e pendências responderam HTTP 200; downloads de XML NF-e/NFS-e/CT-e conferiram com o original em memória; tentativa de baixar documento de outro Workspace pela supervisão escolhida retornou 404. Esses acessos produzem as auditorias/sessões normais, sem alterar notas ou configurações fiscais.

`manage.py check` sem problemas; `makemigrations --check --dry-run` sem mudanças pendentes. O preflight de produção encontrou apenas heartbeat pronto e as configurações de infraestrutura pendentes. `check --deploy` no ambiente local gerou **cinco avisos esperados**, incluindo DEBUG, HTTPS/HSTS e cookies seguros; não foram silenciados ou “corrigidos” habilitando produção no computador local.

Não foi feita nova inspeção visual em navegador nesta rodada. Templates/rotas foram renderizados e a identidade/tokens preservados; isso não certifica pintura, zoom ou todos os tamanhos de tela. A verificação manual nos dois temas, celular/tablet/desktop faz parte da homologação. Não houve ensaio de Docker/Linux, PostgreSQL, Redis, SMTP, DNS/TLS público, concorrência/load no servidor ou restauração do banco real de aproximadamente **1.045,6 MB**. Não houve nova prova externa de captura, por restrição expressa do pedido.

## Parte C — migração e publicação, sem executar agora

### C1. Grau de preparação e prioridades

**Preparado para iniciar homologação restrita de infraestrutura; não pronto para abertura pública.** O código e o roteiro existem, mas testes locais não homologam disponibilidade, recuperação ou serviços fiscais externos. Não atribuir porcentagem de prontidão sem esses ensaios.

Impedimentos obrigatórios antes da publicação da oferta atual:

1. Resolver/homologar a NF-e 656 ou restringir explicitamente a oferta do piloto; não anunciar captura NF-e normalizada enquanto o último resultado continuar rejeitado. Esta revisão não autoriza novas consultas de investigação.
2. Configurar servidor, domínio, HTTPS, proxy confiável, DEBUG desativado, hosts/CSRF/cookies seguros e política de cadastro.
3. Migrar para PostgreSQL e configurar Redis compartilhado; testar concorrência, carga e isolamento com o volume real. Não publicar esse SQLite como se a contenção observada estivesse resolvida.
4. Preservar chave dos A1 e fazer backup/restauração real em destino novo, com comparação de identidades/vínculos, cursores, microssegundos de esperas e abertura dos certificados.
5. Configurar SMTP e provar recuperação de senha por e-mail. Revisar contas e permissões master, segredos e acessos operacionais.
6. Ter worker como serviço supervisionado, alertas de parada/falha fiscal recorrente/certificado/backup e ensaio de reinício do host.
7. Homologar imagem Linux/Python de produção, dependências, arquivos estáticos, permissões/volumes e navegação real nos temas/tamanhos alvo.
8. Definir política de acesso/retensão/recuperação e responsáveis de suporte. Revisar os 13 documentos parciais e comunicar a limitação de cobertura; não tratá-los como validação fiscal plena.

Melhorias opcionais, separadas dos impedimentos:

- Recuperação automática de DANFSe por adaptador oficial homologado, sem bloquear o XML.
- MFA para master, KMS/rotação de chaves, trilha/alertas mais avançados e monitoramento centralizado.
- Mais padrões/municípios, outros modelos fiscais e tratamento do CNPJ alfanumérico, que não está suportado pelo cadastro/validações atuais. Não anunciar suporte a essas empresas antes da adaptação/homologação; o diretório oficial já menciona evolução alfanumérica.
- Índices e otimizações medidos em PostgreSQL, agregações persistidas e armazenamento externo privado, se a carga exigir.
- DDA/bancos continuam etapa posterior e fora da oferta atual.

### C2. Infraestrutura e dimensionamento inicial

Receita recomendada existente: Linux suportado pelo provedor, Docker Engine/Compose, PostgreSQL e Redis em rede privada, Gunicorn e Nginx atrás de terminador HTTPS confiável. Windows Server pode executar Django/worker como serviços, mas **não é a receita preparada/homologada**; exigiria supervisor, proxy, permissões e ensaio próprios. Não usar Agendador dependente de usuário logado como solução de disponibilidade de servidor.

Como **hipótese inicial para homologação de poucos clientes**, considerar 2–4 vCPU, 4–8 GB RAM e SSD de 80 GB ou mais, com expansão e monitoramento. Não é capacidade garantida nem benchmark de usuários simultâneos. O banco local já ultrapassou 1 GB, com cópias privadas e respostas/envelopes; reservar espaço para crescimento, logs, arquivos temporários de restore e múltiplas gerações de backup. Medir o cenário real antes de definir o plano final. Para carga maior, separar banco/worker/web após medir, mantendo uma coordenação por CNPJ.

A aplicação precisa de saída HTTPS aos serviços oficiais, DNS e relógio sincronizado. A entrada pública deve ser somente pelo domínio/proxy HTTPS. Banco, Redis, A1, runtime e arquivos de configuração não ficam expostos. HSTS/subdomínios devem ser revisados antes de ativação no domínio real.

### C3. Roteiro da próxima etapa

Não executar estes comandos como parte desta revisão. O procedimento detalhado e os cuidados estão em [IMPLANTACAO.md](IMPLANTACAO.md).

1. Criar homologação privada; copiar somente código, conferir `.dockerignore` e preencher `deploy/.env.production` privadamente. Configurar segredos/domínio/SMTP. Preservar a chave de cifra original; não recriar A1 ou NSU.
2. Construir a imagem e preparar destino vazio, ainda sem captura:

```sh
docker compose -f deploy/compose.yaml build
docker compose -f deploy/compose.yaml up -d db redis
docker compose -f deploy/compose.yaml run --rm web python manage.py migrate
docker compose -f deploy/compose.yaml run --rm web python manage.py check --deploy
docker compose -f deploy/compose.yaml run --rm web python manage.py collectstatic --noinput
```

3. Planejar manutenção real, concluir chamadas em andamento e parar consumidores/escritas antigas. Gerar manifesto/backup cifrado **fora do projeto**, sem sobrescrever outro backup:

```powershell
.\.venv\Scripts\python.exe manage.py conferir_dados > C:\VindexBackups\antes.json
.\.venv\Scripts\python.exe manage.py migrar_dados_protegidos --exportar --arquivo C:\VindexBackups\migracao.vfx
```

Criar antes uma pasta privada adequada. Esses comandos podem manter transação durante a leitura e devem ser executados na janela de manutenção, não para investigar a captura com o worker concorrente. Transferir backup cifrado por canal privado e chave por canal separado.

4. Restaurar somente em banco novo preparado; comparar manifesto e abrir amostras privadas:

```sh
docker compose -f deploy/compose.yaml run --rm -v /caminho/privado:/backup:ro web python manage.py migrar_dados_protegidos --importar --arquivo /backup/migracao.vfx --confirmar-banco-vazio
docker compose -f deploy/compose.yaml run --rm web python manage.py conferir_dados
```

VFX2 exporta JSONL cifrado/autenticado por blocos, com ordem/término/integridade verificados antes da carga e preservação de datas com microssegundos. Não tem o antigo limite global de 512 MB, mas o volume real ainda precisa de ensaio de espaço/tempo. A chave original deve abrir os A1; sessões antigas não são migradas. Testes descartáveis não substituem esse restore real.

5. Só depois de validar o destino, desativar a instalação antiga como consumidora e iniciar os serviços novos:

```sh
docker compose -f deploy/compose.yaml up -d web capture proxy
docker compose -f deploy/compose.yaml exec web python manage.py verificar_captura
docker compose -f deploy/compose.yaml exec web python manage.py verificar_producao --estrito
```

O Nginx da receita só publica `127.0.0.1:8080` no host. O domínio/TLS externo deve encaminhar a esse endereço por proxy confiável, substituindo cabeçalhos de origem. Não abrir PostgreSQL/Redis na internet. Não apontar duas instalações ao mesmo CNPJ com bases/cursors independentes. Rollback precisa considerar o último progresso **do destino**, não reativar uma cópia antiga desatualizada.

6. Homologar autenticação, aprovação/suspensão/API, duas abas de master, URLs/downloads cruzados, filtros/paginação, SMTP, celulares/temas, pressão de escrita, indisponibilidade e retomada. Homologar reinício de web/worker/host sem redução de esperas. Só realizar novas consultas fiscais de teste sob autorização específica e respeitando os intervalos persistidos.
7. Criar backups automáticos consistentes do PostgreSQL, cifrados fora do código, com retenção e cópia externa privada. Guardar chaves separadas, provar restauração regularmente e definir RPO/RTO com o negócio. Definir responsável por alertas e incidentes.
8. Liberar poucos clientes autorizados, observar operação e expandir depois da evidência. Um healthcheck `/saude/` só verifica banco; `verificar_captura` só comprova sinal recente. Container `unhealthy` não é reiniciado automaticamente apenas por ter healthcheck: monitoramento e ação operacional continuam necessários.

### C4. Atualização, manutenção e continuidade

Manter versões/release identificáveis e cópia de rollback do código. Antes de cada migração: backup testado, plano de compatibilidade e janela conforme impacto. Separar deploy web do consumo fiscal sem duplicar consumidores. Nunca apagar documentos/certificados/cursor para “limpar erro”. Preservar respostas duráveis e explicar pendências ao usuário.

Não guardar dados reais como fixtures de teste. Para regressões, gerar exemplos sintéticos sem chaves ou informações de cliente. Mudanças em autenticação, escopo, importação ou certificados exigem os testes pertinentes. Use `py iniciar.py --testar` no Windows; em ambiente preparado, `python manage.py test` executa a suite Django. Há verificações adicionais de DOM/tema em `tools/ui-checks/`; elas não substituem conferência visual e testes de acessibilidade no navegador.

Fontes de implantação: [checklist Django 5.2](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/) e a receita do próprio projeto em `deploy/`. Nenhuma infraestrutura externa foi contratada, configurada ou publicada nesta etapa.
