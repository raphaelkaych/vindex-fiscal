# Recuperação de NFS-e e preparação para produção

Entrega de 21/10/2026. Horários abaixo em Brasília (UTC−3). Este relatório substitui os retratos anteriores como referência do estado atual; as contagens continuam mudando com a captura. Não contém XMLs, chaves de documentos, certificados ou senhas.

## Resultado executivo

Foi implementada e executada a recuperação controlada das 13 NFS-e preservadas: **13 identificadas e disponíveis como importação parcial, zero promovidas a validação completa, 13 ainda pendentes de conferência**. Os XMLs originais foram preservados e seus hashes conferidos antes/depois. Esses documentos não entram nos valores elegíveis dos indicadores.

A captura automática está ativa. Há uma prova real de nova emissão: a NFS-e de NSU 199 foi emitida em **21/10 às 16:32:02** e importada automaticamente às **20:28:26**, depois da autorização de leitura das 15:33:52. Isso comprova o fluxo para a Alpha Pet no ADN nacional; não é teste de nova emissão de todas as empresas ou de todos os municípios.

**Não recomendo abrir a plataforma publicamente ainda.** O código está preparado para uma homologação em servidor, mas a infraestrutura de produção não foi configurada nem testada. A NF-e também voltou a receber rejeição 656; o intervalo está preservado e sua normalização ainda não foi observada. Não há integração municipal de PDF oficial habilitada.

## Captura real da Alpha Pet

Retrato em **21/10/2026 às 21:01:37**, produção, CNPJ 55.737.823/0001-96:

| Fonte | Documentos no painel | Cursor e resultado | Situação |
|---|---|---|---|
| NF-e | 278 notas reais | NSU 123317 / máximo 133839; código 656 | Histórico incompleto; aguardando 21:29:38 |
| NFS-e nacional | 183 aprovadas no schema + 13 parciais | NSU 199; E2220 `NENHUM_DOCUMENTO_LOCALIZADO` | Aguardando 21:29:54; nova emissão efetivamente importada |
| CT-e | 12.692 aprovados no schema | NSU 72081 / máximo 80993; código 138 `documento localizado.` | Captura avançando; histórico ainda incompleto |

As datas de emissão mais recentes nesse retrato eram **01/10/2026 para NF-e**, **21/10/2026 para NFS-e** e **17/09/2026 às 16:42:34 para CT-e**. Portanto, não está tudo limitado a julho, mas NF-e e CT-e ainda não alcançaram o máximo disponível. Não se deve saltar NSUs para chegar às notas recentes.

A resposta oficial NF-e mais recente ocorreu às **20:28:34**, código **656**, motivo exato:

> Rejeicao: Consumo Indevido (Deve ser utilizado o ultNSU nas solicitacoes subsequentes. Tente apos 1 hora)

A consulta enviou o NSU 123317, também retornado pela última consulta aceita. A causa específica da rejeição **não foi comprovada**. Foram encontrados dois grupos de processos contínuos e sua inicialização foi consolidada, mas isso não demonstra a causa do 656. O código atual já recarrega o cursor na reserva do trabalho; não foi atribuída uma correção inexistente a esse trecho. Nenhuma consulta foi forçada durante o bloqueio e nenhum cursor foi zerado.

No ADN, a última conclusão sem documentos novos foi às **20:28:54**: HTTP 404 com código explícito E2220, uma resposta de ausência de novos documentos nessa operação, não uma falha genérica. Existem **199 envelopes preservados: 196 NFS-e e 3 eventos**, sequência local 1–199 sem lacunas, com registro de início em zero. A primeira NFS-e disponível armazenada é de 14/03/2025. Isso comprova o processamento da sequência retornada; **não comprova que todo o histórico fiscal ou todos os provedores municipais estejam cobertos**.

## Investigação individual das 13 NFS-e

Todas são do padrão nacional, namespace `http://www.sped.fazenda.gov.br/nfse`, versão **1.00**, ambiente **produção**. A incompatibilidade principal é a ordem de `pAliq` em relação a `tribISSQN` e `tpRetISSQN`. Duas também têm `infNFSe/xOutInf` não aceito pelo layout histórico disponível. A primeira mensagem de XSD apontava 11 casos de `pAliq` e dois de `xOutInf`; a investigação completa identificou também a ordem tributária nesses últimos dois.

| Entrega local | NSU | Município IBGE | Incompatibilidade | Resultado da assinatura do XML original |
|---:|---:|---:|---|---|
| 1 | 1 | 3509502 | Ordem de pAliq | Certificado da assinatura fora da validade na data de processamento declarada |
| 4 | 4 | 3516408 | Ordem de pAliq | Verificação criptográfica falhou |
| 14 | 14 | 3509502 | Ordem de pAliq | Verificação criptográfica falhou |
| 25 | 25 | 3516408 | Ordem de pAliq | Verificação criptográfica falhou |
| 34 | 34 | 3509502 | Ordem de pAliq | Verificação criptográfica falhou |
| 43 | 43 | 3516408 | Ordem de pAliq | Verificação criptográfica falhou |
| 101 | 51 | 3509502 | Ordem de pAliq | Verificação criptográfica falhou |
| 137 | 87 | 3516408 | Ordem de pAliq | Verificação criptográfica falhou |
| 205 | 105 | 3509502 | Ordem de pAliq | Verificação criptográfica falhou |
| 220 | 120 | 3516408 | Ordem de pAliq | Verificação criptográfica falhou |
| 304 | 154 | 5300108 | Ordem de pAliq e xOutInf | Verificação criptográfica falhou |
| 305 | 155 | 5300108 | Ordem de pAliq e xOutInf | Verificação criptográfica falhou |
| 311 | 161 | 3516408 | Ordem de pAliq | Verificação criptográfica falhou |

Esses resultados dizem respeito ao certificado embutido na assinatura do documento recebido, **não ao A1 da Alpha Pet**, que continua utilizável para consulta. Não foi possível afirmar a validade fiscal dessas 13 notas. Falha de verificação local tampouco é declaração oficial de inexistência ou fraude: seria necessário confrontar os originais com o emissor/consulta oficial e sua situação fiscal.

O tratamento parcial só aceita envelopes já preservados de respostas reais aceitas do conector, com hash, CNPJ e ambiente correspondentes. Uma **cópia em memória** reorganiza somente os filhos previstos e valida todo o restante no XSD oficial. `xOutInf`, quando presente na posição admitida, é validado separadamente no tipo oficial antes de ser desconsiderado nessa cópia. O arquivo original, sua assinatura e os XSDs em disco não são alterados. Mesmo que uma assinatura passe no futuro, essa recuperação continua marcada como parcial enquanto o original não atender ao schema.

SignXML verifica a assinatura original e a referência exata ao identificador da nota, quando possível. Isso não homologa cadeia ICP-Brasil, revogação ou situação fiscal atual. **“Schema validado” também não significa assinatura, pagamento ou situação fiscal certificada.**

## Tratamento de documentos e cobertura

- Identificação de padrão, namespace, versão, município e ambiente. Nacional 1.00/1.01 possui processamento; ABRASF e padrões desconhecidos são identificados/preservados como pendência. Isso não implementa novas APIs municipais.
- Pendências têm causa, NSU, revisão do processador e data; documentos desconhecidos não são mais contabilizados como sucesso sem nota.
- Uma revisão nova do processador permite nova tentativa local, inclusive se a consulta remota estiver em espera. As pendências persistentes usam espera de 24 horas para reprocessamento local. Isso não contorna limites fiscais nem reinicia cursores.
- XML sem PDF pode ser importado normalmente. Notas nacionais emitidas ou tomadas são reconhecidas quando disponibilizadas ao CNPJ pelo ADN.
- Cancelamento e cancelamento por substituição são tratados quando os eventos correspondentes forem recebidos. A chave substituta é preservada. Nenhum evento fiscal foi enviado nesta execução.
- A tela de conectores distingue ausência de novos documentos, ausência de documentos disponíveis na fonte e cobertura ainda não verificável. Não interpreta períodos vazios como prova de inexistência de notas.

Nova área **Documentos pendentes** em `/documentos/pendentes/`, também na supervisão master. Cada XML continua privado no escopo correto, com acesso ao original e aviso nos documentos parciais.

## DANFSe e PDFs

Foi revisada a documentação oficial: a desativação da antiga API ADN de DANFSe ocorreu em **03/08/2026**, segundo as atualizações oficiais. A data inicialmente prevista e citada em relatórios anteriores não deve ser tomada como o estado atual. O contrato público ADN consultado distribui documentos e eventos e não oferece uma operação atual de PDF nesse contrato.

Fontes: [atualizações e implantações oficiais](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/atualizacoes-e-implantacoes), [prorrogação da adequação ao DANFSe](https://www.gov.br/nfse/pt-br/noticias/se-cgnfs-e-prorroga-o-prazo-para-adequacao-ao-novo-leiaute-do-danfse) e [documentação técnica atual](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual).

Foi implementado um contrato interno de adaptadores por município/ambiente para recuperar, validar e associar um PDF oficial à chave da nota, com tamanho/páginas limitados e armazenamento privado. **O registro de adaptadores está vazio: nenhum endpoint foi inventado e nenhum PDF oficial foi recuperado em produção nesta entrega.** Os testes desse caminho usam respostas sintéticas. A ausência ou falha de PDF não impede a importação do XML.

Na NFS-e há um link para a consulta pública oficial pela chave, onde o usuário pode obter o documento quando disponibilizado. É uma navegação manual ao portal oficial, não captura automática nem contorno de autenticação/CAPTCHA. Para habilitar recuperação automática municipal, precisamos de documentação de API vigente do provedor, autorização de uso, cobertura do município e eventuais credenciais obtidas privadamente. Um novo município exige adaptador e homologação; cadastrar apenas o A1 não cria essa integração.

O Vindex continua oferecendo **PDF de conferência**, claramente identificado como representação própria e não DANFSe oficial. Nas 13 parciais, o PDF inclui aviso de revisão; os 13 foram gerados e conferidos em memória, sem modificar os XMLs. Se um PDF oficial for futuramente recuperado pelo adaptador homologado, o download usa esse arquivo com origem registrada. DANFE de NF-e e DACTE de CT-e continuam disponíveis pelos recursos existentes.

## Navegação e indicadores

Paginação compartilhada nas listagens de notas, documentos, agenda, boletos, captura e gestão: primeira/última, anterior/próxima, números próximos, página atual, total e seleção de quantidade. Filtros são preservados; listagens duplas do master têm parâmetros independentes. Limites impedem pedir uma quantidade arbitrária de registros.

Nova área **Indicadores**, `/indicadores/`, acessível ao cliente e ao master no painel supervisionado. Usa somente dados reais armazenados, com filtros de empresa, período de emissão, tipo e ambiente, gráficos mensais de volume/valores, distribuição por tipo e tabelas acessíveis. Os gráficos oferecem valores por foco/tooltip e filtros, sem transmitir dados a serviços externos.

Chaves repetidas são deduplicadas por serviço e ambiente. Valores de NF-e, NFS-e e CT-e não são somados como uma única grandeza. Documentos parciais, cancelados ou substituídos são excluídos dos valores elegíveis; conflitos também são sinalizados. Não se infere pagamento pela presença de parcela, nem atividade fiscal pela ausência de evento. CT-e informa participação, sem inventar a condição de emitente/tomador. Pendências por data de recebimento são rotuladas separadamente das notas por data de emissão. A contagem de PDF oficial considera arquivos realmente armazenados; PDFs locais geráveis não aparecem como oficiais recuperados.

## Captura diária e reinício

O fluxo é genérico por empresa/cliente. A1 válido e compatível + configuração disponível + autorização de leitura/captura na aplicação permitem agendar e processar a fila automaticamente. Vincular certificado sem concluir esses requisitos não autoriza consultas ou manifestações silenciosamente. Ciência da Emissão continua dependendo de consentimento específico por documento, e não confirma a operação comercial.

A identidade do histórico é CNPJ/serviço/ambiente, não o certificado. Renovação e reinício preservam o cursor, esperas e documentos. O acesso e a entrega continuam limitados ao Workspace autorizado; master supervisiona em leitura, com identidade e auditoria próprias.

Foi adicionado bloqueio de instância contínua no sistema operacional. A tarefa em segundo plano pode aguardar e assumir após liberação; o iniciador não fica relançando filhos quando outro processo já está ativo. As reservas por CNPJ/ambiente permanecem. Dois executáveis Python encadeados pelo ambiente virtual podem pertencer ao mesmo grupo lógico; não são automaticamente dois consumidores.

A tarefa Windows **Vindex Fiscal - Captura** foi reiniciada e estava ativa, com um único grupo de worker observado. O computador precisa ficar ligado, conectado e com o usuário Windows conectado. Desligado ou sem internet, não há consulta; o trabalho volta a partir do estado salvo quando o processo retorna. Em servidor, o worker deve ser um serviço supervisionado independente do navegador e da sessão do usuário.

## Segurança e preparação operacional acrescentadas

- `verificar_producao` verifica configurações sem consultar o fisco ou imprimir segredos. Na instalação local, apenas o sinal recente do worker passou; os itens de infraestrutura seguem pendentes.
- Filtragem de variáveis locais sensíveis nos relatórios de exceção dos serviços fiscais, além das proteções existentes.
- Exportação cifrada **VFX2 em blocos**, em vez de carregar o backup inteiro na memória. O banco real já tinha aproximadamente 634 MB; a limitação antiga de restauração em 512 MB não seria adequada. Integridade, ordem, término e autenticação dos blocos são verificados antes da carga. Datas preservam microssegundos, inclusive intervalos fiscais. Compatibilidade com backups antigos limitados é mantida.
- Restauração transacional somente em banco vazio, arquivo temporário privado e chave original obrigatória. Testes provaram restauração em banco descartável, incluindo A1 fictício, cursores, relacionamentos e espera exata. **Não foi exportado/restaurado o banco real completo nem migrado para PostgreSQL nesta execução.**

## Verificações executadas

- **333 testes Django, todos aprovados**, incluindo isolamento, supervisão, API, certificados, importação, transporte TLS, manifestações, processamento parcial, assinaturas, cancelamento/substituição, indicadores, paginação, PDF, bloqueio de worker e backup/restauração protegida.
- `manage.py check` sem problemas; `makemigrations --check --dry-run` sem migrações faltantes; contrato OpenAPI regenerado e validado.
- Páginas reais supervisionadas de indicadores, pendências e documentos paginados responderam HTTP 200 com autenticação master em cliente HTTP Django. Teste não usa a senha do usuário nem troca sua sessão no navegador.
- Os 13 PDFs parciais foram gerados em memória e tiveram texto/chave/aviso e preservação do XML conferidos. Não equivalem a DANFSe oficial.
- Conferência real do banco e da atividade do worker; nova NFS-e pós-autorização importada automaticamente. Nenhuma consulta manual antecipada, evento transmitido ou reset de NSU.
- **32 verificações de DOM/tema aprovadas** e sintaxe do novo `analytics.css` conferida. Elas **não substituem uma revisão visual em navegador**. A automação de navegador ficou indisponível pela política de confiança da URL. A orientação da skill [computer-use](C:/Users/user/.codex/plugins/cache/openai-bundled/computer-use/26.1013.40934/skills/computer-use/SKILL.md), “stop issuing app input”, foi respeitada; não houve contorno desse bloqueio. A conferência visual manual nos dois temas/celular continua pendente.
- Não houve homologação de PostgreSQL/Redis/Docker, SMTP, TLS público, restauração do banco real, segunda empresa real ou API municipal de DANFSe. Esses limites impedem declarar produção pronta.

## Comandos no Windows

Abra o PowerShell na pasta do projeto:

```powershell
cd C:\Users\user\Downloads\vindex-fiscal
py iniciar.py --preparar
py iniciar.py
```

O primeiro prepara dependências/migrações, o segundo inicia o portal. Nesta máquina as alterações já foram aplicadas e o portal foi reiniciado. Acesse `http://127.0.0.1:8000`, entre na conta existente e abra Indicadores, Documentos pendentes e Conectores fiscais. No master, abra `/gestao/`, escolha o cliente e **Ver painel**.

Diagnósticos sem consultas fiscais:

```powershell
.\.venv\Scripts\python.exe manage.py verificar_captura
.\.venv\Scripts\python.exe manage.py verificar_producao
.\.venv\Scripts\python.exe manage.py reprocessar_documentos --empresa 5 --servico nfse
Get-ScheduledTask -TaskName 'Vindex Fiscal - Captura'
```

O terceiro apenas lista o diagnóstico. Para reaplicar processamento **local**, sem consultar o ADN nem mudar NSU, existe `--executar`; as 13 já foram reprocessadas nesta entrega. Não é um comando diário necessário. A tarefa existente mantém a captura; se estiver parada, use `Start-ScheduledTask -TaskName 'Vindex Fiscal - Captura'`. Não crie outra tarefa duplicada.

Para criar outro master explicitamente e executar os testes:

```powershell
.\.venv\Scripts\python.exe manage.py criar_admin_master
py iniciar.py --testar
```

O cadastro master pede dados interativamente. Não use senha na linha de comando ou no chat. A conta master já existente não precisa ser recriada.

## O que falta para publicar e passos de evolução

1. **Escolher servidor e domínio.** Preparar Linux/Docker e infraestrutura com acesso privado; configurar DNS e HTTPS válido. Não foi contratado ou publicado serviço externo.
2. **Configurar produção.** PostgreSQL, Redis compartilhado, segredo Django, domínio/CSRF/cookies seguros, SMTP/remetente e cadastro com aprovação ou fechado. Preservar a `CERTIFICATE_ENCRYPTION_KEY` original em armazenamento seguro. Não gerar outra para o histórico existente.
3. **Homologar em ambiente restrito.** Seguir [IMPLANTACAO.md](IMPLANTACAO.md), ensaiar backup/restauração do volume real e comparar `conferir_dados` antes/depois. Parar os consumidores antigos antes de ativar o novo; nunca rodar dois consumidores independentes do mesmo CNPJ.
4. **Validar operação real.** Reinício do host/worker, retomada de cursores, indisponibilidade da origem, concorrência PostgreSQL, navegação privada por cliente/master/API, download e carga. Testar segunda empresa real autorizada e nova emissão. Acompanhar a próxima NF-e aceita após o 656 sem reduzir sua espera.
5. **Operar com monitoramento.** Alertas para worker parado, certificado próximo do vencimento, rejeição recorrente, pendências e falha de backup. Política de retenção, responsável por recuperação, suporte e procedimento de revisão dos XMLs parciais. Homologar entrega real de recuperação de senha por SMTP.
6. **Liberar gradualmente.** Começar com clientes piloto e acesso controlado. Validar isolamento e recursos sob carga antes de abertura ampla. Recomendo MFA para contas master antes de ampliação; **MFA não foi implementado nesta entrega**.
7. **Ampliar cobertura com evidência.** Documentar municípios/provedores demandados e obter APIs/autorizações privadas; desenvolver cada adaptador com teste real. A ausência de um provedor não se resolve apenas cadastrando A1. DDA e bancos continuam fora desta etapa.

No servidor, após configuração, migração e início supervisionado do worker, use:

```sh
docker compose -f deploy/compose.yaml exec web python manage.py verificar_producao --estrito
docker compose -f deploy/compose.yaml exec web python manage.py verificar_captura
```

O modo estrito deve passar antes da liberação, mas isso é verificação de configuração, não certificação de infraestrutura ou sucesso fiscal. Os comandos completos e cuidados de migração estão no guia de implantação.

Da sua parte, **não é necessário alterar código a cada novo certificado** nas fontes já implementadas. É necessário cadastrar a empresa corretamente, vincular A1 compatível e válido, concluir autorizações/configuração, manter o worker disponível e atender às causas específicas mostradas no conector. O sistema consulta o que as fontes autorizadas efetivamente disponibilizarem; não promete todas as notas de todos os municípios nem um XML que dependa de manifestação ainda não autorizada.
