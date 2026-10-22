# Captura automática de NF-e no Windows

A captura está implementada para empresas de todos os clientes. Cada empresa precisa do cadastro por CNPJ, A1 vigente da mesma raiz e autorização de leitura. Os documentos vêm do serviço oficial; certificado salvo não é apresentado como consulta aceita.

## Iniciar a aplicação

Na pasta do projeto:

```powershell
py iniciar.py
```

O inicializador prepara dependências/migrações e inicia o portal em http://127.0.0.1:8000 junto com o processo de captura. Ele supervisiona o worker e o reinicia se encerrar inesperadamente. Se a captura já estiver ativa pelo Agendador de Tarefas, reutiliza esse processo. Mantenha o terminal aberto para usar o portal; Ctrl+C encerra os processos iniciados por ele. A tarefa independente do Windows continua ativa. Ao abrir novamente, a fila retoma consentimentos, NSUs e prazos. Não é preciso executar comandos a cada consulta.

Para somente captura, usando o mesmo banco e chave de cifra:

```powershell
py iniciar.py --capturar
```

## Habilitar uma empresa

1. Cadastre o CNPJ em **Minhas empresas**.
2. Em **Certificados**, vincule o A1 da empresa pela aplicação. Não envie arquivo ou senha pelo chat.
3. Confirme autorização de uso e marque **Habilitar a captura automática de NF-e recebidas em produção**. A UF é opcional.
4. A primeira consulta será agendada. Acompanhe em **Captura SEFAZ**.
5. XMLs completos recebidos e importáveis aparecem em **Notas recebidas**, com origem SEFAZ e no CNPJ correto.

Para A1 já cadastrado, abra a configuração de **Captura SEFAZ**, confirme a autorização e salve. Renovar o certificado retoma a captura já autorizada, sem apagar documentos, reiniciar NSU ou antecipar consulta. Pausar preserva o histórico e impede novas consultas daquela autorização.

## Entender o painel

O painel diferencia processo ativo/parado, autorização pendente, certificado ausente/vencido, consulta agendada/em andamento, espera e erros específicos. O sinal de atividade é local à instalação; não substitui alertas de infraestrutura.

Confira última tentativa, código/motivo, data/hora oficial, NSUs, próxima consulta permitida, contagens por tipo e histórico. Tentativa com erro não é resposta fiscal aceita. Código 137 significa que não havia documentos disponíveis naquela consulta.

Resumos e eventos têm páginas/downloads privados próprios. Resumo não é XML completo e não gera parcelas. XML com impedimento de importação fica preservado, com causa visível e tentativa local posterior. Previsões e conferências não comprovam pagamento bancário.

## Resumos e Ciência da Emissão

A página do resumo explica a diferença e oferece **Autorizar e enviar Ciência da Emissão**, exclusivamente para a chave identificada, com confirmação própria. Essa autorização é independente da leitura automática.

Ciência é evento fiscal real: registra conhecimento da emissão, pode viabilizar disponibilização posterior do XML e exige acompanhamento da manifestação conclusiva aplicável. Não confirma a operação comercial. O Vindex não envia Ciência automaticamente nem implementa envio de manifestação conclusiva. Um resultado incerto/duplicado não é reenviado automaticamente. Veja regras e fontes em [INTEGRACAO-SEFAZ.md](../INTEGRACAO-SEFAZ.md).

## Esperas e falhas

- Após 137, 656 ou fim da fila, aguarde pelo menos uma hora. A verificação local da fila não significa chamada ao governo a cada poucos segundos.
- Enquanto há páginas disponíveis, o processo continua pelo NSU recebido. Reiniciar, renovar A1 ou salvar autorização não elimina a espera.
- Timeout ou resultado desconhecido provocam espera conservadora de uma hora. O painel mostra a causa e o horário permitido.
- Usuário novo pode não receber histórico anterior ao primeiro acesso. A janela é de até 90 dias, sujeita às condições de geração e distribuição.
- Se o A1 vencer ou não puder ser aberto, vincule certificado válido na aplicação. Erro de confiança TLS exige corrigir as autoridades do ambiente; não desative validação.
- Em divergência de NSU, não zere cursor nem tente números aleatórios. Preserve evidências e investigue o retorno. Instalações independentes do mesmo CNPJ precisam de coordenação.

## Iniciar com o Windows

Depois de preparar e validar a instalação, o script abaixo registra uma tarefa de captura no logon do usuário atual, com permissões limitadas:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\configurar-captura-windows.ps1
```

A tarefa usa o Python do projeto, funciona sem janela e escreve mensagens operacionais em `tmp/capture-worker.log`. Ela captura sem abrir o portal. O banco, o A1 cifrado e o arquivo .env precisam continuar acessíveis à mesma conta Windows. O computador precisa estar ligado e com internet; suspensão/desligamento interrompem a execução.

Para remover somente essa tarefa:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\configurar-captura-windows.ps1 -Remover
```

Políticas do Windows podem negar o registro; o erro informa a causa. O script não se eleva sozinho. Em servidor publicado, mantenha web e captura como serviços supervisionados com banco/configuração compartilhados, conforme [PRODUCAO.md](PRODUCAO.md).

## Manutenção

```powershell
# Preparar sem iniciar consultas nem servidor
py iniciar.py --preparar

# Testes sintéticos, sem consultas fiscais
py iniciar.py --testar

# Uma volta da fila já autorizada, respeitando os prazos
.\.venv\Scripts\python.exe manage.py capturar_sefaz --once

# Worker separado para servidor web próprio
.\.venv\Scripts\python.exe manage.py capturar_sefaz --interval 15 --limit 20
```

Não há opção de forçar consulta ou reiniciar NSU.

## Estado da validação

O piloto efetuou consultas autenticadas de produção, recebeu documentos reais e importou XML completo no CNPJ correto. Após a correção do tratamento de NSU e a espera conservadora, o worker retomou sozinho em **21/10/2026 às 14:25:48 (Brasília)**, recebeu código 138 e importou novas NF-e sem clique de consulta. Às **14:42:23**, houve rejeição oficial 656; o processo conserva 5.200 documentos e quatro NF-e, aguardando **15:43:23**. A auditoria não encontrou divergência local na sequência; a causa da rejeição permanece sem comprovação. A resposta posterior à espera ainda precisa de acompanhamento. O código da resposta perdida antes da correção não pode ser deduzido pelo erro local.

Contagens e resultados reais atualizados ficam no painel privado. Documentos reais não são distribuídos com o código. O [relatório atualizado](RELATORIO-ATUAL.md) registra contagens agregadas e limites da conferência. A tarefa **Vindex Fiscal - Captura** já está registrada e em execução nesta máquina; não é necessário repetir comandos por consulta. Manifestações reais, implantação pública, infraestrutura PostgreSQL/Redis, reinício real do Windows e futuras emissões exigem as validações operacionais correspondentes. Notas completas também oferecem [DANFE gerado em PDF](DANFE.md).
