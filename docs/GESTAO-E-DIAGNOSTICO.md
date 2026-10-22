# Gestão master e diagnóstico técnico da captura

**Retrato histórico:** há uma entrega posterior com recuperação parcial das 13 NFS-e, nova emissão capturada e nova rejeição 656. Consulte [o relatório atualizado](NFSE-RECUPERACAO-PRODUCAO.md) antes de usar os números e conclusões abaixo como situação atual.

Conferência de dados reais em **21/10/2026, 19:59:18, Brasília**. Empresa piloto Alpha Pet LTDA, CNPJ 55.737.823/0001-96, ambiente de produção. As quantidades abaixo são um retrato; a captura permanece ativa e pode avançar depois desse horário.

## O acesso do administrador

A carteira em `/gestao/` recebeu indicadores de clientes, empresas, documentos importados, erros de conectores/entregas e sinal do processo de captura. Busca aceita nome, e-mail e CNPJ com ou sem pontuação; o filtro de situação mantém a seleção. Componentes usam os tokens Vindex, os dois temas, foco existente e adaptação para celular/tablet. Tabelas extensas conservam rolagem interna.

**Ver painel** abre `/gestao/clientes/ID/painel/`: são as mesmas views/templates do cliente, com seus dados, filtros, indicadores, agenda, notas, boletos, certificados, documentos e integrações. O administrador pode abrir detalhes, baixar XML/PDF e exportar os relatórios CSV existentes. Não foi criado um conjunto paralelo de números ou um relatório fictício.

O contexto administrativo permanece visível. Cliente e escopo ficam na URL, inclusive nos links gerados por Django. Não há troca de `request.user`, login como cliente ou seleção global de Workspace na sessão. Duas abas mantêm escopos independentes. A autenticação e a permissão master são verificadas em cada requisição; a consulta é auditada com o administrador como ator. Respostas desse contexto recebem `no-store`.

**Supervisão é leitura:** POST/PUT/PATCH/DELETE e rotas de alteração são recusados no servidor. Cadastros, uploads, alterações financeiras, emissão de credenciais e manifestações fiscais não são autorizados por esse modo. A API normal mantém seu escopo por credencial/Workspace. Em **Operação e cadastros** continuam os controles administrativos explícitos de aprovar/suspender acesso, pausar/retomar capturas autorizadas e revogar API.

A tela Integrações e API também foi corrigida: havia textos históricos dizendo que transporte A1/worker e conectores ainda não existiam. Agora distingue conectores implementados, cobertura limitada e funcionalidades realmente pendentes.

## O que está funcionando em produção

| Serviço | Notas importadas | Emissão mais recente importada | Último resultado observado |
|---|---:|---|---|
| NF-e modelo 55 | 278 | 01/10/2026 | 138 — Documento(s) localizado(s), 19:28:24 |
| NFS-e tomadas / ADN nacional | 182 | 20/10/2026 | HTTP 404, NENHUM_DOCUMENTO_LOCALIZADO / E2220, 19:27:16 |
| CT-e modelo 57 | 8.682 | 29/08/2026 | HTTP 200 / 138 — documento localizado., 19:59:15 |

Os documentos foram recebidos dos serviços reais. O diagnóstico local confirmou A1 acessível, vigente e com raiz de CNPJ compatível, com autorização de leitura habilitada nos três conectores. O diagnóstico não fez nova consulta fiscal e, sozinho, não comprova aceitação remota; essa aceitação é demonstrada pelas respostas armazenadas.

NF-e usa NFeDistribuicaoDFe por SOAP 1.2; CT-e usa CTeDistribuicaoDFe; NFS-e usa ADN Contribuintes por GET autenticado. O A1 é aberto do armazenamento cifrado existente. As conexões usam autenticação mTLS e verificação TLS; não foi habilitada opção de ignorar certificado do servidor.

O fluxo persistente armazena resposta bruta, classifica documentos e avança o cursor após guardar o lote. XMLs completos compatíveis são importados de forma idempotente. Resumos e eventos têm tratamento próprio e não são promovidos artificialmente a notas. Eventos de cancelamento recebidos não determinam situação de pagamento.

## Por que nem todas as últimas notas já aparecem

### NF-e: histórico ainda incompleto e espera de segurança

Cursor atual **000000000123317**, máximo informado **000000000133839**. Essas posições incluem eventos e resumos: a diferença não representa quantidade de notas faltantes.

A consulta 776 recebeu um lote 138, preservou a resposta e precisou de recuperação local. O lote foi recuperado sem repetir HTTP; o cursor avançou e o intervalo previamente gravado foi mantido. Próxima consulta permitida **20:28:26**. O registro recuperado atual não conserva a causa original dessa falha; não é correto atribuí-la retroativamente a um erro específico de certificado, rede ou banco. A última resposta oficial não foi 656. As rejeições 656 anteriores e a retomada estão documentadas nas entregas históricas.

Ainda existem **13 resumos sem XML completo importado correspondente**. Podem depender de manifestação e da posterior disponibilização do XML pela origem. A aplicação exige autorização específica por documento para Ciência da Emissão; não envia Confirmação da Operação automaticamente. Não foi enviada manifestação nesta etapa. O certificado e a autorização geral de leitura não substituem essa decisão fiscal.

**Consequência:** NF-e está conectada e importando, mas ainda não foi comprovado que a fila esteja atualizada até hoje. O worker retomará a partir do cursor permitido, sem pular documentos intermediários.

### NFS-e: fila consultada, com 13 importações locais bloqueadas

O ADN entregou **195 XMLs completos e 3 eventos**. Foram importadas 182 notas. **13 completos** permanecem preservados com o erro:

> Documento não corresponde ao schema oficial NFSe_v1.00.xsd. Original preservado para revisão.

Os campos que provocam a recusa nos pacotes conhecidos são `pAliq` (11 documentos) e `xOutInf` (2). Isso depende de compatibilidade/validação de leiaute no conector. Não é resolvido reenviando certificado, alterando senha ou inventando valores. Não foram removidas restrições gerais nem alterado o XML para forçar importação.

O cursor está em **198**. A resposta HTTP 404 com status explícito `NENHUM_DOCUMENTO_LOCALIZADO` e E2220 indica ausência de novos documentos depois desse NSU naquela consulta; não significa falha de certificado. Próxima consulta permitida **20:28:16**.

**Consequência:** há NFS-e recentes, até 20/10. A abrangência é das notas compartilhadas no ADN, com a empresa como tomadora nos papéis implementados. Não existe cobertura universal de todas as prefeituras, todos os leiautes e todas as modalidades de NFS-e.

### CT-e: leitura automática dos lotes antigos

Cursor **000000000067381**, máximo **000000000080991**. Sem erro local de entrega nesse retrato. A próxima tentativa estava permitida a partir de **19:59:17**, e a fila continuava avançando. Durante esta etapa passou de 7.534 para 8.682 notas importadas sem consulta manual.

**Consequência:** o conector funciona, porém a data máxima de emissão ainda é de agosto porque o histórico não terminou. A quantidade final e a chegada ao período atual precisam continuar sendo acompanhadas. Não foi reiniciado o cursor nem executada uma busca artificial direto no máximo para aparentar atualização.

## Como a automação diária funciona

1. O usuário cadastra o CNPJ e vincula um A1 válido, com sua senha informada somente na aplicação. CNPJ/validade e possibilidade de abertura são verificados.
2. No vínculo, seleciona as autorizações de leitura de NF-e, NFS-e e/ou CT-e. CT-e exige UF. A configuração persistida torna a empresa elegível para a fila; salvar o formulário não realiza HTTP fiscal dentro da requisição web.
3. O processo periódico verifica a fila local a cada **15 segundos** por padrão, com retomada mais rápida para paginação NF-e permitida. Isso não significa consultar a SEFAZ a cada 15 segundos para cada empresa: o banco controla elegibilidade e intervalos de cada serviço.
4. Quando permitido, consulta o próximo NSU, guarda e importa o lote. Ao atingir o fim/sem documentos, espera aproximadamente **uma hora e um minuto**; rejeições e resultados incertos impõem esperas próprias. Cada resposta prevalece sobre qualquer intenção de consultar “uma vez por dia”.
5. Uma reserva temporária impede concorrência no mesmo CNPJ/serviço/ambiente. O progresso é persistente; reiniciar o processo ou renovar o A1 não zera o histórico. Clientes diferentes com o mesmo CNPJ só recebem em seu próprio Workspace se tiverem certificado próprio válido e leitura autorizada.
6. Novos lotes disponibilizados pela origem seguem o mesmo processamento, sem solicitar mudanças de código ou um clique por consulta. Enquanto houver histórico anterior, a atualização do período mais recente pode ficar atrasada.

**Confirmação com limites:** o agendamento e a importação periódica existem para todas as empresas elegíveis, não só o piloto. A captura não é habilitada indiscriminadamente apenas por anexar um arquivo de certificado. A disponibilidade de XML completo, as autorizações e a cobertura de cada serviço continuam necessárias. Não há dependência da Qive.

## O que depende do usuário e o que depende do desenvolvimento

| Ponto | Situação / responsável |
|---|---|
| Empresa nova | Usuário cadastra CNPJ, A1, UF quando exigida e conclui as autorizações na aplicação. Depois não precisa conversar com o desenvolvedor a cada nota. |
| Alpha Pet | A1 e leitura dos três serviços já estão configurados. Não é necessário repetir o vínculo para continuar o histórico. |
| Resumos NF-e sem XML | Responsável fiscal avalia e autoriza a manifestação específica quando cabível. Não prometer download imediato após o evento. |
| 13 NFS-e de leiaute incompatível | Desenvolvimento/validação do conector; originais já preservados. |
| Computador local | Deve permanecer ligado, com internet e sessão Windows conectada. Captura tem tarefa própria, independente da aba do navegador. |
| Operação 24 horas | Servidor sempre disponível, domínio/HTTPS e homologação de infraestrutura. Preparação existe; implantação externa/PostgreSQL/Redis/SMTP ainda não foram homologados aqui. |
| DANFSe oficial | Pendente. Há PDF de conferência da NFS-e; DANFE NF-e e DACTE CT-e continuam disponíveis. Não confundir espelho com DANFSe oficial v2.0. |
| DDA / conexões bancárias | Fora da etapa; não implementados. |

A tarefa Windows **Vindex Fiscal - Captura** estava **Running**, sem limite de duração, habilitada para continuar em bateria, com início no logon e três tentativas de reinício em caso de falha, com intervalo de um minuto. Isso não substitui monitoramento ou hospedagem 24 horas. Não foi realizado reinício real do Windows nesta conferência.

Não foi comprovado em produção o ciclo completo de uma nota emitida depois da ativação, para uma segunda empresa real. Há testes isolados de dois Workspaces recebendo lote posterior, e há crescimento real automático do histórico do piloto. São evidências diferentes; nenhuma foi apresentada como se fosse a outra.

## Como conferir agora

Atualize **http://127.0.0.1:8000/gestao/** com a conta master já criada. Na carteira, clique em **Ver painel**. Use **Captura de NF-e** para consultar respostas/intervalos; em **Minhas empresas → Conectores**, confira NFS-e/CT-e. **Documentos consolidados** mostra os documentos importados. Na agenda e nas notas, os CSVs disponíveis usam o mesmo escopo e filtros do cliente.

Se o sistema estiver parado, execute na pasta do projeto:

```powershell
py iniciar.py
```

Para diagnosticar sem disparar uma nova consulta fiscal:

```powershell
.\.venv\Scripts\python.exe manage.py verificar_captura
.\.venv\Scripts\python.exe manage.py diagnosticar_empresa --empresa 5
Get-ScheduledTask -TaskName 'Vindex Fiscal - Captura'
```

Se o diagnóstico indicar processo parado e a tarefa não estiver em execução:

```powershell
Start-ScheduledTask -TaskName 'Vindex Fiscal - Captura'
```

Para executar os testes isolados:

```powershell
py iniciar.py --testar
```

Esses comandos de diagnóstico não precisam ser repetidos a cada certificado ou nota. Não envie senhas, certificados ou chaves pelo chat.

## Verificações concluídas

- **311 testes aprovados** na suíte completa final por `py iniciar.py --testar`, em **161,836 segundos**. Incluem autenticação, API, escopo, certificados, importação e os novos testes de supervisão.
- A supervisão foi testada com duas contas/Workspaces: igualdade dos indicadores do dashboard, alternância entre abas, links no escopo, CSV somente do cliente, XML estrangeiro 404, alteração de permissão entre requisições, bloqueio de formulários/POST, ausência de criação de Workspace para o master e auditoria com identidade administrativa.
- **32 verificações de tema/DOM/CSS aprovadas**; sintaxe do novo CSS administrativo validada. `manage.py check` sem problemas e `makemigrations --check --dry-run` sem mudanças pendentes.
- A conta master existente acessou por HTTP o servidor em execução: carteira, painel do cliente e agenda retornaram **200** com o contexto esperado. Também foram conferidos documentos, integrações e operação por renderização Django; saúde e arquivo CSS responderam 200. Sessões de verificação foram encerradas sem alterar as sessões do navegador do usuário.
- Diagnóstico final confirmou captura ativa. Não houve reinício do cursor, nova consulta fiscal manual ou envio de evento para realizar esses testes. Nenhum teste simulado foi executado sobre os documentos/certificados reais.

## Limite da conferência visual

O controle do navegador foi interrompido pela ferramenta porque ela não conseguiu determinar a URL atual com confiança suficiente. Não houve tentativa de contornar o bloqueio. Os testes de renderização HTTP, DOM/CSS e escopo não equivalem a uma inspeção visual real nos dois temas e em todos os tamanhos; essa validação permanece pendente.

Foi utilizada a habilidade [Computer Use](C:/Users/user/.codex/plugins/cache/openai-bundled/computer-use/26.1013.40934/skills/computer-use/SKILL.md). Sua [orientação de interrupção](C:/Users/user/.codex/plugins/cache/openai-bundled/computer-use/26.1013.40934/docs/guidance.md) exige “stop issuing app input” quando o controle é encerrado; por isso a automação do navegador foi interrompida.
