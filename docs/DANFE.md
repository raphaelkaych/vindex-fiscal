# XML e DANFE

CT-e modelo 57 oferece **DACTE (PDF)** em seus detalhes. NFS-e oferece **PDF de conferência**, gerado localmente do XML validado, com valores literais e indicação de cancelamento recebido/homologação. Está disponível também na supervisão master. Não é apresentado como DANFSe oficial: o modelo v2.0 da NT 008 ainda depende de implementação/homologação. O XML original permanece disponível. Veja [conectores e limites](MASTER-E-CONECTORES.md).

Na lista **Notas** e nos detalhes de uma nota, **XML** baixa o conteúdo original e **DANFE (PDF)** gera sua representação auxiliar. O serviço de distribuição SEFAZ entrega XMLs; este PDF é produzido localmente pelo Vindex, não é o arquivo gráfico original do fornecedor.

A geração exige NF-e modelo 55 completa, destinatário e chave correspondentes, protocolo de autorização e dados suficientes para impressão A4. Resumos, eventos, XMLs incompletos ou valores que não podem ser preservados com precisão não geram PDF. O motivo aparece na nota; o XML original permanece disponível. A geração não consulta situação fiscal atual, não confirma pagamento e não envia manifestação.

O layout usa BrazilFiscalReport 1.3.1, com código de barras, chave, emitente, destinatário, protocolo, produtos, totais e duplicatas existentes no XML. Respeita orientação retrato/paisagem e paginação. Exemplos fictícios recebem identificação em todas as páginas. A ausência de dados não autoriza inventar condições de cobrança.

O download exige login e acesso ao Workspace da empresa; o servidor gera o PDF em memória, sem publicar arquivo nem certificado. O PDF não substitui a guarda do XML. O processo não valida a assinatura do XML importado manualmente nem comprova a situação atual na SEFAZ.

## Verificação

Os testes cobrem autorização, isolamento, XML incompleto/malicioso, fidelidade dos valores, protocolo, múltiplas páginas, paisagem, homologação e preservação do XML. A conferência visual usa somente amostras fictícias:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe tools/check_danfe_pdf.py
```

Esses comandos opcionais instalam o renderizador de conferência e criam imagens sintéticas em `tmp/pdfs/`. Para o uso normal, basta `py iniciar.py`; a biblioteca de geração é instalada pelo inicializador.

Referências: [Portal NF-e — MOC 7, Anexo II: DANFE e código de barras](https://www.nfe.fazenda.gov.br/PORTAl/exibirArquivo.aspx?conteudo=f+NhsSn3%2F5M%3D), [documentação do gerador](https://engenere.github.io/BrazilFiscalReport/pt/danfe/) e [avisos de terceiros](TERCEIROS.md).
