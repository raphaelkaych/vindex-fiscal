# Continuação — captura, administração e PDFs

**Relatório histórico:** consulte [a entrega posterior](NFSE-RECUPERACAO-PRODUCAO.md) para as 13 importações parciais, nova NFS-e e bloqueio NF-e 656. Correção da informação de PDF abaixo: a data inicialmente prevista foi prorrogada; a [página oficial de atualizações](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/atualizacoes-e-implantacoes) registra a desativação da antiga API ADN de DANFSe em **03/08/2026**. Os relatos de limitações dos 13 XMLs abaixo antecedem o tratamento parcial atual.

Conferência em **21/10/2026, 19:33:51, Brasília**, Alpha Pet LTDA, produção. Contagens são um retrato desse momento; o painel privado acompanha a evolução.

## Resultado real

| Serviço | Completos recebidos | Importados | Emissão mais recente importada | Outros documentos recebidos |
|---|---:|---:|---|---|
| NF-e | 278 | 278 | 01/10/2026 | 290 resumos, 17.010 eventos, 20.972 resumos de eventos |
| NFS-e | 195 | 182 | 20/10/2026 | 3 eventos; 13 completos aguardam compatibilidade de leiaute |
| CT-e | 6.039 | 6.039 | 18/08/2026 | 1.161 eventos |

A captura não ficou limitada às notas de julho: avançou automaticamente. As filas NF-e e CT-e ainda não alcançaram o máximo informado pela origem. Não se deve pular o cursor para procurar notas recentes: isso perderia documentos intermediários. A data de importação não é a data de emissão.

- **NF-e:** resposta oficial 138, “Documento(s) localizado(s)”, em 21/10/2026 às **19:28:24**. Cursor **000000000123317**, máximo **000000000133839**. A consulta 776 foi recuperada do XML de resposta já preservado, sem repetir HTTP, código local `recovered_local`; próxima consulta permitida **20:28:26**. A falha local original dessa consulta não pode ser identificada retrospectivamente apenas pelo registro recuperado. Não foi registrada nova rejeição 656 nessa última consulta.
- **NFS-e:** HTTP **404**, status `NENHUM_DOCUMENTO_LOCALIZADO`, motivo **E2220 — Nenhum documento localizado: não existem documentos fiscais para o Contribuinte a partir do NSU informado**, às **19:27:16**. Essa combinação documentada é fim normal de fila, não erro de certificado. Cursor **198**; próxima consulta **20:28:16**. Últimas emissões importadas chegam ao dia anterior à conferência.
- **CT-e:** HTTP **200**, código **138**, “documento localizado.”, às **19:33:49**. Cursor **000000000064281**, máximo **000000000080988**. Continua percorrendo lotes; próxima tentativa a partir de **19:33:51**. Nenhuma falha de entrega local nesse retrato.

Os horários acima são de Brasília. A retomada anterior após 656 está documentada em [entrega anterior](ENTREGA-CONECTORES-MASTER.md). Nenhuma manifestação fiscal foi enviada nesta continuação. Certificados, documentos e cursores existentes foram preservados.

## O que mudou

- **Master:** datas mínima/máxima de emissão e última importação; situação dos conectores; filtros por empresa e tipo e paginação independente de NFS-e/CT-e. Supervisão mantém o cliente explícito na URL, autenticação do administrador, auditoria e downloads limitados ao cliente selecionado.
- **PDF de NFS-e:** botão nos detalhes do documento e na supervisão master. Geração local em memória a partir do XML validado, identificação da chave, prestador/tomador, serviço/valores e relação dos campos originais sem arredondamentos adicionais. Cancelamento recebido e homologação aparecem claramente. Nenhum PDF real foi salvo nos arquivos da entrega.
- **NF-e e CT-e:** DANFE e DACTE continuam disponíveis, com o XML original.
- **Execução:** captura de leitura retomada na tarefa Windows existente e heartbeat confirmado ativo. Preferências, autorizações e progresso permanecem no banco.

### Limite específico do PDF de NFS-e

O botão é **PDF de conferência**, identificado como espelho do XML. **Não é uma implementação homologada do DANFSe v2.0**. A [NT 008 oficial](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/rtc/nt-008-se-cgnfse-danfse-20260505.pdf), seção 1, informa suspensão da API nacional de geração em 01/07/2026. O modelo oficial local v2.0 ainda precisa ser implementado e validado antes de receber esse nome no produto. O espelho entregue pode ter várias páginas; a NT exige uma página para seu DANFSe. Não foi apresentado um como se fosse o outro.

## Automação para todos os clientes

O fluxo usa configurações por empresa, serviço e ambiente e não contém tratamento exclusivo da Alpha Pet. Vincular um A1 válido, habilitar a captura e concluir as autorizações de leitura na aplicação agenda o trabalho automaticamente. CT-e exige UF. O processo periódico importa lotes futuros sem uma nova alteração de código ou um clique por consulta. Reiniciar o processo retoma o cursor persistido. Renovar o certificado preserva o histórico do CNPJ.

**Somente vincular o certificado, sem habilitação/autorização dos serviços, não concede consentimento fiscal.** Resumos dependentes de manifestação exigem a decisão específica prevista na aplicação. O fluxo respeita intervalos, bloqueios e disponibilidade real da origem; não garante que todo município/documento exista no ADN.

No uso local, mantenha computador ligado, internet e sessão Windows conectada. A tarefa **Vindex Fiscal - Captura** já está configurada. Isso não equivale a um serviço publicado 24 horas em servidor.

## Pendências

**Desenvolvimento/validação:** DANFSe oficial v2.0; compatibilidade de 13 NFS-e preservadas (11 recusadas no campo `pAliq`, 2 em `xOutInf` pelos schemas disponíveis); conclusão da leitura dos lotes antigos. Não foram alterados os XMLs ou relaxada a validação para forçar importação. Esses pontos não se resolvem enviando senha de certificado pelo chat.

**Operação do usuário:** criar o login master; concluir as autorizações das futuras empresas; manter o processo disponível e renovar A1 quando necessário. Para produção externa, preparar servidor/domínio/HTTPS/SMTP e homologar a implantação descrita em [IMPLANTACAO.md](IMPLANTACAO.md). Docker/PostgreSQL/Redis/SMTP não foram homologados neste computador. DDA e conexões bancárias permanecem para etapa posterior.

**Conferência ainda não realizada:** recebimento em produção de uma nota comprovadamente emitida depois da ativação, para uma segunda empresa real; reinício real do Windows; inspeção completa do navegador em temas/tamanhos. A ferramenta de controle do navegador encerrou por não conseguir determinar a URL com confiança; não foi contornada. Testes de servidor não substituem essa conferência visual.

## Verificações realizadas

- **305 testes aprovados** na suíte completa final, executada por `py iniciar.py --testar` (124,371 segundos), incluindo autenticação, isolamento, importação, certificados, master, PDFs e captura.
- Novo teste executa duas passagens da fila periódica para dois Workspaces, importa documentos de um lote posterior e verifica bloqueio de XML entre clientes. Usa transporte/A1/schema substituídos e dados fictícios somente no banco isolado; não é comprovação de uma nova emissão em produção.
- Testes de PDF verificam valores sem arredondamento, chave incompatível, texto longo, cancelamento/homologação, privacidade e supervisão vinculada ao cliente explícito. PDF de uma NFS-e real foi gerado em memória (4 páginas), com chave presente e XML inalterado; nenhuma cópia real foi incluída na entrega.
- Amostra inteiramente fictícia em duas páginas renderizada e inspecionada visualmente. `manage.py check` sem problemas, nenhuma migração pendente e diagnóstico final com captura ativa.

## Comandos no Windows

Na pasta do projeto:

```powershell
py iniciar.py --preparar
.\.venv\Scripts\python.exe manage.py criar_admin_master
py iniciar.py
```

O primeiro prepara dependências e migrações. O segundo solicita seu e-mail/senha no terminal e concede o acesso master explicitamente. O terceiro abre o servidor e aproveita o processo de captura ativo.

Entre em **http://127.0.0.1:8000/entrar/** e abra **http://127.0.0.1:8000/gestao/**. Selecione o cliente, confira as datas e filtre NFS-e/CT-e. Abra o documento para XML ou PDF. No portal do cliente: **Minhas empresas → Conectores** e **Documentos consolidados**.

```powershell
.\.venv\Scripts\python.exe manage.py verificar_captura
.\.venv\Scripts\python.exe manage.py diagnosticar_empresa --empresa 5
py iniciar.py --testar
```

Os dois primeiros fazem diagnóstico local sem uma nova consulta fiscal. O último executa testes isolados, sem usar os certificados reais. Não é necessário executá-los a cada nova nota ou certificado.
