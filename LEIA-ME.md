# Vindex Fiscal — plataforma local e API própria

**Gerenciamento atualizado (22/10/2026):** [contas, empresas, A1, serviços, auditoria 656 e preparação PostgreSQL](docs/GESTAO-CADASTROS-656-POSTGRES.md). Em Gestão master → Operação e cadastros, use **Gerenciar conta, empresas e certificados**. Desativação preserva histórico; exclusão física só é permitida para cadastro vazio. Nenhum cadastro real foi removido automaticamente e a rejeição NF-e ainda não foi considerada resolvida.

**Revisão final de 22/10/2026:** [relatório operacional, arquitetura, diagnóstico e roteiro de publicação](docs/REVISAO-FINAL-E-PUBLICACAO.md). Ajustes pontuais de status/desempenho e bloqueio da API para contas pendentes/suspensas; 345 testes aprovados. NF-e continua com última resposta 656; CT-e/NFS-e têm estados próprios. Nenhuma consulta fiscal, alteração de cursor/intervalo ou publicação foi executada nessa revisão. Homologação de infraestrutura ainda é obrigatória.

**Ajuste posterior:** [aviso antigo do worker, intervalo de duas horas e organização do menu](docs/AJUSTE-INTERVALOS-E-MENU.md). O 656 permanece como resposta oficial; o progresso foi preservado e a espera ampliada.

**Entrega atual (21/10/2026):** [recuperação de NFS-e, indicadores, captura real e passos para produção](docs/NFSE-RECUPERACAO-PRODUCAO.md). As 13 notas antes recusadas estão disponíveis como **parciais**, preservando originais e pendências. Novas telas: **Indicadores** (`/indicadores/`) e **Documentos pendentes** (`/documentos/pendentes/`), também no painel supervisionado pelo master. Uma nova NFS-e foi importada automaticamente após a autorização. NF-e voltou a aguardar rejeição 656; veja horários e limites no relatório. PDF oficial municipal ainda depende de adaptador homologado. A publicação exige configurar e validar a infraestrutura do [guia de implantação](docs/IMPLANTACAO.md).

**Gestão atualizada:** [painel master, supervisão do cliente e diagnóstico técnico da captura](docs/GESTAO-E-DIAGNOSTICO.md). Na carteira de clientes, use **Ver painel** para navegar pelas mesmas telas do cliente em leitura, com sua identidade administrativa preservada.

Última continuação: [captura, painel master e PDF de NFS-e](docs/CONTINUACAO-CAPTURA-PDFS.md). O master permite filtrar e paginar NFS-e/CT-e e conferir as datas de emissão/importação. NFS-e tem PDF de conferência privado; DANFSe oficial v2.0 segue pendente.

**Etapa atual:** [gestão master, NFS-e/CT-e e comandos no Windows](docs/MASTER-E-CONECTORES.md), [resultado real e limites](docs/ENTREGA-CONECTORES-MASTER.md) e [implantação preparada](docs/IMPLANTACAO.md). O acesso master é criado explicitamente pelo comando local, sem senha padrão.

Portal web independente em Python e Django, com identidade visual baseada na referência enviada por Raphael. A marca usa azul vivo sobre azul muito escuro, com conteúdo claro e painéis organizados por CNPJ. Este projeto não está integrado aos aplicativos existentes da Vindex.

## Começar no Windows

1. Extraia todo o ZIP para uma pasta normal, por exemplo `Documentos/vindex-fiscal`.
2. No VS Code, escolha **Arquivo > Abrir pasta** e selecione a pasta que contém `iniciar.py`.
3. Abra **Terminal > Novo Terminal**.
4. Execute:

```powershell
py iniciar.py
```

Se o comando `py` não existir, tente `python iniciar.py`.

Na primeira execução, o inicializador cria `.venv`, instala as bibliotecas de `requirements.txt`, gera chaves exclusivas em `.env` e prepara o banco SQLite. É necessário acesso à internet para baixar as bibliotecas. Nenhuma conta em hospedagem ou API paga é contratada.

Abra **http://127.0.0.1:8000** no navegador. Clique em **Criar conta** e cadastre seu nome, e-mail, cliente/grupo e senha. Não existe senha padrão ou usuário administrativo pré-configurado.

Você também pode abrir `iniciar-windows.bat`. O comando inicia o servidor e o processo de captura das empresas com leitura autorizada, ou aproveita um processo de captura já ativo. **Ctrl+C** encerra os processos iniciados nesse terminal; uma tarefa independente de captura no Windows continua ativa. Os dados, as autorizações, os intervalos e o progresso de NSU continuam no banco para a próxima execução.

## Dados reais no uso normal

O portal trabalha com os documentos da sua conta. Exemplos e seeds foram retirados do fluxo normal. Registros identificados por origem de teste ficam preservados, sem entrar nas contagens operacionais. Dados ficticios permanecem somente nas conferencias automatizadas em banco isolado.

## Novos recursos: boletos, revisão e API

Abra **Boletos** para importar PDF/dados e associar uma cobrança à parcela correta. Nos detalhes da nota, **Informar previsão manual** e **Revisar dados** permitem completar condições encontradas, com motivo e histórico, sem confirmar pagamento.

Em **Integrações e API**, gere uma credencial individual com empresas, permissões e validade. O segredo aparece uma vez; a revogação é feita pela mesma tela. Swagger em **http://127.0.0.1:8000/api/v1/docs/** e ReDoc em **http://127.0.0.1:8000/api/v1/redoc/** descrevem somente operações implementadas.

Veja o [estado atual da captura oficial](INTEGRACAO-SEFAZ.md), o [refinamento visual](docs/QA-VISUAL.md), a [entrega anterior da API, de 20/10/2026](docs/ENTREGA.md), a [documentação da API](docs/API.md), os [boletos](docs/BOLETOS.md), a [matriz com fontes Qive/SEFAZ](docs/MATRIZ-FUNCIONAL.md) e a [preparação para produção](docs/PRODUCAO.md). O conector SEFAZ é próprio; não depende da Qive. DDA e OCR continuam sem integração.

## Tema claro e escuro

Use **Ativar modo escuro** (lua) ou **Ativar modo claro** (sol) no cabeçalho ou acima do formulário de acesso. O texto e o ícone mostram a próxima ação. Há apenas esse botão de tema.

No primeiro acesso, o tema acompanha a preferência de aparência do sistema. Ao alternar pelo botão, a preferência fica salva neste navegador e é mantida ao navegar ou recarregar a página. A escolha vale para quem usar este navegador; ela não é um dado da conta e não é sincronizada com outros dispositivos. Sem armazenamento local, a alternância continua funcionando na página atual. Sem JavaScript, o tema acompanha o sistema e o botão fica oculto.

Para visualizar a mudança, inicie o projeto normalmente com `py iniciar.py` e atualize o navegador. Se os arquivos antigos estiverem no cache, use **Ctrl+F5**. Não é necessário instalar bibliotecas nem alterar o banco para usar o tema.

## O que já funciona

| Área | Entrega |
|---|---|
| Acesso | Cadastro, login por e-mail, alteração de senha e logout por POST |
| Minha conta | Nome, telefone e nome do cliente/grupo |
| Empresas | Vários CNPJs por cliente, cadastro e edição de dados |
| Painel | Visão unificada e filtro por empresa, com nome e CNPJ em cada nota |
| Notas | Importação de até cinco XMLs de NF-e modelo 55, detalhes, XML original e DANFE em PDF quando o XML permite geração fiel |
| Financeiro | Duplicatas do XML, revisão e inclusão manual com histórico, agenda e conferência; sem comprovação bancária |
| Boletos | PDF privado ou dados estruturados, dígitos verificadores, revisão e vínculo explícito com parcela |
| API própria | REST /api/v1/, credenciais por integração/empresas, escopos, validade e revogação; OpenAPI e exemplos |
| Certificados | Upload A1, conferência local do arquivo, senha, validade e CNPJ; renovação e remoção |
| Captura oficial | NFeDistribuicaoDFe com A1/mTLS e TLS validado, leitura autorizada por empresa, worker, NSU persistente e importação dos XMLs completos recebidos |
| Novos conectores | ADN Contribuintes para NFS-e tomadas e CTeDistribuicaoDFe para CT-e 57, com filas próprias e XMLs privados; DACTE quando gerável |
| Gestão master | /gestao/, permissão própria, supervisão por URL em leitura, controles separados de conta/API/captura e auditoria |
| Documentos distribuídos | Resumos, XMLs completos, eventos e resumos de eventos separados; downloads privados e histórico das respostas oficiais |
| Ciência da Emissão | Envio somente após autorização explícita por resumo; não confirma a operação nem é enviado pelo worker |
| Exportação | CSV de notas e previsões, respeitando os filtros e o acesso do usuário |
| Histórico | Registro das principais operações de cadastro, importação e certificados |

O painel de cada empresa é vinculado ao **CNPJ**, e o certificado é uma credencial renovável daquela empresa. Trocar ou remover o certificado não apaga as notas.

Em **Notas**, baixe **XML** ou **DANFE (PDF)**. O PDF é gerado pelo Vindex a partir do XML completo com protocolo; resumos não permitem essa geração. Veja [DANFE](docs/DANFE.md) e o [relatório atualizado da captura real](docs/RELATORIO-ATUAL.md).

## Importar um XML real

1. Cadastre o CNPJ destinatário em **Minhas empresas**.
2. Abra **Importar XML** e selecione arquivos `.xml` de NF-e de produto, modelo 55.
3. O sistema identifica a empresa destinatária e rejeita documentos que não pertencem às empresas cadastradas na sua conta.
4. A chave da nota impede importação duplicada dentro da mesma empresa.
5. Veja as duplicatas em **Agenda financeira** ou abra o documento para conferir cada parcela.

O arquivo deve estar em UTF-8, com namespace da NF-e e chave de acesso. PDFs, fotos, NFS-e, resumos de NF-e e XMLs de eventos ainda não entram neste fluxo. Cada XML pode ter até 2 MB; o envio aceita no máximo cinco arquivos. Os valores precisam ser positivos nesta versão.

A leitura usa `cobr/dup/nDup`, `dVenc` e `vDup`. Quando faltam valores, datas ou duplicatas, o sistema sinaliza a conferência e não inventa condições comerciais. Finalidades especiais, como devolução, não geram parcelas automaticamente. Divergência entre soma das duplicatas e valor total fica sinalizada.

**A importação não valida a assinatura digital, a cadeia ICP-Brasil ou a situação atual da nota na Sefaz.** Um protocolo de autorização dentro do arquivo é apenas uma informação do XML. O usuário continua responsável por conferir a operação antes de lançar obrigações definitivas.

## Parcelas não são pagamentos

- Os valores exibidos são **previsões**, sujeitas à conferência.
- A marca **Conferida** registra somente a revisão dos dados.
- Vencimento passado não indica necessariamente falta de pagamento.
- Boletos e linha digitável podem ser importados e analisados localmente. Não há consulta de saldo, DDA, baixa ou pagamento bancário nesta entrega.
- O sistema não agenda pagamentos no banco.

## Certificados A1

Em **Certificados**, escolha a empresa, envie um `.pfx` ou `.p12` de até 1 MB, informe a senha e confirme que está autorizado a utilizá-lo.

A conferência local exige chave privada, período vigente e campo e-CNPJ no `otherName` de OID `2.16.76.1.3.3`. A raiz do CNPJ do certificado deve coincidir com a da empresa. Isso permite a associação entre matriz e filiais da mesma raiz, quando aplicável. Arquivos sem CNPJ reconhecível são rejeitados.

O arquivo e a senha são cifrados com Fernet antes de irem para o banco. A senha não reaparece nas telas, e o certificado não tem URL pública de download. Esta conferência não verifica cadeia ICP-Brasil, revogação ou aceitação pelo serviço governamental.

O formulário permite **habilitar a captura automática de leitura em produção**. Essa autorização é separada da permissão para armazenar e utilizar o certificado. Ao concluir o envio com a captura habilitada, os requisitos são validados e a primeira consulta é agendada. Para certificados já cadastrados, abra **Captura de NF-e**, escolha a empresa e autorize as consultas. A UF é opcional no serviço de distribuição.

O cadastro do A1 não prova aceitação pelo governo. O painel identifica a última tentativa, código e motivo oficial, documentos recebidos, impedimentos e a próxima consulta permitida. Certificado ausente, vencido, incompatível ou impossível de abrir com a chave local impede a consulta e exige a ação indicada. Renovar um A1 de uma captura já autorizada retoma o agendamento, preservando o NSU e os intervalos. Nunca envie certificados ou senhas ao chat ou ao GitHub.

## Captura automática no uso diário

1. Cadastre a empresa no seu acesso e vincule seu A1 válido.
2. Habilite e autorize **somente as consultas de leitura**, no envio do A1 ou em **Captura de NF-e**.
3. Mantenha `py iniciar.py` em execução. O inicializador abre o portal e o worker; reinicia o worker caso ele encerre inesperadamente. Cada início retoma a fila persistida.
4. Acompanhe a empresa em **Captura de NF-e**. XMLs completos de NF-e modelo 55 destinados ao CNPJ passam pelo importador e aparecem em **Notas fiscais**, sem duplicidade por chave/empresa. Resumos e eventos ficam na captura, sem criar parcelas fictícias.

Os lotes seguem o cursor informado pela SEFAZ. A aplicação compartilha a trava e o intervalo do mesmo CNPJ/ambiente entre seus clientes, mas entrega documentos apenas a empresas do acesso autorizado, com consentimento e certificado compatível válido. Outros programas que consultem o mesmo CNPJ precisam coordenar a sequência e o intervalo; o Vindex não controla sistemas externos. Após falta de documentos, consumo indevido ou fim da sequência, a próxima consulta respeita pelo menos uma hora de espera. O polling local da fila não significa uma nova chamada ao governo a cada verificação.

A distribuição não garante todo o histórico. Para novo usuário ou após longa interrupção, as regras oficiais de geração de NSU e disponibilidade podem limitar os documentos retornados. Algumas notas chegam primeiro como resumo. Uma consulta aceita sem documentos é registrada como tal, sem preencher o painel com exemplos.

**Ciência da Emissão é um evento fiscal real.** Abra o resumo, leia os efeitos e marque a autorização específica caso queira enviá-lo. Ciência registra conhecimento da emissão, não confirma a operação comercial, e exige manifestação conclusiva posterior no prazo legal aplicável. A captura não envia Ciência automaticamente. Confirmação da Operação, Desconhecimento da Operação e Operação não Realizada não são enviados por esta aplicação. Download de documento também não envia eventos. Consulte [INTEGRACAO-SEFAZ.md](INTEGRACAO-SEFAZ.md) para os limites e verificações atuais.

Para executar somente o worker, sem abrir outro servidor:

```powershell
py iniciar.py --capturar
```

Esse comando é uma alternativa para operação separada; o uso diário com `py iniciar.py` já inclui a captura. Encerrar o terminal interrompe as consultas até o próximo início. Operação contínua no Windows deve manter o processo sob um serviço ou tarefa supervisionada, conforme [PRODUCAO.md](docs/PRODUCAO.md).

## Dados e recuperação

- `dados.sqlite3`: contas, empresas, XMLs e certificados cifrados.
- `.env`: segredos locais e chave necessária para abrir os certificados.
- `.venv`: bibliotecas instaladas, que podem ser recriadas.

O ZIP não contém banco com dados, segredos, certificados reais, ambiente Python ou documentos dos clientes. Tudo é criado no seu computador.

Para um backup local consistente, encerre o servidor antes de copiar o banco. Guarde também a chave de cifra de `.env` em local separado e protegido: perder essa chave impede recuperar os certificados cifrados. Copiar banco e chaves juntos para um local exposto elimina a proteção prática da cifra.

O `.gitignore` exclui banco, `.env`, certificados, ambiente Python e chaves privadas. Confira os arquivos antes de qualquer commit. O repositório deve guardar somente código e exemplos fictícios.

## Verificação realizada

A verificação atual e os limites do conector estão em [INTEGRACAO-SEFAZ.md](INTEGRACAO-SEFAZ.md); `docs/ENTREGA.md` preserva o resultado histórico de 20/10/2026. A suíte inclui acesso, importação, certificados, API, boletos, revisão de previsões, transporte, schemas, captura persistente e autorização da interface. Os testes automatizados usam documentos sintéticos e banco de teste; não executam consultas fiscais, bancárias ou manifestações reais. A consulta piloto real é uma operação separada, registrada no relatório de captura.

Para executar no seu computador:

```powershell
py iniciar.py --testar
```

Para apenas instalar e preparar, sem abrir servidor:

```powershell
py iniciar.py --preparar
```

A interface contém regras responsivas para desktop e celular; a limitação da inspeção visual anterior está documentada em `docs/QA-VISUAL.md`. Houve consulta piloto real de distribuição com A1 e importação de XML, conforme o relatório atual de captura. Isso não comprova cobertura universal, homologação de todos os cenários fiscais ou implantação pública. DDA e operações bancárias não foram executados.

## Estrutura para continuar no VS Code

- `config/`: configurações e rotas principais.
- `portal/models.py`: cliente, empresas, certificados, notas e parcelas.
- `portal/forms.py`: formulários e validações de entrada.
- `portal/views.py`: telas, filtros e ações com escopo por cliente.
- `portal/services/invoices.py`: leitura e importação do XML.
- `portal/services/certificates.py`: inspeção e cifra dos certificados.
- `portal/services/sefaz_transport.py`: transporte oficial com A1/mTLS e validação TLS.
- `portal/services/capture.py`: autorizações de leitura, fila durável, entrega por cliente e progresso por CNPJ/ambiente.
- `portal/management/commands/capturar_sefaz.py`: worker periódico de leitura.
- `portal/capture_views.py`: acompanhamento da captura e autorização específica de Ciência.
- `portal/services/sefaz_manifest.py`: envio de Ciência da Emissão autorizado por documento.
- `portal/services/demo.py`: dados estritamente fictícios.
- `portal/tests.py`: testes de comportamento e isolamento.
- `templates/portal/`: páginas HTML.
- `static/portal/app.css`: tema, componentes e responsividade.
- `static/portal/app.js`: menu móvel, filtros e seleção de arquivos.
- `INTEGRACAO-SEFAZ.md`: estado real, regras, fontes e limites da captura.
- `IDENTIDADE-VISUAL.md`: tokens e decisões de identidade.

## Antes de publicar ou receber clientes externos

Esta é uma base local funcional, não uma instalação liberada para produção. A recuperação de senha por e-mail exige SMTP configurado. Verificação de e-mail e gestão de vários usuários por cliente ainda não foram implementadas; uma conta proprietária representa cada cliente/grupo. O administrador técnico do Django, se criado, tem acesso administrativo global. O limite de tentativas utiliza cache local e deve ser substituído por controle compartilhado no ambiente publicado.

A publicação exige revisão da separação entre clientes, política de acesso a certificados, cadeia/revogação quando aplicável, backups com restauração testada, HTTPS, `DEBUG=False`, servidor adequado, banco persistente, tratamento de erros e monitoramento. Segredos e certificados não devem ser expostos a logs nem a repositórios.

O transporte SEFAZ e o worker estão implementados. Publicar para clientes externos ainda exige configurar e supervisionar o worker, validar concorrência e isolamento na infraestrutura escolhida e monitorar falhas/intervalos. `runserver` e o inicializador local não substituem um servidor de produção. DDA é uma integração bancária própria, distinta do serviço fiscal, e continua sem implementação. Consulte `INTEGRACAO-SEFAZ.md`.

## Documentação de referência

- Django: https://docs.djangoproject.com/en/5.2/
- Segurança na publicação: https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/
- Certificados PKCS#12: https://cryptography.io/en/latest/hazmat/primitives/asymmetric/serialization/#pkcs12
- Portal NF-e: https://www.nfe.fazenda.gov.br/portal/

Sem instalação de serviços pagos pelo inicializador. Custos de hospedagem, operação contínua, banco e serviços externos devem ser definidos antes da publicação.
