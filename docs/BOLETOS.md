# Boletos locais no Vindex Fiscal

Entrega verificada em **20/10/2026**. Importação e revisão locais disponíveis; **DDA/banco não conectado**. Não houve teste com boleto, conta bancária, certificado ou pagador real.

## Diagnóstico e fontes consultadas antes da implementação

A base possuía previsões de parcelas extraídas de XML, sem modelo de boleto, arquivo PDF privado, parser de códigos ou conector DDA. O módulo acrescenta documentos de cobrança independentes e vínculos explícitos às parcelas já existentes.

| Tema | Evidência oficial | Decisão no Vindex |
|---|---|---|
| Cobrança: barras, linha e DVs | [CAIXA: especificações técnicas SIGCB](https://www.caixa.gov.br/Downloads/cobranca-caixa/ESP_COD_BARRAS_SIGCB_COBRANCA_CAIXA.pdf) | Reconhecer barras de 44 posições e linha de 47; conferir módulos 10 dos campos e 11 do DV geral. |
| Vencimento após o reinício do fator | [Banco do Brasil: especificações técnicas, Anexo IV](https://www.bb.com.br/docs/pub/emp/empl/dwn/Doc5175Bloqueto.pdf) | O fator 1000 corresponde a 03/07/2000 no ciclo antigo e 22/02/2025 no novo; preservar candidatos, exigir data declarada e não escolher pelo dia da importação. |
| Arrecadação vigente | [FEBRABAN: layouts](https://portal.febraban.org.br/pagina/3425/33/pt-br/layout-febraban) e [layout v8, vigente desde 01/06/2026](https://cmsarquivos.febraban.org.br/Arquivos/documentos/PDF/Layout%20-%20C%C3%B3digo%20de%20Barras%20-%20Vers%C3%A3o%208%20-%2011_05_2026.pdf) | Barras de 44/linha de 48; módulo definido pelo indicador. Indicadores 7/9 expressam referência, sem conversão automática em reais. Não inferir vencimento do campo livre sem o layout específico do emissor. |
| Leitura de PDF | [pypdf: extração de texto](https://pypdf.readthedocs.io/en/stable/user/extract-text.html) e [robustez](https://pypdf.readthedocs.io/en/stable/user/robustness.html) | Leitura de texto digital com limites. Não há camada semântica universal; rótulos ambíguos e scans exigem revisão. pypdf não é OCR. |
| DDA do pagador | [BCB: cadastro no DDA](https://www.bcb.gov.br/meubc/faqs/p/cadastro-no-dda-para-utilizacao-do-boleto-de-pagamento-eletronico) | Cadastro depende de instituição de relacionamento que ofereça o serviço. A1/XML não substituem adesão ou autorização bancária. |
| Disponibilidade de API DDA e cobertura | [BB: Débito Direto Autorizado](https://www.bb.com.br/site/pra-voce/contas/todos-os-produtos-e-servicos/debito-direto-autorizado/) e [CAIXA: DDA](https://www.caixa.gov.br/poder-publico/modernizacao-gestao/dda/Paginas/default.aspx) | A página BB menciona visualização por API após adesão. Não foi implementado endpoint de fornecedor: ainda faltam contratação, credenciais, especificação técnica, limites, custos e homologação. Tributos e serviços públicos têm cobertura distinta. |
| APIs do beneficiário | [CAIXA: webservice de cobrança](https://www.caixa.gov.br/Downloads/cobranca-caixa/WEBSERVICE-XML-COBRANCA-BANCARIA.pdf) | Registro/consulta de cobranças emitidas pelo beneficiário não provam consulta universal de títulos emitidos por terceiros contra o pagador. |

As fontes estão publicamente disponíveis em URLs oficiais. Alguns manuais de cobrança têm edição antiga; foram usados somente para o formato neles descrito, junto ao manual BB acessível na consulta para o reinício do fator. A arrecadação foi implementada com o layout v8 de 2026. A página de layouts teve falha transitória de acesso; o PDF oficial v8 foi acessível. Não foi presumida homologação bancária a partir desses documentos.

## Como usar

1. Cadastre o CNPJ pagador em **Minhas empresas**.
2. Abra **Boletos → Importar boleto**.
3. Selecione a empresa e envie PDF de até 5 MB ou informe linha digitável/código de barras.
4. Abra **Revisar dados** para completar os campos encontrados no documento. Os documentos permanecem privados.
5. Use **Associar parcela** somente após conferir nota, identificadores e obrigação correspondente. Se faltar a parcela, complete as previsões no fluxo da nota antes de vincular o boleto.

O formulário aceita dados do beneficiário, CPF/CNPJ, pagador, CNPJ pagador, identificação, valor e vencimento declarados. Quando informado, o CNPJ pagador deve coincidir exatamente com o CNPJ selecionado. CNPJ alfanumérico e CPF passam por validação dos dígitos; nenhum CPF de pagador pode ser usado no lugar de uma empresa CNPJ.

Não existe ação para pagar, agendar, baixar ou confirmar liquidação nesta entrega. O estado financeiro do boleto é sempre **pagamento não consultado**. Texto “pago”, vencimento passado, conferência e vínculo não o alteram. O painel soma as parcelas; boletos são documentos vinculáveis e não criam outra obrigação.

## Precisão e revisão

- Somente cobrança bancária em reais (moeda 9) e os segmentos conhecidos de arrecadação são reconhecidos. Códigos não suportados ou com DV inválido são rejeitados.
- Cobrança: cada um dos três DVs da linha e o DV geral das barras são conferidos. Arrecadação: os quatro blocos e o DV geral são conferidos, com módulos distintos conforme indicador.
- A validação informa **Dígitos conferidos**; isso não consulta registro, beneficiário real, autenticidade, cancelamento ou liquidação em uma base bancária.
- Valores usam `Decimal` com centavos, sem arredondamento silencioso. Na cobrança bancária, o trecho usual de dez posições é somente um **candidato**, exibido no aviso: o campo `amount` fica vazio até existir valor explícito no formulário/API ou rótulo do PDF. Isso também se aplica quando o fator parece válido e a data está preenchida, pois valores altos podem ocupar essa área. Valor declarado divergente do candidato é preservado e sinalizado. Valores não finitos, não positivos, `float` ou com mais de duas casas são rejeitados pelo serviço.
- Fator de cobrança 1000–9999 mantém candidatos dos dois ciclos. Uma data explícita compatível resolve a ambiguidade local; uma data divergente permanece sinalizada. Fator zero/especial não fornece data ou valor automaticamente: valores superiores a dez posições podem ocupar a área do fator. Essa modalidade especial precisa de informação explícita e conferência com o emissor.
- Arrecadação: indicadores 6/8 podem declarar valor efetivo; 7/9 não são tratados como reais automaticamente. Não há interpretação universal segura de vencimento no campo livre. Informe-o a partir do documento.
- PDF: a linha/código é procurada apenas em sequências reconhecidas. Se houver múltiplas cobranças, nenhuma é escolhida automaticamente. É possível indicar o código explícito ao importar.
- Nome, CPF/CNPJ, valor, vencimento e identificação do PDF só são extraídos de rótulos explícitos na mesma linha, sem inferência de colunas. Campos ausentes/inválidos ficam em revisão. Nome do banco não é adivinhado; o código de compensação é obtido da cobrança quando aplicável.
- PDFs sem texto são guardados para revisão manual. **Não há OCR instalado ou executado**; a tela informa esse limite. PDFs com camada OCR pré-existente podem conter erros, por isso a revisão visual continua necessária.

## Privacidade, limites e duplicidade

O PDF original fica no banco em `BinaryField`, sem URL de mídia pública. Downloads exigem sessão/API autorizada, com Workspace e empresa conferidos no servidor, `attachment`, `nosniff` e cache privado sem armazenamento. Nenhum certificado é usado pelo módulo.

Limites: 5 MB por PDF, 1–10 páginas, 1 MB de conteúdo descomprimido por stream/página, orçamento de parsing e de decodificação, profundidade de árvore e limite de chamadas de formulários internos. Os limites da biblioteca são aplicados por contexto antes da descompressão. PDFs criptografados, inválidos ou excessivos são rejeitados com mensagem sem detalhes privados do parser. Em produção, complemente com limites de upload/tempo/processo no servidor; o parser local não equivale a uma sandbox de documentos.

Há índices únicos para **empresa + código de barras normalizado** e **empresa + SHA-256 do PDF**. Repetir a mesma importação retorna o registro existente, sem criar parcelas. Se os dados estruturados conflitarem com o registro, é necessário usar a revisão auditada. Se código e hash apontarem para registros distintos, a importação é bloqueada para revisão. Reimportação não substitui o PDF original; um PDF pode ser anexado quando o registro ainda não tem arquivo.

Um boleto vincula uma parcela; uma parcela aceita um boleto. Vínculos entre CNPJs ou Workspaces diferentes são bloqueados. Divergências de valor, vencimento ou beneficiário/dados não confirmados exigem justificativa explícita com pelo menos 10 caracteres. Beneficiário diferente do fornecedor pode representar cessão/intermediário: o sistema registra essa análise e não conclui fraude ou equivalência automática. Desfazer o vínculo preserva nota, parcela, PDF e histórico. Uma revisão que faria o boleto divergir da parcela exige desfazer o vínculo e confirmar novamente.

`BoletoEvent` e a auditoria geral registram importação, anexação, revisão e associação/desassociação, com origem, identificação interna do ator e alterações. Os avisos anteriores e posteriores ficam no evento de revisão; incertezas da extração do PDF original, como múltiplos códigos e campos inválidos, continuam sinalizadas após mudanças de nome ou outros campos. Não há remoção de eventos pela interface/API. É auditoria de aplicação, não armazenamento inviolável contra administradores de banco.

## Contrato dos serviços

`portal/services/boletos.py` concentra as regras reutilizadas por telas e API:

```python
import_boleto(workspace, data, payload=None, allowed_companies=None, actor=None)
# -> (boleto, created). data['company']: objeto Company ou ID autorizado.
# data: barcode/digitable_line, amount, due_on, beneficiary_name/document,
# payer_name/document, reference; source: manual, pdf ou api.

update_boleto(workspace, boleto, data, actor=None, source='manual', allowed_companies=None)
associate_boleto(workspace, boleto, installment, actor=None, source='manual',
                 allowed_companies=None, review_reason='')
disassociate_boleto(workspace, boleto, actor=None, source='manual', allowed_companies=None)
```

`allowed_companies=None` libera todas as empresas **daquele Workspace**; lista vazia não libera empresa alguma. As funções revalidam o escopo de objetos recebidos, relações e pagador. `BoletoImportError`/`BoletoAssociationError` representam erros de negócio. Os campos internos de validação, origem derivada, hash e arquivo não são aceitos como prova bancária do consumidor. A documentação API do projeto descreve as rotas REST efetivamente publicadas.

`UnconfiguredDDAConnector.fetch(company)` sempre lança `DDAConnectorUnavailable`, explicando requisitos; não envia requisição nem produz trabalho/captura fictícia. Um futuro conector precisará separar consulta do pagador de cobrança do beneficiário e verificar dados entregues, PDFs, situação, cobertura, consentimento, contrato, custos e retenção antes de ativação. A importação local funciona sem contratar fornecedor.

## Instalação e verificação no Windows

Na pasta do projeto:

```powershell
py iniciar.py --preparar
py iniciar.py --testar
py iniciar.py
```

O primeiro comando instala as versões de `requirements.txt` (incluindo `pypdf==6.21.1`) e aplica migrações. O segundo usa banco temporário de testes. O terceiro inicia o sistema local. Nenhum comando contrata banco/provedor ou realiza pagamento.

Para rodar apenas os testes do módulo depois de preparar:

```powershell
.\.venv\Scripts\python.exe manage.py test portal.test_boletos --noinput
```

Os testes usam apenas códigos arbitrários e PDFs fictícios em memória, identificados como sem valor bancário/fiscal. Cobrem formatos/DVs, mudança do fator, ambiguidade, arrecadação por valor/referência, limites PDF, arquivo ilegível, duplicidade, precisão, divergências, vínculo sem nova obrigação, auditoria e acesso entre clientes. Aprovação sintética não comprova leitura de todos os layouts bancários, autenticidade de boleto ou homologação DDA.
