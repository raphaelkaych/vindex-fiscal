# Pesquisa de documentos e exportação Excel

Abra **Documentos consolidados** (`/documentos/`). A busca aceita filtros combinados de empresa, tipo, CNPJ/nome do emitente, CNPJ do destinatário/tomador, número, série, chave, período de emissão, valor mínimo/máximo, situação informada e ambiente. Pesquise produtos/serviços por descrição ou código, combinando código exato, NCM e CFOP. A descrição e o nome do fornecedor ignoram maiúsculas/acentos na busca, preservando o texto original no resultado.

Quando um filtro de item é aplicado, todos os critérios precisam corresponder **ao mesmo item**. O documento aparece uma única vez, e os itens correspondentes mostram quantidade, unidade, valor unitário e valor declarado, somente quando presentes no XML. CT-e pode informar produto predominante da carga; isso não equivale a itens adquiridos e não gera quantidade/preço inferidos. Na NFS-e, a descrição do serviço e seu código nacional são extraídos do documento, sem inventar NCM/CFOP ou parcelas.

O botão **Exportar Excel** usa exatamente os mesmos filtros, sem limitar à página visível. O arquivo contém documentos, itens encontrados individualizados, agrupamento por fornecedor, por empresa, por mês e os critérios da consulta. Tipos e ambientes permanecem separados. Datas e valores são células tipadas; CNPJ, série, número e chave permanecem texto para preservar zeros e precisão. Texto vindo do documento nunca é executado como fórmula. Cabeçalhos, largura de colunas, linha congelada e filtros automáticos facilitam a leitura. Não há necessidade de instalar Excel no servidor.

Até 50 mil documentos e 150 mil itens por exportação. Acima disso, reduza o período ou selecione uma empresa; o sistema avisa sem entregar um arquivo incompleto. Os agrupamentos usam valores declarados dos documentos selecionados, inclusive cancelados/parciais se incluídos no filtro; não representam pagamentos. Campos ausentes ficam vazios na planilha.

O índice é uma projeção reconstruível, privada e vinculada ao documento de origem. Novas importações web, API e captura alimentam-no automaticamente na mesma transação. A busca consulta campos indexados/normalizados em vez de varrer XMLs. Na atualização de uma instalação existente:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py indexar_documentos
```

Faça backup antes de migrar. O build Linux já executa ambos os comandos. `indexar_documentos` retoma somente documentos sem índice; `--reconstruir` refaz a projeção local, sem reimportar, consultar o fisco ou modificar XML/NSU. Restauração por fixture precisa desta indexação posterior; snapshot SQLite preserva o índice existente.

Resumos/eventos continuam na captura, separados dos documentos completos. NFS-e parcial fica sinalizada. Cancelamento NF-e só é marcado a partir de evento de cancelamento aceito recebido para a própria empresa; ausência de evento não comprova autorização vigente. A supervisão master permite pesquisar/exportar em leitura no cliente da URL, com auditoria. O papel master não amplia a API nem a pesquisa do seu painel normal.

Tipos disponíveis: **NF-e 55, NFS-e nacional, CT-e 57**. NFC-e 65 não possui importação/captura nesta versão. O botão de PDF continua na área/detalhe de cada documento suportado; a pesquisa não cria XML ou PDF a partir de resumo.

Indicadores fiscais mantêm barras e linha SVG sem biblioteca adicional, agora com rosca/legenda, transições curtas, destaque por foco/mouse, informações dos pontos e links para os documentos de cada mês. Há comparação da quantidade com o período anterior de igual duração. A comparação avisa se o índice está incompleto. Movimentos respeitam `prefers-reduced-motion`; os valores exatos permanecem em tabela acessível e a soma entre naturezas fiscais diferentes continua separada.
