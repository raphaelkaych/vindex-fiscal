# Recuperação por chave e exclusão de conta

## Escopo das regras de consumo

A distribuição nacional de NF-e segue a NT 2014.002 v1.40. Cada resposta `distNSU` admite até 50 documentos; isso não limita o histórico inteiro a 50 ou 600 arquivos. A sequência usa `ultNSU`, e respostas 137, 656 ou fim da fila impõem espera. O limite de 20 consultas por hora refere-se às consultas pontuais `consNSU`/`consChNFe`.

O Vindex mantém margem de 18 consultas pontuais em janela móvel de uma hora, com intervalo mínimo de 210 segundos entre elas, somadas entre modalidades e Workspaces do mesmo CNPJ/ambiente. O bloqueio 656 impede todas as modalidades de NF-e. Não há rodízio de certificados, troca de IP, consulta em homologação para obter documentos de produção ou antecipação do bloqueio.

Rejeições persistentes ampliam a espera local: a cada três falhas consecutivas, a espera configurada é multiplicada por dois, limitada a 24 horas. Uma configuração maior continua sendo respeitada. Essa é uma política preventiva do aplicativo, não um novo prazo legal nem uma declaração de bloqueio permanente. Prazos previamente salvos nunca são encurtados pelo cadastro ou exclusão de uma conta.

A regra de 50 bloqueios citada na NT 2018.002 trata dos serviços autorizadores e de critérios parametrizáveis da UF. Sua menção em um artigo não diagnostica bloqueio permanente do `NFeDistribuicaoDFe`. O código, o motivo, a modalidade, os horários e o histórico real devem ser analisados. O aplicativo não dispõe de comando de desbloqueio remoto.

## Recuperação excepcional por chave

Há uma fila persistente `SefazKeyRecovery`. Ela agenda somente NF-e referenciada em CT-e com schema validado, da própria empresa e ambiente, no qual o CNPJ figura como destinatário da carga. Esse vínculo é evidência para investigar; a condição de destinatário da NF-e é conferida somente no XML recebido.

Para diagnosticar, a partir da pasta do projeto:

```powershell
.\.venv\Scripts\python.exe manage.py recuperar_nfe_referenciadas --company ID_DA_EMPRESA --desde AAAA-MM-DD --limit 10
```

Substitua os valores pelo ID e data desejados, dentro dos últimos 90 dias. O comando seleciona CT-e emitidos e chaves com competência a partir dessa data, até o mês atual. Acrescente `--executar` para agendar. O comando não faz HTTP; o worker já existente processa a fila após bloqueios e quotas. Há limite de 20 solicitações pendentes por CNPJ/ambiente; as chaves mais recentemente referenciadas são priorizadas. É uma recuperação pontual de evidências identificadas, não uma varredura alternativa do histórico.

A operação `consChNFe` usa o mesmo endpoint oficial, A1 cifrado, validação TLS e XSD. Só é aceita uma resposta compatível com a chave solicitada. NSU ausente é permitido nessa modalidade. O retorno é preservado antes do processamento e pode ser recuperado localmente, sem novo HTTP, se houver falha de armazenamento. XML completo e destinatário compatível passam pelo importador existente. Resumo não é transformado em nota completa. O cursor e o máximo da distribuição ficam intactos.

O retorno real do AN 1.7.8 omitiu `ultNSU`/`maxNSU` do cabeçalho na busca por chave, embora o XSD publicado os exija. O arquivo oficial foi preservado; somente essa modalidade usa uma variante em memória que admite esses dois campos ausentes. Outros campos e as validações de ambiente/chave/documento permanecem obrigatórios. Distribuição sequencial não admite omitir seus cursores. A recuperação local também entrega/importa os documentos e atualiza as contagens, sem antecipar a agenda.

Consultas rejeitadas por permissão, expiração, cancelamento ou inexistência são finalizadas com o motivo oficial; não são repetidas em loop. 656 bloqueia todas as filas de NF-e e amplia a espera. Erros 108/109/999 têm repetição limitada. Nenhuma consulta envia Ciência ou outra manifestação. Uma consulta pontual aceita não prova que a distribuição sequencial foi normalizada; a tela mantém esse aviso separado.

Se a recuperação por chave receber 656, a próxima janela volta a testar primeiro a distribuição sequencial, depois da espera ampliada. A recuperação excepcional não substitui indefinidamente a captura principal.

Em **Captura de NF-e**, a tabela **NF-e referenciadas em CT-e** mostra o agendamento e o resultado de cada pedido do próprio acesso. Os XMLs completos importados aparecem em **Notas fiscais**. O gerador de **DANFE (PDF)** existente é reutilizado quando o XML contém os dados e o protocolo necessários; não são criados documentos a partir de eventos ou resumos.

## Excluir minha conta

Em **Minha conta → Excluir minha conta**, o titular pode remover seu login, empresas, A1, credenciais de API e arquivos privados. A tela informa as quantidades e os efeitos. Exige POST, CSRF, senha atual, nome exato do cliente e confirmação explícita. Senhas não são reapresentadas. Há limite de tentativas. A supervisão master por URL continua somente leitura e não oferece esse direito em nome do cliente.

Esta exclusão é um fluxo específico solicitado pelo titular. O gerenciamento administrativo rotineiro continua permitindo exclusão simples apenas de cadastro vazio. Para executar uma solicitação explícita como operador local:

```powershell
.\.venv\Scripts\python.exe manage.py excluir_conta_cliente --workspace ID_DO_CLIENTE --executor-email EMAIL_DO_MASTER --confirmar-nome "NOME EXATO DO CLIENTE"
```

O comando apenas diagnostica sem `--executar`. O executor precisa de `admin_master` e `operate_clients`. O login administrativo não pode ser apagado por esse fluxo enquanto mantiver função administrativa; transfira e remova seus privilégios antes. Consultas em andamento impedem a exclusão até sua conclusão.

As entregas, documentos e configurações privados desse Workspace são removidos em transação única, com lotes para respeitar os limites do SQLite. A captura desse vínculo é encerrada. Documentos e certificados de outros clientes são preservados.

As filas, cursores, bloqueios, consultas oficiais e evidências de eventos fiscais do CNPJ não são apagados. O histórico de consultas passa a apontar diretamente para `SefazDistributionStream`; seu vínculo privado pode tornar-se nulo. Isso preserva a sequência e a quota mesmo após exclusão. Autorizações/eventos fiscais retidos impedem que um recadastro gere Ciência duplicada. Auditorias administrativas são mantidas sem vínculo ao cliente excluído. Backups existentes não são eliminados automaticamente: a operação em produção precisa de política própria de retenção e atendimento de solicitações de dados. O botão não promete apagar todos os registros fiscais compartilhados ou cópias de segurança.

## Referências oficiais

- [NT 2014.002 v1.40 — distribuição, seções 3.4–3.7 e 3.11.4](https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=uWO2d%2FgTuWg%3D).
- [NT 2018.002 — consumo nos serviços autorizadores](https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=HAYP6dvLy7I%3D).
- [Atendimento da Receita Federal para NF-e](https://www.gov.br/receitafederal/pt-br/canais_atendimento/fale-conosco/sped/nf-e).
