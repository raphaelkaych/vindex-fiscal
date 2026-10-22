# Bibliotecas de documentos auxiliares

## Logomarca NFS-e

`static/portal/nfse-logo-oficial.png` é o arquivo horizontal original publicado pelo Portal Nacional NFS-e, incorporado sem alteração de conteúdo, com proporção preservada na impressão. Fonte: [Logo — NFS-e — Horizontal](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/logos-da-nfs-e/Logo%20-%20NFS-e%20-%20Horizontal.png/view). O portal informa licença [Creative Commons Atribuição-SemDerivações 3.0 Não Adaptada](https://creativecommons.org/licenses/by-nd/3.0/deed.pt_BR). A marca identifica o documento nacional; seu uso não representa homologação do Vindex pelo governo.

A geração de DANFE e DACTE utiliza **BrazilFiscalReport 1.3.1**, de Engenere e seus contribuidores, sem modificar os arquivos da biblioteca. É instalada dinamicamente pelo pip e permanece substituível no ambiente Python.

- Projeto e código-fonte: https://github.com/Engenere/BrazilFiscalReport
- Distribuição: https://pypi.org/project/BrazilFiscalReport/1.3.1/
- Licença: GNU LGPL versão 3, disponível no [repositório original](https://github.com/Engenere/BrazilFiscalReport/blob/main/LICENSE) e na distribuição instalada.
- O mecanismo PDF é fpdf2, também distribuído com seus próprios avisos e licença: https://github.com/py-pdf/fpdf2

O projeto não incorpora cópia modificada dessas bibliotecas. O arquivo requirements.txt identifica a dependência utilizada; as licenças acompanham sua instalação. Para redistribuir um ambiente Python completo, preserve os avisos, licenças e as possibilidades de substituição/modificação das bibliotecas conforme suas licenças. O ZIP de código do Vindex não deve incluir .venv nem documentos de clientes.

O gerador de CT-e usa uma subclasse local para reservar a área branca do QR e preservar avisos nas páginas de continuação. O pacote BrazilFiscalReport instalado permanece sem alterações; a extensão não usa monkeypatch global.

pypdfium2 é dependência opcional de desenvolvimento para renderizar amostras fictícias de conferência. Seus avisos acompanham o pacote instalado; não é necessário para gerar ou baixar o DANFE no portal.


## Verificação de assinatura XML

SignXML **5.2.0**, licença Apache, é dependência instalada sem modificação para verificar a assinatura do XML original em casos de recuperação NFS-e. [Documentação e código oficial](https://xml-security.github.io/signxml/). SHA-1 é admitido explicitamente apenas na leitura de assinaturas legadas; isso não cria assinaturas novas nem valida cadeia ICP-Brasil/revogação. Preserve os avisos da distribuição.
