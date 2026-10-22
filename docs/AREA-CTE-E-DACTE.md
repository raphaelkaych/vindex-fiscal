# Transportes · CT-e e DACTE — 22/10/2026

## Acesso

No menu lateral, abra **Transportes · CT-e**, em `/cte/`. Os CT-e já importados pelo conector passam a aparecer nessa área automaticamente, sem copiar documentos ou reiniciar o histórico. A lista é exclusiva para CT-e do Workspace autenticado; produção é o filtro inicial.

Há busca por número/transportador/CNPJ/chave, empresa, ambiente, situação e período de emissão, com paginação e contagens dos filtros atuais. A tabela oferece **Abrir**, **XML** e **DACTE (PDF)**. NF-e e NFS-e continuam nas áreas próprias; Documentos consolidados continua disponível.

Nos detalhes aparecem transportador/emitente, remetente, destinatário, expedidor, recebedor e tomador conforme o XML, identificação, percurso/modal, valores da prestação, carga/quantidades, ICMS, IBS/CBS quando informado, dados específicos do modal, observações, autorização recebida e documentos vinculados com paginação. Carga/mercadorias e valor do frete são conceitos distintos. Valor a receber no XML não comprova pagamento.

O master usa a mesma área em `/gestao/clientes/<id>/painel/cte/`, em leitura e com auditoria. Downloads conferem Workspace e tipo antes de ler/gerar o arquivo. Não se troca o usuário autenticado nem se guarda cliente selecionado em sessão. A API comum não ganha novos acessos.

## DACTE e escolha do modelo

Foi reaproveitado o gerador BrazilFiscalReport já instalado. A estrutura segue a primeira referência apresentada: retrato quando indicado no XML, canhoto, transportador, identificação, chave de acesso/código de barras, QR Code, partes, carga, componentes do serviço, tributos, documentos originários e observações. O transportador é identificado pelos dados recebidos; não é inventado logo comercial nem usado o logo NFS-e no CT-e.

Referência oficial: [MOC CT-e 4.00 — Anexo II, especificações do DACTE](https://www.cte.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=yIxPYTwmPQM%3D). O PDF é gerado localmente a partir do XML, não baixado de um serviço de PDF governamental. Ele não substitui o XML, não consulta situação atual e não verifica assinatura/cadeia ICP-Brasil ou pagamento.

O fluxo suporta **CT-e completo modelo 57, versão 4.00**, já distribuído/importado. Não implementa CT-e OS modelo 67, emissão de CT-e ou nova importação manual pelo formulário de NF-e. O tipo e a orientação seguem o documento; a conferência desta entrega concentrou-se no modal rodoviário/retrato. Não foi declarada homologação universal de todos os modais, regimes ou contingências.

Antes de gerar, são conferidos XML seguro/XSD, identidade de 44 dígitos, modelo/versão, ambiente, protocolo e chave correspondente. Permanecem os limites de precisão monetária e de carga: se houver perda de precisão ou composição não suportada, é mostrado o erro e o XML permanece disponível. Documentos parciais não são promovidos a DACTE.

O QR usa o endereço existente no XML, com chave/ambiente correspondentes e domínio governamental. Se faltar ou divergir, o sistema não imprime um QR vazio ou inventa um endereço: informa a causa e mantém o original. Não há requisição externa durante a conversão.

## Correção de enquadramento do QR

A marca de homologação da biblioteca atravessava o QR na amostra e impedia sua decodificação. Foi criada uma subclasse local, por geração, sem modificar o pacote instalado nem fazer monkeypatch global:

- QR quadrado de 30 mm, centralizado na área original do cabeçalho;
- margem branca de quatro módulos;
- fundo branco reservado que protege os módulos da marca d'água;
- link de consulta correspondente ao XML;
- avisos de homologação/cancelamento mantidos e aplicados também às páginas de continuação.

O PDF pode ter mais de uma página quando há muitos documentos vinculados; não força uma página cortando referências. Os testes verificam a última chave de uma amostra com 120 referências e o aviso de cancelamento em todas as páginas.

## Conferência

- 38 testes iniciais de CT-e/NFS-e/conectores passaram, incluindo filtros, escopo, downloads, supervisão, mensagens de erro e DACTE.
- DACTE sintético renderizado em PNG e inspecionado visualmente; QR decodificado da página renderizada com ZXing, com endereço/chave/ambiente correspondentes.
- Seis CT-e reais existentes foram lidos em memória: seis PDFs gerados, seis chaves presentes no PDF e seis QRs decodificados da página. Nenhum documento real foi salvo para a conferência, alterado ou incluído no repositório.
- Lista e detalhes renderizados sobre dados locais por requisição autenticada em memória: HTTP 200 e `no-store`, sem criar sessão no banco.
- Sem nova consulta fiscal, manifestação, mudança de cursor/intervalo, renovação de A1 ou migração de dados. A captura em funcionamento permanece independente dessa área.
- `manage.py check`: sem problemas; `makemigrations --check --dry-run`: sem mudanças.
- A ferramenta de navegador desta sessão estava indisponível na conferência anterior. Estas telas reutilizam componentes/tokens e regras responsivas de NFS-e, mas a inspeção visual interativa em celular/tablet/desktop permanece pendente. A inspeção visual dos PDFs foi realizada por renderização local.
- Suíte completa `py iniciar.py --testar`: **386 testes em 171,209 s, OK; 383 executados/aprovados e 3 de PostgreSQL ignorados** pela ausência do ambiente de homologação. Depois do ajuste pontual para listar todas as chaves complementadas, os **12 testes específicos de CT-e** passaram novamente. O log completo fica em `tmp/testes-area-cte.log` e não é publicado.

## Usar no Windows

```powershell
py iniciar.py
```

Abra `http://127.0.0.1:8000/cte/`, entre na conta e use **Abrir**, **XML** ou **DACTE (PDF)**. Se o portal já estiver aberto, atualize com `Ctrl+F5`. Se o servidor web estiver sem recarga automática, é necessário recarregá-lo para carregar o novo código. Não é necessário reiniciar o worker para esta entrega.

Para testar:

```powershell
py iniciar.py --testar
```

O comando opcional `python tools/check_dacte_pdf.py` gera somente uma amostra fictícia em `tmp/pdfs/`, usando a dependência de desenvolvimento PDFium. A fixture de renderização substitui o XSD apenas nesse diagnóstico; não representa consulta ou homologação fiscal. Nenhum documento real é incorporado ao teste.

## NFS-e incluída nesta atualização

Também seguem nesta entrega os ajustes anteriores de NFS-e: logo horizontal oficial preservado, cabeçalho, QR centralizado em coluna própria com legenda, avisos mantidos e conferência de leitura. Veja [Área de NFS-e e PDF](AREA-NFSE-E-PDF.md) e [atribuições de terceiros](TERCEIROS.md). São alterações de código/assets/documentação; banco, certificados, XMLs reais e segredos ficam fora do GitHub.
