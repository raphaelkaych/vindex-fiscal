# Diagnóstico e matriz funcional — Vindex Fiscal

Atualizado em **21/10/2026**. O Vindex possui conector próprio de distribuição SEFAZ, worker de leitura, autorizações por empresa e importação dos XMLs completos recebidos. Houve consulta piloto real e importação de XML; o resultado e os limites estão em [INTEGRACAO-SEFAZ.md](../INTEGRACAO-SEFAZ.md). A plataforma permanece independente da Qive. DDA e operações bancárias continuam sem integração.

A pesquisa e a matriz de decisão abaixo preservam o diagnóstico histórico de **20/10/2026**, anterior às implementações. Naquela etapa não havia ocorrido consulta fiscal real. Elas não descrevem o estado atual do conector; a atualização funcional está no final deste documento.

## Diagnóstico inicial confirmado — histórico de 20/10/2026

Foram lidos `AGENTS.md`, `LEIA-ME.md`, `IDENTIDADE-VISUAL.md`, `INTEGRACAO-SEFAZ.md`, modelos, serviços, rotas, configurações e testes existentes.

- Django 5.2; um proprietário por Workspace; empresas únicas por `(workspace, cnpj)`. As telas, arquivos XML e exportações consultam o Workspace do usuário. Não há gestão de vários usuários no mesmo cliente.
- NF-e modelo 55 completa por upload, chave única por empresa, XML privado no banco e leitura segura com `defusedxml`. O importador não verifica assinatura digital, cadeia ICP-Brasil nem situação fiscal atual. Resumos, eventos, NFS-e e CT-e são rejeitados.
- Duplicatas vêm de `cobr/dup`; falta de vencimento ou de duplicatas gera revisão. As parcelas são previsões; `checked` registra conferência. Não há liquidação bancária. O identificador de uma duplicata sem `nDup` recebia sequência interna; deve ser identificado como identificador local, nunca número declarado pelo fornecedor.
- Certificado A1 e senha cifrados com Fernet; validade e raiz de CNPJ conferidas localmente. A empresa mantém o histórico quando o certificado é renovado/removido. Não há verificação de cadeia/revogação ou acesso governamental.
- Filtros, paginação de telas, agenda, auditoria textual, dados fictícios explicitamente identificados, exportação CSV e tema claro/escuro já existem.
- API REST, boletos, anexos PDF, OCR, DDA, captura SEFAZ, estado de NSU, worker e eventos fiscais estavam ausentes.
- Produção: cookies seguros e redirecionamento HTTPS quando `DEBUG=False`; limites em cache local; banco configurado como SQLite. PostgreSQL, servidor de produção, cache compartilhado e observabilidade exigem configuração adicional. Nenhum segredo ou banco real foi inspecionado neste diagnóstico.

Evidências locais principais: `portal/models.py`, `portal/services/invoices.py`, `portal/services/certificates.py`, `portal/views.py`, `portal/urls.py`, `portal/tests.py` e `config/settings.py`.

## Fontes oficiais e acesso — registro da pesquisa de 20/10/2026

| Código | Fonte consultada | Resultado e limite |
|---|---|---|
| Q1 | [Portal Qive](https://developers.qive.com.br/) e [operação inicial solicitada](https://developers.qive.com.br/docs/post/v2/dfe/nfe) | HTML depende de JavaScript; a variável pública `NEXT_PUBLIC_API_URL` do próprio portal aponta para Q2. |
| Q2 | [Swagger oficial carregado pelo portal atual](https://docs.arquivei.com.br/arquivei-apis-swagger/dfe-api.json) | Acessível sem credenciais; Swagger 2.0, `info.version=1.106.0`, título Qive API. O domínio histórico Arquivei foi aceito porque é referenciado pelo portal Qive atual. Não prova disponibilidade contratual nem resposta real. |
| Q3 | [Plataforma Qive — Boletos](https://qive.com.br/solucoes/por-documento/boletos) | Página comercial anuncia DDA pela Núclea, associação documental, histórico e comprovantes quando disponíveis. A página diz que a plataforma gerencia documentos e não executa pagamentos. Somente Q2 comprova operações públicas. |
| S1 | [Portal NF-e — Notas Técnicas](https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=04BIflQt1aY%3D) | Índice oficial consultado informa NT 2014.002 v1.40, publicada em 03/07/2026, e NT 2020.001 v1.60, publicada em 23/04/2026. O navegador textual apresentou redirecionamento; uma sessão HTTP com cookies permitiu consultar os documentos públicos sem autenticação. |
| S2 | [NT 2014.002 v1.40 oficial](https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=uWO2d%2FgTuWg%3D) | PDF integral obtido e lido: 18 páginas, versão julho/2026, implantação em 08/07/2026. Confirma CNPJ alfanumérico, limite de 50 documentos, NSU facultativo por documento, regras de espera e limites de histórico. Não representa teste do serviço. |
| S3 | [NT 2020.001 v1.60 — manifestação](https://www.nfe.fazenda.gov.br/Portal/exibirArquivo.aspx?conteudo=%2BWTd7iuD21s%3D) | Conteúdo oficial indexado informa implantação em produção em 01/06/2026 e alteração para 90 dias das manifestações conclusivas pelo Ajuste SINIEF 14/26. Ciência é distinta de confirmação. Acesso direto ao PDF apresentou redirecionamento; não usar FAQs antigas como regra de prazo atual. |
| S4 | [Portal NF-e — distribuição e consumo indevido (material anterior)](https://www.nfe.fazenda.gov.br/Portal/exibirArquivo.aspx?conteudo=U0LlsYVGBRU%3D) | Explica NSU sequencial, espera de uma hora após falta de documentos e rejeição 656. É material anterior à v1.40: referência de desenho, não certificação da regra vigente. |
| S5 | [Schema oficial Distribuição DF-e v1.04](https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=IzuP2y0G6hk%3D) | ZIP oficial obtido sem extrair arquivos ao projeto. Contém `distDFeInt_v1.01.xsd`, `retDistDFeInt_v1.01.xsd`, `resNFe_v1.01.xsd`, `resEvento_v1.01.xsd` e tipos. O atributo `docZip/@NSU` é opcional; o cursor de retorno é distinto. |
| S6 | [Serviços de produção](https://www.nfe.fazenda.gov.br/portal/webServices.aspx) e [homologação](https://hom.nfe.fazenda.gov.br/portal/webServices.aspx) | Endereços atuais verificados nas listas oficiais. GET de metadados WSDL encontrou erro de confiança da cadeia TLS no ambiente local; a verificação TLS não foi desativada. Nenhuma requisição de distribuição foi enviada. |
| D1 | [Núclea — DDA](https://www.nuclea.com.br/dda/) | Descreve adesão por instituição financeira do pagador e apresentação de boletos; pagamento depende de autorização própria. Não fornece credenciais nem contrato de API para o Vindex. |
| D2 | [Núclea — Plataforma Centralizada de Recebíveis](https://www.nuclea.com.br/plataforma-centralizada-de-recebiveis/) | Explica adesão e operação por instituições financeiras. Não demonstra acesso universal a todos os boletos somente com A1. |

## Operações Qive efetivamente encontradas

Resumo de Q2: `POST /v2/dfe/nfe` **consulta**, não emite. Aceita `Filters`, `Fields`, `Limit` (máximo 500) e `Paginator`; filtros incluem proprietários/papéis, datas, emitente, destinatário, situação, origem e etiquetas. XML/metadados são separados de `GET /v1/nfe/danfe` (PDF base64). Eventos: `GET /v2/nfe/events`; manifestação: `POST /v1/nfe/manifest`, consulta de andamento e variante síncrona. Etiquetas: `/v1/account/tags/list`, `/v1/dfe/tags/list`, `/v1/dfe/tags/update`; propriedades: `/v1/property`. Empresas: `GET /v1/company`.

Boletos: `GET /v1/bank-billet`, `POST /v2/bank-billet/search`, `GET /v1/bank-billet/{owner}/{digitableLine}/pdf`. Há filtros, cursor e vínculos documentais. `POST /v1/receipts/list` distingue origem `manual`/`automatico`. Também estão documentados NFS-e, CT-e, CT-e OS, NFC-e, MDF-e, OCR, utilities e documentos LATAM, cada um com operações próprias.

Essas operações são referências funcionais; o Vindex não as consome nesta entrega. Filtros com vários CNPJs demonstram capacidade técnica, enquanto permissões, plano, cobertura, custos, retenção e ativação DDA precisam de confirmação contratual e teste autenticado.

## Matriz de decisão

P0 = essencial nesta evolução local; P1 = próxima entrega sujeita a validação; P2 = expansão. O estado nesta tabela é anterior à implementação. A documentação de uso registra o que foi efetivamente entregue depois.

| Funcionalidade | Evidência/URL | Dados necessários | Estado inicial no Vindex | Implementação própria possível | Dependência externa | Complexidade | Prioridade |
|---|---|---|---|---|---|---|---|
| Cliente e múltiplos CNPJs | Código local; Q2 empresas/proprietários | Usuário, Workspace, CNPJ validado | Disponível nas telas | Reutilizar escopo em API e serviços | Nenhuma para cadastro local | Média | P0 |
| Consulta, filtros, paginação | Código local; Q2 consulta | Empresas permitidas, período, emitente e origem | Parcial nas telas | API versionada, filtros permitidos e paginação | Nenhuma | Média | P0 |
| XML privado e importação idempotente | Código local; Q2 XML/upload | XML completo, destinatário, chave | Disponível via telas | Reusar importador e autorizar downloads na API | Origem/autenticidade atual exigem consulta específica | Média | P0 |
| DANFE/PDF fiscal | Q2 DANFE | XML completo válido e renderizador | Ausente | Futuro renderizador próprio com revisão de leiaute | Biblioteca/serviço adequado; não chamar XML de PDF | Alta | P2 |
| Dados de cobrança e pagamento declarado | Código local; XML NF-e | `cobr/fat`, `dup`, `pag/detPag` e origem | Leitura parcial de duplicatas e forma | Preservar declaração e revisão sem inferir quitação | Nenhuma para leitura local | Média | P0 |
| Completar/conferir previsão | Código local | Valor, data informada, responsável, motivo | Apenas conferência simples | Serviço de revisão auditado e escopo por empresa | Nenhuma | Média | P0 |
| PDF/dados de boleto privados | Q3 referência funcional; D1 | Arquivo/dados, pagador, valor, identificadores | Ausente | Texto digital, formulário, hash e armazenamento privado | Extrator de PDF; OCR opcional | Alta | P0 |
| DV, linha e código de barras | Padrão bancário aplicável, a verificar separadamente | Formato, dígitos e campos codificados | Ausente | Validação local por formato; revisão quando não suportado | Manual oficial atual; banco para autenticidade | Alta | P0 |
| Vencimento por fator | Padrão bancário atual, a verificar separadamente | Fator, data explícita e contexto | Ausente | Preservar ambiguidade do ciclo; não escolher data arbitrária | Regra vigente oficial e confirmação documental | Alta | P0 |
| Boleto vinculado à nota/parcela | Q3; código local | Empresa comum, identificadores, valor, vencimento | Ausente | Associação explícita, sugestões e divergências; somar obrigação uma vez | Nenhuma para associação local | Alta | P0 |
| Histórico e revisão | Código local; Q3 | Autor, origem, objeto e alteração | Auditoria textual parcial | Registrar importação, associação e baixa manual | Nenhuma | Média | P0 |
| Comprovante, baixa manual e liquidação | Q3; D1 | Anexo/origem/data/evidência do estado | Ausente | Estados separados; baixa manual não é confirmação bancária | Fonte bancária confiável para confirmação externa | Alta | P0/P1 |
| Consulta DDA recebida | D1, D2, Q3; Q2 boleto | Adesão pagador, autorização, contrato e credenciais | Ausente | Interface de conector explicitamente não configurado | Banco/fornecedor autorizado; custos/cobertura não confirmados | Alta | P1 |
| Distribuição SEFAZ por CNPJ | S1, S2; S4 histórico | A1 autorizado, ambiente, UF, CNPJ, NSU | Ausente | Começar por estado local, parser e protocolo de transporte | NT/schema vigentes, mTLS, autorização e homologação real | Alta | P1 |
| NSU, concorrência e retentativas | S2, S5 | Último NSU, resposta, prazo e trava por CNPJ | Ausente | Persistência, execução única e espera; falhas verdadeiras | Worker para rotina; coordenação com outros consumidores e homologação | Alta | P1 |
| Resumos, XML completo, eventos | S1/S2 | Schema, NSU, conteúdo descompactado, chave | Somente XML completo | Pipeline com classificação; rejeitar tipo desconhecido | Distribuição oficial para recebimento real | Alta | P1 |
| Cancelamentos e situação fiscal | Q2 eventos; S1 | Evento/protocolo com origem e validade | Ausente | Modelo próprio de eventos e efeitos locais auditados | Fonte oficial para situação atual; não inferir do vencimento | Alta | P1 |
| Manifestação do destinatário | S3; Q2 manifestação | Evento escolhido, autorização, certificado e justificativa | Ausente | Planejar ação explícita com autorização e idempotência | Homologação e regra fiscal vigente; sem evento real nesta entrega | Alta | P1 |
| Etiquetas e metadados | Q2 etiquetas/propriedades | Etiqueta, documento, autor e empresa | Ausente | Recurso local futuro independente | Nenhuma para organização local | Média | P2 |
| Certificado: metadados e vencimento | Código local | Empresa permitida, validade e titular | Disponível nas telas | Expor somente metadados mínimos na API | Cadeia/revogação e acesso dependem de validação específica | Média | P0 |
| API própria e credenciais | Pedido do usuário; código local | Hash do segredo, Workspace, empresas, escopos, validade | Ausente | DRF/OpenAPI; segredo só na criação, revogação e HTTPS | Bibliotecas mantidas, sem fornecedor fiscal obrigatório | Alta | P0 |
| NFS-e/CT-e/outros modelos | Q2 grupos próprios | Leiautes, regras, identificação e autorização próprios | Ausente; importador rejeita | Análise e conectores distintos | Prefeituras/ADN/SEFAZ ou fornecedor contratado | Alta | P2 |
| Execução de pagamentos | Q3 delimitação; pedido do usuário | Autorização bancária específica | Ausente | Fora desta entrega | Banco e autorização transacional | Alta | Fora do escopo |

## Critérios para avançar

1. Entregar primeiro importação local, revisão, associação, documentos privados e API própria; telas e API usam as mesmas regras.
2. Não transformar estado cadastral de certificado em “SEFAZ conectada”. Não retornar captura bem-sucedida com transporte indisponível. Registrar última sincronização somente após resposta externa efetiva.
3. Para SEFAZ, manter NT/schema vigentes, validação TLS, A1 autorizado, cobertura e operação supervisionada. A consulta piloto real de 21/10/2026 comprova uma execução, sem substituir a validação dos demais cenários. A NT v1.40 confirma janela de até 90 dias e ausência de geração retroativa de NSU para novo usuário ou após interrupção superior a 60 dias. Não prometer histórico integral. Respostas contêm até 50 `docZip` em base64/gzip. Espera mínima de uma hora após 137, 656 ou `ultNSU=maxNSU`; consultas pontuais possuem limite de 20 por hora e não estão implementadas. Outras aplicações do mesmo CNPJ precisam compartilhar a sequência.
4. Ciência de emissão, confirmação, desconhecimento e operação não realizada têm efeitos distintos. Download local nunca deve provocar manifestação. Prazos antigos de 180 dias não são base válida para codificação em 2026 sem conferência da NT v1.60 e legislação aplicável.
5. Para DDA, decidir fornecedor somente após confirmar consulta de **boletos recebidos**, cadastro/consentimento por pagador, cobertura, dados/PDF entregues, estados, limites, contrato e custos. API para emitir cobranças próprias não comprova esse acesso.
6. Os testes sintéticos devem provar isolamento, revogação, escopos, revisão e idempotência. Não equivalem a homologação com governo, banco ou fornecedor.

## Estado atual — captura oficial de 21/10/2026

| Área | Implementado | Limite preservado |
|---|---|---|
| Distribuição SEFAZ | Transporte oficial NFeDistribuicaoDFe com A1/mTLS, servidor TLS validado e schemas oficiais; consulta real comprovada no piloto | Disponibilidade é determinada pelo serviço, sem promessa de histórico integral |
| Ativação e rotina | A1 válido, consentimento de leitura por empresa, primeira consulta agendada e worker iniciado por `py iniciar.py` | Certificado cadastrado sem consentimento não habilita a leitura; processo precisa permanecer em execução |
| Retomada e concorrência | NSU, cooldown e lease duráveis por CNPJ/ambiente, compartilhados entre empresas desse CNPJ na instalação | Outros sistemas e instalações com bancos separados exigem coordenação externa |
| Entrega por cliente | Caixa de entrada durável e reentrega por hash para empresas autorizadas com certificado compatível válido; telas/arquivos limitados ao Workspace | Nenhuma caixa de documentos de outro cliente fica disponível ao usuário |
| Importação | XML completo de NF-e modelo 55 destinado ao CNPJ passa pelo importador; chave por empresa evita duplicação com upload/API | XML de outro papel fiscal ou incompatível permanece separado com o impedimento, sem virar nota recebida |
| Resumos e eventos | Classificação e armazenamento privados, separados de notas completas e previsões | Não geram parcelas nem mudam automaticamente situação fiscal ou pagamento |
| Acompanhamento | Última tentativa, resposta oficial, cStat/xMotivo, contagens, documentos, histórico e próxima consulta permitida | Agendamento salvo não é prova de que o processo está conectado neste instante |
| Ciência da Emissão | Autorização específica por resumo, assinatura e envio fiscal explícito, com registro de resultado e bloqueio de reenvio duplicado | Não é executada pelo worker; não confirma a operação. Manifestações conclusivas não têm envio implementado |
| API própria | Leitura das notas importadas pela captura, com credenciais/empresas/escopos existentes | Não há endpoint REST de captura ou manifestação; esses controles ficam no portal |
| DDA, bancos e pagamentos | Boletos locais e revisão continuam separados da integração fiscal | Sem consulta DDA, liquidação ou execução de pagamento |

Os módulos principais são `portal/services/sefaz_transport.py`, `portal/services/sefaz_schema.py`, `portal/services/capture.py`, `portal/services/sefaz_manifest.py`, `portal/sefaz_models.py`, `portal/capture_views.py` e `portal/management/commands/capturar_sefaz.py`. A renovação do A1 revalida os requisitos e retoma a fila autorizada, sem zerar o cursor. O recebimento é persistido antes da entrega local; reiniciar entre essas etapas permite reprocessar o que já foi recebido sem pedir novamente ao governo.

O campo `reported_nsu` mantém o cursor informado em rejeição para revisão; o cursor processado não avança em rejeição para pular documentos. A espera oficial é preservada, incluindo falta de documentos, rejeição 656 e fim da sequência. Consultas aceitas sem documentos não são convertidas em notas fictícias.

Testes automatizados usam respostas sintéticas e banco temporário; não enviam manifestações nem fazem consultas reais. Testes não podem preencher evidência de sucesso real como se fossem a SEFAZ. A consulta piloto é registrada separadamente. Fontes, regras atuais, resultado operacional e limitações estão em [INTEGRACAO-SEFAZ.md](../INTEGRACAO-SEFAZ.md); implantação supervisionada em [PRODUCAO.md](PRODUCAO.md).
