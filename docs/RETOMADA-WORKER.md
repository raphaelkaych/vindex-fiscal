# Captura iniciada e interrupção posterior — 21/10/2026

A tela enviada pelo usuário não significava que nenhum documento havia sido capturado. No retrato das 22:23, a empresa local VINDEX - TESTE 2 tinha **278 NF-e, 196 NFS-e e 14.118 CT-e** preservados. Havia documentos até setembro nos CT-e e até 21/10 nas NFS-e. Datas de emissão, importação, eventos e serviços são conceitos distintos; a situação do painel de captura de NF-e não descreve sozinha todos os conectores.

O banco e os registros mostraram falhas `OperationalError` no worker para a empresa local 6. A tarefa Windows estava Ready, com último resultado 1 (encerramento com erro). O iniciador do portal já havia criado um processo substituto e o sinal de execução estava novamente ativo na inspeção. O log antigo do helper não preservava a classe da exceção fatal; portanto, não foi comprovado que ela era a mesma falha de banco registrada na auditoria, nem o motivo exato do erro de banco. Não se afirmou que o certificado havia sido rejeitado.

## Correção

O loop contínuo agora trata `OperationalError` e `InterfaceError` de banco sem encerrar o consumidor inteiro. Registra classe/código seguro, sem mensagem de exceção ou dados fiscais, aguarda o ciclo e reavalia a fila pelas regras normais. Não refaz diretamente uma chamada remota: autorizações, leases, recuperação de respostas e cooldown continuam sendo consultados. Se o banco continuar indisponível, a causa de infraestrutura precisa ser resolvida; o tratamento não conserta disco, permissões ou configuração.

No modo `--once`, a mesma falha termina como erro explícito, sem anunciar sucesso. Outros erros inesperados não são silenciosamente transformados em captura concluída.

Para carregar a correção, foram verificadas as reservas, pausados brevemente os Workspaces 1 e 3 (ambos originalmente ativos), encerrado o grupo substituto do worker e iniciada a tarefa **Vindex Fiscal - Captura** às **22:26:28**. Os dois Workspaces foram despausados. A tarefa ficou Running e `verificar_captura` confirmou atividade. Cursores, certificados, documentos e intervalos não foram zerados ou reduzidos. O CT-e manteve a espera já registrada de resultado incerto de execução anterior.

## O que significa 656

656 é rejeição oficial por uso indevido, não uma etapa obrigatória de baixar muitas notas nem consequência automática de uma requisição longa. A mensagem observada aponta a continuação pelo `ultNSU`. É correto consumir os lotes disponíveis, preservar o último NSU retornado e, após fim da fila, aguardar antes de procurar novidades. A rejeição exige espera, mas sua recorrência pede investigação; o aplicativo não deve depender de ser bloqueado para regular o fluxo.

Mantida a política de duas horas e a resposta 656 real. Nenhuma consulta manual foi disparada nesta intervenção. [Regras do Portal NF-e](https://www.nfe.fazenda.gov.br/portal/informe.aspx?AspxAutoDetectCookieSupport=1&Informe=0cu%2FyBLKrCs%3D&ehCTG=false).

Os testes específicos de retomada cobrem falha de banco em um ciclo seguida por funcionamento no seguinte, ausência de vazamento da mensagem da exceção e falha explícita em `--once`. A correção não substitui a homologação de PostgreSQL e monitoramento no servidor, já indicada no guia de produção.

## Resultado observado após a retomada

O worker realizou **automaticamente** uma consulta de produção às **22:29:09**, após a espera ampliada. A resposta voltou a ser 656, com a mesma mensagem de continuidade por ultNSU. A consulta enviou **123317**, porém a resposta agora informou **133884** (maxNSU zero na rejeição). Isso demonstra divergência entre a sequência local preservada e o NSU informado pela origem; a razão de esse número ter avançado ainda não foi comprovada. Não se concluiu que outro programa externo esteja ativo nem que todo o intervalo tenha sido entregue ao Vindex.

O NSU processado permaneceu **123317**. Não se substituiu automaticamente pelo 133884, para não pular documentos potencialmente ausentes. A próxima tentativa foi salva para **22/10 às 00:29:09, Brasília**, e o processo continuou ativo. O intervalo maior, portanto, **não normalizou a NF-e** nesta observação; esse ponto continua exigindo investigação da distribuição. A falha local que derrubava o loop e a rejeição oficial são problemas distintos.

**340 testes aprovados** com `py iniciar.py --testar`; `manage.py check` sem problemas. A tarefa Windows continuava Running e foi observado apenas um grupo lógico do helper de captura após o reinício. Não houve reset, perda de documentos ou envio de evento fiscal.
