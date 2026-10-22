# Intervalos, aviso de erro e menu lateral

Atualização de 21/10/2026, após a entrega de recuperação de NFS-e.

## Avisos da imagem

O código **656 é uma resposta real da SEFAZ** e permanece no histórico. O texto retornado menciona consumo indevido/ultNSU; aguardar mais não prova nem corrige, por si só, sua causa. Não foi feita nova chamada para tentar remover o aviso. A regra de espera e continuidade pelo último NSU foi conferida no [informe oficial do Portal NF-e](https://www.nfe.fazenda.gov.br/portal/informe.aspx?AspxAutoDetectCookieSupport=1&Informe=0cu%2FyBLKrCs%3D&ehCTG=false).

O aviso separado **“Falha interna … Código: worker” estava desatualizado**. Um diagnóstico local, com transporte de rede bloqueado, processou a empresa normalmente como `waiting`. Porém, o caminho de espera só atualizava o estado para respostas 137/138 e deixava o erro antigo sobre uma resposta 656 conhecida.

Foi corrigida a reconciliação desse estado: quando há 656 conhecido e nenhuma falha local pendente no stream, a configuração passa a mostrar `sefaz_656` e o motivo oficial. Se ainda existir falha local, ela não é ocultada. A exceção específica de rejeição oficial também não é mais reclassificada genericamente como erro de requisitos pelo worker. Novas falhas inesperadas geram auditoria com a classe da exceção, sem sua mensagem, XML, certificado ou senha. A causa da antiga exceção interna não ficou registrada com detalhe suficiente para ser afirmada retroativamente.

## Intervalos

- Espera padrão após NF-e 137/656 ou fim da fila aceita: **120 minutos** desde a referência mais tardia entre recebimento local e horário oficial.
- NFS-e/CT-e: **120 minutos** após fim da fila/rejeição; recuperação de resultado incerto desses conectores também usa a espera conservadora.
- Histórico ainda disponível: intervalo curto de **10 segundos** entre lotes no processo contínuo; a agenda local pode aguardar mais conforme o ciclo. Não se espera duas horas entre cada lote de histórico.
- O polling local da fila continua independente; conferir o banco a cada ciclo não dispara consulta fiscal enquanto o prazo estiver vigente.
- Configuração opcional de servidor: `FISCAL_IDLE_INTERVAL_MINUTES=120`. O código impede reduzir esse valor abaixo de 61 minutos. Retentativas locais de importação e outras políticas de falha não são a mesma coisa que consultas periódicas sem novos documentos.

As esperas já salvas de fim de fila/bloqueio foram ampliadas uma única vez, sem reduzir esperas maiores. NSUs, XMLs, notas, certificados e autorizações foram preservados. No piloto, NF-e manteve **NSU 123317**, código 656 e passou a aguardar **21/10 às 22:28:38, Brasília**; NFS-e manteve NSU 199. A próxima consulta aceita de NF-e ainda precisa ser observada; o código oficial não foi removido nem substituído por sucesso.

A captura foi pausada brevemente para manutenção, retomada e o worker em segundo plano foi reiniciado para carregar a política nova. Não é necessário executar comandos diários adicionais.

## Menu

Gestão master fica primeiro, somente para quem possui a permissão. No painel comum/supervisionado, vêm Visão geral, Minhas empresas, Indicadores fiscais, Notas fiscais, Documentos consolidados, Pendências fiscais e Captura de NF-e; depois permanecem agenda, boletos, integrações e certificados. Cada opção usa ícone SVG no padrão existente. Não foram criadas novas seções, permissões ou mistura de dados entre clientes. O estado ativo de Documentos consolidados também recebeu `aria-current`.

Para usar as mudanças, atualize a página. O iniciador e a tarefa Windows existentes continuam sendo os mesmos. Use `manage.py verificar_captura` para conferir o processo; o sucesso desse comando não equivale a uma resposta fiscal aceita.

## Conferência final

**338 testes aprovados** com `py iniciar.py --testar`, incluindo regressões para o aviso antigo de worker, preservação de falha local verdadeira, espera de duas horas com relógio oficial adiantado e limite mínimo de configuração. `manage.py check` sem problemas. A página de captura supervisionada respondeu HTTP 200, preservou a resposta 656 e não apresentou mais o texto de falha interna. A ordem do menu e os ícones foram conferidos no HTML autenticado. A tarefa Windows estava Running, com heartbeat ativo e o Workspace piloto despausado. Não foi feita nova inspeção visual automatizada em navegador nesta alteração.
