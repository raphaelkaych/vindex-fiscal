# Entrega da captura — 21/10/2026

> Registro histórico da primeira conferência, anterior às 14:25. A pendência de retomada descrita abaixo foi resolvida e comprovada pelo worker. Consulte o [relatório atualizado](RELATORIO-ATUAL.md) para o resultado posterior e o DANFE.

## Resultado comprovado do piloto

O A1 já vinculado foi localizado, aberto do armazenamento cifrado e revalidado, sem exportação de segredo. A vigência termina em 23/03/2027 e o CNPJ corresponde à empresa piloto autorizada. A consulta de produção usou mTLS e validação TLS do servidor, sem desativar confiança.

Foram recebidos **450 documentos reais**: 1 resumo NF-e, 1 XML completo, 215 eventos e 233 resumos de eventos. **Uma NF-e foi importada**, com origem SEFAZ e sem marca de demonstração. O destinatário corresponde à empresa e o XML salvo corresponde ao documento recebido. As páginas privadas da captura e da nota renderizaram HTTP 200. Nenhum XML, chave fiscal, certificado ou senha integra este relatório.

Última resposta aceita nessa conferência: **21/10/2026, 13:18:49, Brasília**, produção, **138 — Documento(s) localizado(s)**. O NSU persistido é 000000000085217 e o máximo informado na última resposta aceita é 000000000133686. O restante da fila ainda não foi esgotado.

## Ocorrências e pendência real

1. A primeira consulta recebeu **404 — Rejeicao: Uso de prefixo de namespace nao permitido**. O XML foi corrigido para namespace NF-e padrão, sem prefixos. As nove páginas seguintes receberam 138 e incluíram o XML importado.
2. A tentativa automática de **13:25:47** falhou no parser com **O último NSU do retorno supera o NSU máximo.** O código/motivo oficial daquela resposta não foi preservado pelo código então carregado e não pode ser deduzido do erro local. Não foi afirmado que houve 656, nem atribuição a outro programa; o proprietário informou que não utiliza outro consumidor.
3. A relação entre os NSUs passou a ser conferida como progresso apenas nas respostas aceitas. A resposta bruta privada agora é persistida antes da validação XSD/processamento; metadados oficiais são preservados mesmo numa falha. A correção tem testes de regressão.
4. A espera conservadora já registrada foi preservada. A próxima tentativa fica programada para **21/10/2026, 14:25:48, Brasília**. Não foi feita consulta antecipada. O resultado dessa rodada posterior ainda não foi validado nesta conferência.

O NSU não foi zerado, adiantado nem substituído por cursor de rejeição. As notas existentes foram preservadas.

## Fluxo entregue

Cadastro de A1 e autorização de leitura agendam captura para qualquer empresa de qualquer Workspace. Renovação preserva histórico e progresso; desmarcar a captura na renovação pausa futuras consultas. Leitura não autoriza manifestação.

O worker mantém cursor e reserva global por CNPJ/ambiente; entrega apenas em caixas autorizadas com A1 válido do próprio cliente; importa XML modelo 55 recebido para o destinatário correto; preserva resumos/eventos e impedimentos; reprocessa localmente documentos com erro. Falha de transporte, resultado desconhecido e reserva real abandonada têm espera conservadora.

O inicializador integra portal e captura e reutiliza worker já ativo. O painel apresenta atividade do processo, tentativa/resposta oficial, contagens, histórico, próxima data permitida, NSUs e causas de erro.

A tarefa **Vindex Fiscal - Captura** foi registrada no Agendador de Tarefas do Windows, para logon do usuário atual, sem senha armazenada e com permissões limitadas. A tarefa foi iniciada e seu processo foi observado em execução, com sinal de atividade atualizado. O portal foi reiniciado reutilizando essa captura; NSU e horário da próxima consulta permaneceram iguais.

Ciência da Emissão tem autorização específica por chave, assinatura e validação por schemas oficiais atuais, inclusive CNPJ alfanumérico. Bloqueia duplicidade por CNPJ/ambiente/chave e resultado incerto. **Nenhum evento fiscal real foi enviado.** Manifestação conclusiva e DDA não têm envio/integração implementados.

## Verificações

- Execução completa de `py iniciar.py --testar`: **250 testes aprovados**. Após a revisão final da opção de pausa na renovação, os **101 testes pertinentes** de captura, pipeline, interface e certificados passaram, incluindo a regressão adicionada.
- **32 verificações JavaScript/DOM/CSS aprovadas**: temas, persistência, teclado, menu, retorno de ações e componentes. Isso não é inspeção visual de pixels em navegador.
- Migrações aplicadas, `makemigrations --check --dry-run` sem mudanças; OpenAPI validada sem avisos.
- Assinatura da Ciência verificada criptograficamente após serializar/reabrir o SOAP, com certificado sintético. Testes não fazem consultas ou manifestações reais.
- Validação real de importação, hash do XML recebido, CNPJ, origem e renderização das páginas privadas. Downloads e páginas fiscais usam escopo por Workspace e cache privado desativado.
- Registro/início da tarefa Windows, atividade do worker e retomada dos processos observados sem antecipar a consulta.

Não foram executados reinício real do Windows, envio fiscal de Ciência, implantação pública, operação com PostgreSQL/Redis, inspeção visual completa em navegador ou validação de recebimento futuro de novas emissões. A consulta agendada após a falha permanece a principal validação real pendente.

Comandos e operação diária: [CAPTURA-SEFAZ.md](CAPTURA-SEFAZ.md). Protocolos e fontes oficiais: [INTEGRACAO-SEFAZ.md](../INTEGRACAO-SEFAZ.md).
