# Retomada de NF-e após rejeição 656

## O que mudou

A captura distingue o cursor dos lotes já armazenados do NSU informado pela SEFAZ em uma rejeição. Preservar somente o primeiro e reenviá-lo indefinidamente pode repetir a rejeição de sequência, mesmo após a espera.

Na próxima consulta permitida, a última resposta `distNSU` pode orientar a retomada, desde que tenha corpo preservado, ambiente correto, schema válido, código 656, motivo referente a `ultNSU` e NSU superior ao cursor local. Somente metadados ou uma rejeição por quota não autorizam a mudança. Nenhuma espera é antecipada.

O cursor local só muda quando uma nova resposta aceita é armazenada. Na mesma transação, o intervalo intermediário ainda não recebido fica em `SefazNsuRecovery`. Não é apresentado como histórico já importado. A origem da divergência remota precisa ser investigada separadamente; não se presume a existência de outro consumidor.

## Duas filas, uma identidade e uma reserva

- A distribuição `distNSU` mantém a prioridade para receber documentos novos.
- Os NSUs intermediários são verificados pontualmente por `consNSU`, quando a distribuição está aguardando seu próximo ciclo.
- Cada recuperação aceita armazena o documento e atualiza sua própria posição na mesma transação, sem alterar `ultNSU`/`maxNSU` da distribuição.
- A consulta pontual admite um único documento com o NSU solicitado. Resposta divergente fica preservada para revisão, sem avanço.
- Respostas 137 pontuais ficam registradas como NSU sem documento disponível. Uma verificação concluída com indisponíveis não garante acervo completo.
- A1 válido, consentimento, situação da empresa/conta e isolamento de entrega continuam obrigatórios.
- Os vínculos do mesmo CNPJ/ambiente compartilham reserva, bloqueio e frequência. Duplicar o cadastro não cria uma segunda sequência de distribuição.
- A recuperação limita-se a 18 consultas em uma janela móvel de uma hora, com intervalo mínimo de 210 segundos. É uma margem local abaixo do limite oficial de 20 consultas pontuais por hora. A mesma quota não é interpretada como limite de páginas `distNSU`.
- Uma rejeição 656 bloqueia as duas filas pelo intervalo conservador existente, atualmente duas horas. Timeout ou interrupção também exige espera antes da retomada.

Nenhuma dessas leituras envia Ciência da Emissão ou outro evento fiscal. Resumo não vira XML completo por esta recuperação; eventual manifestação mantém autorização própria por documento.

## Persistência e observabilidade

A migração `0015_sefaz_recovery` acrescenta a modalidade e o ponto anterior de retomada ao histórico de consultas, a espera global explícita e a fila de recuperação. Ela não redefine cursores, apaga certificados ou remove documentos.

O painel de captura mostra o intervalo pendente, próximo NSU, documentos recuperados, NSUs indisponíveis e erros. O histórico identifica distribuição e recuperação pontual. A auditoria local também separa essas modalidades para não interpretar uma recuperação antiga como regressão do cursor atual.

Uma lacuna extensa leva tempo para ser conferida com o limite oficial. O prazo de disponibilidade do serviço continua aplicável. Não há garantia de recuperação de um documento já expirado ou não disponibilizado ao CNPJ.

## Windows

Para preparar uma instalação que recebeu o código atualizado:

```powershell
py iniciar.py --preparar
```

O comando aplica migrações e verifica a aplicação. Para iniciar a aplicação com captura:

```powershell
py iniciar.py
```

Se a captura já estiver instalada no Agendador de Tarefas, reinicie a tarefa após atualizar o código, em uma janela sem consulta em andamento:

```powershell
Stop-ScheduledTask -TaskName "Vindex Fiscal - Captura"
Start-ScheduledTask -TaskName "Vindex Fiscal - Captura"
```

Não rode outro worker para tentar antecipar a espera. A tarefa e o inicializador utilizam os controles de instância e de banco existentes.

Na migração para hospedagem, preserve o banco/cursor e a chave de cifra original. A captura local e a hospedada não devem operar o mesmo CNPJ de produção com bancos independentes; a reserva desta instalação não coordena outra instalação desconectada. Interrompa a captura local quando o servidor assumir a operação.

Auditoria sem rede, sem abrir o A1 e sem alterar cursores:

```powershell
.\.venv\Scripts\python.exe manage.py auditar_distribuicao --cnpj SEU_CNPJ --ambiente 1
```

Testes:

```powershell
py iniciar.py --testar
```

## Referências oficiais

- [NT 2014.002 v1.40, julho de 2026 — retorno do último NSU na rejeição 656 e consultas pontuais](https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=uWO2d%2FgTuWg%3D), seções 3.6 e 3.11.4; PDF oficial conferido em 22/10/2026.
- [Informe do Portal NF-e sobre consumo indevido na distribuição](https://www.nfe.fazenda.gov.br/portal/informe.aspx?AspxAutoDetectCookieSupport=1&Informe=0cu%2FyBLKrCs%3D&ehCTG=false).
- O pedido `consNSU` é validado pelo mesmo schema oficial local `distDFeInt_v1.01.xsd`; a resposta utiliza `retDistDFeInt_v1.01.xsd`.

As regras de outros serviços de emissão não devem ser aplicadas indiscriminadamente à distribuição nacional de documentos.
