# Diagnóstico inicial — 20/10/2026

Inspeção dos arquivos, sem consultar documentos reais, certificados ou segredos.

| Área | Estado encontrado antes desta evolução | Evidência local |
|---|---|---|
| Contas e clientes | Funcional; um proprietário por Workspace | `portal/models.py`, `portal/views.py`, `portal/tests.py` |
| Empresas | Funcional; CNPJ identifica o histórico dentro do cliente | `Company`, restrição workspace/CNPJ |
| NF-e de compras | Importação manual modelo 55; XML privado; sem validação de assinatura ou consulta fiscal | `portal/services/invoices.py` |
| Parcelas | Duplicatas extraídas; conferência manual; sem edição dos dados incompletos | `Installment`, agenda e detalhes |
| Pagamento declarado no XML | Somente descrição da modalidade; valores e cobrança ainda não preservados separadamente | `parse_nfe` |
| Certificados | A1 inspecionado localmente, arquivo e senha cifrados; renovação preserva empresa/notas | `portal/services/certificates.py` |
| Boletos | Ausente | Sem modelo, importador, tela ou conector |
| API de integrações | Ausente | Sem DRF, credenciais ou esquema |
| SEFAZ, DDA, manifestações | Ausentes; telas informam o limite | `INTEGRACAO-SEFAZ.md` |
| Identidade | Tema claro/escuro com preferência local, tokens da marca e regras responsivas | `static/portal/` |
| Produção | HTTPS/cookies seguros quando DEBUG=False; hosts por ambiente; SQLite e cache local; sem PostgreSQL configurável ou worker | `config/settings.py` |

A referência funcional Qive foi conferida em seu portal e no Swagger que o próprio portal referencia. O POST de NF-e é consulta por filtros, não emissão. O esquema atual inclui pesquisa de boletos e download de PDF, cuja disponibilidade técnica não garante contratação ou consentimento. A matriz detalhada, com fontes e dependências, está em `MATRIZ-FUNCIONAL.md`.

Prioridade: (1) modelos e serviços locais de boletos e revisão das previsões; (2) API própria com credenciais por cliente/CNPJ; (3) documentação e testes de isolamento; (4) preparação verificável da distribuição SEFAZ. Chamadas externas, pagamentos e manifestações reais não serão executados sem homologação e credenciais autorizadas.

Fontes iniciais: https://developers.qive.com.br/ ; https://docs.arquivei.com.br/arquivei-apis-swagger/dfe-api.json ; https://qive.com.br/solucoes/por-documento/boletos . As datas das versões e limitações de acesso estão na matriz.
