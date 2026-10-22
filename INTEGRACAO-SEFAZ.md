# Captura oficial de NF-e — estado atual

**Auditoria posterior:** [gerenciamento e investigação 656](docs/GESTAO-CADASTROS-656-POSTGRES.md). Os dois acessos do piloto compartilham uma fila; não foi comprovada a causa da rejeição. Reforçados consumo por identidade/ciclo e preservação do retorno em falha de gravação, sem mudança manual de NSU.

**Referência atual (22/10):** [revisão final e diagnóstico por serviço](docs/REVISAO-FINAL-E-PUBLICACAO.md). A NF-e permanece com rejeição 656 na última resposta conhecida; o “Ainda não executada” do segundo acesso foi corrigido apenas na apresentação. A investigação usou exclusivamente registros locais/documentação, sem consultas fiscais ou mudanças de cursor/intervalo.

**Política atual:** [intervalos e diagnóstico do aviso de erro](docs/AJUSTE-INTERVALOS-E-MENU.md). A espera padrão após 137/656/fim da fila passou a duas horas; referências anteriores a uma hora descrevem o mínimo ou o comportamento anterior. O histórico ainda disponível continua em lotes com intervalo curto.

**Atualização de 21/10 às 21h01:** [relatório atual](docs/NFSE-RECUPERACAO-PRODUCAO.md). NF-e em espera por 656, cursor preservado; NFS-e com nova emissão importada automaticamente e CT-e avançando. As referências anteriores abaixo são históricas.

**Diagnóstico mais recente:** [gestão e situação técnica da captura](docs/GESTAO-E-DIAGNOSTICO.md). As referências numéricas históricas abaixo não substituem o painel privado atual.

**Conferência posterior:** a retomada das 15:43 de 21/10/2026 recebeu novas respostas 138. Um lote preservado foi recuperado localmente após falha de armazenamento, sem repetir HTTP nem antecipar a espera. Veja o [relatório da nova etapa](docs/ENTREGA-CONECTORES-MASTER.md). NFS-e e CT-e agora possuem [conectores separados](docs/MASTER-E-CONECTORES.md); as seções abaixo descrevem especificamente NF-e.

Atualizado em **21/10/2026**. O transporte oficial está implementado e foi executado em produção com o A1 cifrado da empresa piloto. Houve recebimento e importação de XML completo real no CNPJ correto. O resultado de cada consulta pertence ao banco privado e aparece em **Captura SEFAZ**. Não há dependência da Qive.

O fluxo atende às empresas de todos os Workspaces: certificado válido, autorização de leitura e processo de captura ativo. Certificados existentes não são habilitados indiscriminadamente. A autorização do piloto foi registrada conforme instrução do proprietário; outras empresas autorizam na aplicação. Na última conferência, o piloto tem quatro notas reais importadas e aguarda a próxima tentativa após rejeição oficial 656; o motivo e a investigação estão no relatório atualizado. A estabilidade contínua e o fim da fila ainda não estão comprovados.

Veja [o guia de uso no Windows](docs/CAPTURA-SEFAZ.md), [o relatório atualizado](docs/RELATORIO-ATUAL.md) e [a preparação de produção](docs/PRODUCAO.md). A retomada automática após a espera foi comprovada em 21/10/2026, às 14:25:48 (Brasília), com novas notas reais importadas pelo worker. A tarefa de captura no logon já está registrada nesta instalação.

## Transporte

| Ambiente | NFeDistribuicaoDFe |
|---|---|
| Produção | https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx |
| Homologação | https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx |

O transporte usa SOAP 1.2, operação `nfeDistDFeInteresse`, XML `distDFeInt` versão 1.01, namespace NF-e sem prefixo e NSU de 15 posições. `cUFAutor` é opcional; não é inventada uma UF. Endpoint e SOAP action foram confirmados pelo WSDL de produção obtido com mTLS. A validação TLS não foi desativada.

O A1 e sua senha são abertos do armazenamento Fernet existente durante o uso. Cada uso revalida vigência e raiz do CNPJ. A chave PEM temporária exigida pelo SSLContext fica cifrada com senha efêmera em diretório privado, com ACL restrita no Windows, e é removida antes da conexão. As autoridades do sistema validam o servidor. `SEFAZ_EXTRA_CA_FILE` permite autoridades adicionais verificadas; não existe opção de ignorar TLS.

## Estado e processamento

- `portal/services/capture.py`: autorização, requisitos, consulta de uma página, armazenamento durável e entrega privada.
- `portal/services/sefaz_transport.py`: transporte oficial. `portal/services/sefaz_schema.py`: validação com schemas oficiais locais, sem downloads de schema em tempo de execução.
- Cursor, cooldown e lease são únicos por CNPJ/ambiente/origem em `SefazDistributionStream`. Empresas do mesmo CNPJ em Workspaces diferentes coordenam o consumo nesta instalação.
- Cada entrega exige autorização e A1 válido da própria empresa, revalidado antes de espelhar documentos. A interface nunca expõe a caixa de outro Workspace.
- A resposta oficial fica no histórico privado antes da validação/processamento, com código, motivo, horário e contagens. XMLs reais não entram em código, exemplos ou logs.
- Cada lote admite até 50 documentos. Limites locais: resposta de 12 MB, documento de 2 MB e lote descompactado de 20 MB, protegidos contra DTD/entidades e expansão gzip.
- Resumos, XMLs completos, eventos e resumos de eventos ficam separados. Só XML completo modelo 55 com destinatário correspondente é importado como NF-e recebida.
- Hash, NSU conhecido e chave da nota evitam duplicidades. XML com impedimento fica preservado, com causa visível e nova tentativa local, sem repetir a consulta para recuperar o mesmo conteúdo.
- O worker pagina enquanto há documentos disponíveis. Após 137, 656 ou fim da fila aceita, aguarda pelo menos uma hora. Resultado desconhecido também provoca espera conservadora de uma hora.
- Rejeições não fazem o cursor saltar para NSU informativo. A relação entre `ultNSU` e `maxNSU` de uma rejeição não é interpretada como avanço aceito.

O pipeline legado `run_distribution` permanece para testes internos com transporte injetado. O fluxo público real usa `capture.run_company` e coordenação global. Origem `test` nunca é apresentada como consulta real. A API REST não expõe execução de consultas nem manifestações.

## Manifestação

A leitura não autoriza eventos. Somente **Ciência da Emissão (210210)** tem envio implementado, mediante autorização específica por resumo/chave, sessão do proprietário e POST com CSRF. Não há Ciência automática no worker, upload ou download. Nenhum evento fiscal real foi enviado durante o piloto.

O evento é assinado pelo A1 e enviado a NFeRecepcaoEvento4. Ambiente, órgão, chave, tipo e sequência são conferidos; o protocolo é necessário para apresentar registro aceito. Há bloqueio por CNPJ/ambiente/chave, inclusive entre Workspaces. Resultado incerto exige revisão antes de reenvio. Os schemas atuais suportam CNPJ alfanumérico.

Ciência registra conhecimento da emissão e pode permitir disponibilização posterior do XML. Não confirma a operação comercial. O prazo de Ciência é de 10 dias da autorização; a manifestação conclusiva aplicável tem prazo de 90 dias da autorização segundo as fontes abaixo. Confirmação da Operação, Desconhecimento e Operação não Realizada não têm envio implementado. A interface informa a necessidade de acompanhamento fiscal.

## Disponibilidade e limites

A distribuição mantém documentos por até 90 dias. Para novo usuário, a geração de NSU inicia no primeiro acesso; não há garantia de recuperação retroativa. Após mais de 60 dias sem uso, a geração retoma com novo acesso. Cancelamentos podem ser distribuídos sem manifestação. Eventos recebidos não mudam automaticamente parcelas, pagamentos ou situação fiscal.

O limite de 20 consultas por hora da NT aplica-se a `consNSU` e `consChNFe`, não à paginação `distNSU` implementada aqui. Consultas pontuais ainda não estão disponíveis. Consumidores externos e instalações com bancos separados precisam coordenar NSU. Uma falha isolada não comprova a existência de outro consumidor.

DDA, consulta bancária, conciliação e pagamentos continuam sem conector bancário. NFS-e e CT-e possuem transporte/importação próprios, separados deste conector NF-e. O uso local não substitui hospedagem, backup, monitoramento e validação de concorrência em PostgreSQL.

## Fontes oficiais verificadas

- [NT 2014.002 v1.40 — distribuição](https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=uWO2d%2FgTuWg%3D).
- [Schemas distribuição 1.04](https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=IzuP2y0G6hk%3D).
- [Serviços de produção](https://www.nfe.fazenda.gov.br/portal/webServices.aspx).
- [NT 2020.001 v1.60 — manifestação](https://www.nfe.fazenda.gov.br/Portal/exibirArquivo.aspx?conteudo=%2BWTd7iuD21s%3D).
- [Pacote 010d v1.03 — schemas de eventos atuais](https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=%2BpBOYTXBtbk%3D).
- [Proveniência dos schemas locais](portal/services/schemas/sefaz/LEIA-ME.md).
