# Área de NFS-e e PDF local — 22/10/2026

## Como acessar

No menu lateral, abra **Notas de serviço · NFS-e** (`/nfse/`). A área lista exclusivamente NFS-e importadas no Workspace autenticado, com produção selecionada por padrão. Não mistura NF-e de produtos e CT-e. Documentos consolidados e a área de NF-e continuam disponíveis.

Há busca por número/prestador/CNPJ/chave, empresa, ambiente, situação e datas de emissão; paginação; contagens dos resultados e ações **Abrir**, **XML** e **PDF**. Datas inválidas ou empresa fora do escopo não exibem documentos. O histórico de vínculos desativados continua consultável.

Nos detalhes há prestador, tomador, destinatário e intermediário, identificação/DPS, descrição do serviço, tributos e valores presentes no XML, informações complementares, evidências financeiras já extraídas e consulta pública pela chave. Valores ausentes não viram zero. Schema validado não equivale a assinatura verificada ou situação fiscal atual confirmada.

O master acessa a mesma área em `/gestao/clientes/<id>/painel/nfse/`, sempre com escopo na URL, em leitura e com auditoria. A permissão master não amplia os downloads normais de outro Workspace.

## PDF

O gerador foi reorganizado em uma página A4, com cabeçalho, chave de 50 dígitos, QR Code clicável para a consulta pública, blocos de partes, serviço, tributação municipal/federal, valores, IBS/CBS presentes e informações complementares. Emissão/data e dinheiro têm formatação brasileira. Não é feita consulta externa para gerar o arquivo.

Referência: [NT 008 v1.02, DANFSe](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/rtc/nt-008-se-cgnfse-danfse-20260714-v1-02.pdf). A implementação é **baseada** no modelo nacional; não foi declarada homologação ou equivalência integral com todos os detalhes da NT. O cabeçalho incorpora o logo horizontal original do Portal Nacional, com proporção preservada e atribuição em [Terceiros](TERCEIROS.md). Alguns códigos permanecem identificados como códigos e localidades como IBGE; IBS/CBS é apresentado com os caminhos dos dados recebidos. No Windows usa Arial/Microsoft Sans Serif disponíveis no sistema; em outros sistemas há fallback Helvetica, sem distribuir fontes proprietárias. Esses pontos exigem evolução antes de anunciar conformidade integral ao leiaute oficial.

O arquivo é identificado como **DANFSe gerado pelo Vindex** para documentos com schema validado. Não é um PDF baixado do governo e não verifica assinatura, cadeia ICP-Brasil ou pagamento. Cancelamento/substituição aparecem apenas quando informados pelos eventos já recebidos. O estado remoto pode ter mudado desde a última captura.

Documentos **parciais** mantêm **PDF de conferência**, com alerta de estrutura/assinatura; nunca são promovidos a documentos validados por gerar PDF. Homologação tem aviso de ausência de validade jurídica. Um PDF oficial previamente recuperado por adaptador continua sendo usado quando disponível; nenhum novo adaptador/serviço de PDF oficial foi habilitado.

Campos extensos são abreviados visualmente com reticências para manter a página legível; a tela e o XML preservam o conteúdo disponível integral. Composição não suportada ou falha de representação retorna mensagem compreensível e mantém o XML disponível. As entradas XML são verificadas antes de gerar o PDF, incluindo versão, schema/perfil compatível e correspondência da chave.

## Operação e preservação

Não há migração de banco ou nova dependência nesta entrega. Nenhum certificado, consentimento, cursor, intervalo ou estado de captura foi alterado por este desenvolvimento. Não foram executadas consultas fiscais ou manifestações; apenas leituras locais para conferência. O worker não precisa ser reiniciado por esta alteração de telas/PDF.

No Windows:

```powershell
py iniciar.py
```

Abra `http://127.0.0.1:8000/nfse/`. Se o servidor já estiver aberto, atualize a página e use `Ctrl+F5` para renovar o CSS. Caso seja executado sem recarga automática, reinicie somente o servidor web conforme o modo de implantação.

## Verificação

- Testes de escopo de listagem, filtros, datas, ambientes, paginação, downloads XML/PDF, bloqueio de outro cliente/tipo, detalhes, supervisão URL/auditoria e bloqueio de POST no master.
- Testes de PDF: página única A4, chave/valor, URL do QR, descrições longas, ausência de valores fictícios, quatro partes, substituição, homologação, parciais e preservação do XML.
- PDFs sintéticos normal/parcial renderizados com PDFium e inspecionados em PNG. Nenhum PDF real foi salvo em arquivo para essa conferência.
- Conferência em memória de 6 NFS-e com schema validado e 13 parciais já armazenadas: 19 PDFs gerados em uma página e chave correspondente; originais intactos em memória, sem escrita de XML ou chamada fiscal.
- `manage.py check` e `makemigrations --check --dry-run`: sem problemas/sem mudanças de modelo.
- Conferência visual no navegador não realizada: a ferramenta retornou nenhum navegador habilitado e `Browser is not available: iab`. Responsividade e temas usam os tokens existentes e regras para três/duas/uma coluna, mas ainda exigem inspeção visual em navegador real.
- Suíte completa `py iniciar.py --testar`: **375 testes em 170,352 s, OK; 372 executados/aprovados e 3 de PostgreSQL ignorados** por ausência do ambiente de homologação correspondente. Log local: `tmp/testes-area-nfse.log`.
- Lista e detalhes também renderizados sobre os dados locais por RequestFactory autenticado, sem criar sessão no banco: ambos HTTP 200 e `Cache-Control` com `no-store`.

Os arquivos de prévia e diagnósticos estão em `tmp/`, ignorado pelo Git. Não fazem parte do código distribuído. A captura existente continua separada da geração do PDF; esta entrega não resolve nem modifica a rejeição NF-e 656.

## Refinamento do cabeçalho e QR

O logo oficial horizontal é incorporado localmente, sem requisições durante o download do PDF. O cabeçalho passa a ter identificação do município, ambiente gerador informado no XML e aviso de homologação centralizado. O QR tem coluna reservada de 51 x 34 mm, imagem quadrada de 22 mm com margem branca de quatro módulos, centralização horizontal e legenda em área separada. Os campos de identificação usam as três colunas à esquerda e não atravessam o QR. O layout continua em uma página e os avisos de parciais/cancelamento/substituição são preservados.

Foram renderizadas amostras sintéticas normal e parcial e os QRs foram decodificados com ZXing a partir do PNG da página (não apenas do arquivo QR original), ambos apontando para a chave correta. O decodificador foi instalado somente em `tmp/qr-checker` para conferência; não é dependência da aplicação nem é distribuído. Os testes também verificam imagem do logo/QR incorporadas, proporção quadrada, dimensão mínima e legenda presente.

Após esse refinamento, os 14 testes de área NFS-e/PDF/PDF oficial passaram. Foram novamente conferidos em memória os mesmos 6 documentos com schema validado e 13 parciais, todos em uma página e sem alterar o XML. A suíte completa de 375 testes acima é a verificação da entrega anterior; não foi repetida por este ajuste de composição. O servidor web local foi recarregado para aplicar o gerador; o processo de captura não foi reiniciado.
