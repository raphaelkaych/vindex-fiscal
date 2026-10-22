# Implantação preparada, sem publicação automática

**Complemento:** [gestão e preparação PostgreSQL](GESTAO-CADASTROS-656-POSTGRES.md), com configuração `config.postgres_test_settings` restrita a banco de homologação e testes reais de concorrência ainda pendentes de execução nesse backend. A migração 0014 acrescenta o estado lógico de empresa; exportação/restauração preserva esse campo.

Antes de iniciar, leia a [revisão final de 22/10/2026](REVISAO-FINAL-E-PUBLICACAO.md): contém bloqueios obrigatórios, estado real por serviço, dimensionamento inicial e limitações verificadas. O código está preparado para homologação; isso não significa publicação aprovada ou captura NF-e normalizada.

Receita escolhida: **servidor Linux com Docker Compose**, PostgreSQL 17, Redis 7, Gunicorn e Nginx atrás de um terminador HTTPS confiável. O funcionamento local no Windows permanece. Não houve contratação, publicação externa, execução do Docker ou migração real para PostgreSQL nesta máquina; Docker não está instalado aqui.

## Preparar o servidor

Copie somente o código. `.dockerignore` impede incluir .env, bancos, documentos, certificados, .venv e arquivos temporários no contexto da imagem. Não envie esses dados pelo GitHub.

Copie `deploy/.env.production.example` para `deploy/.env.production` e preencha no servidor privado. Preserve **CERTIFICATE_ENCRYPTION_KEY original** para abrir os A1 existentes. Não gere outra chave no deploy. Configure segredo Django, domínio, origens CSRF, senhas iguais em PGPASSWORD/POSTGRES_PASSWORD e SMTP. O exemplo não contém segredos.

No Linux, com Docker Engine e Compose disponíveis, a partir da pasta do projeto:

```sh
docker compose -f deploy/compose.yaml build
docker compose -f deploy/compose.yaml up -d db redis
docker compose -f deploy/compose.yaml run --rm web python manage.py migrate
docker compose -f deploy/compose.yaml run --rm web python manage.py check --deploy
docker compose -f deploy/compose.yaml run --rm web python manage.py collectstatic --noinput
```

Web e captura usam o mesmo banco e a mesma chave privada de configuração. As reservas são persistentes por identidade/serviço/ambiente. Não inicie a captura nova enquanto a instalação antiga continuar consultando.

O Nginx interno escuta **127.0.0.1:8080** no host. Configure o domínio/HTTPS no proxy externo da infraestrutura antes de liberar acesso. O proxy externo deve apontar a esse endereço local. Não publique diretamente a porta interna nem aceite cabeçalhos de proxy arbitrários da internet. O exemplo Nginx substitui `X-Forwarded-Proto` e a aplicação só confia nesse cabeçalho quando `VINDEX_TRUST_PROXY=1`. PostgreSQL/Redis não possuem portas publicadas.

## Migrar dados existentes

Planeje janela de manutenção: encerre o portal local com Ctrl+C e pare a tarefa de captura. Aguarde consultas em andamento terminarem antes de parar o processo. Verifique também processos independentes iniciados manualmente; `Stop-ScheduledTask` pode não encerrar um processo Python filho imediatamente. Não rode as instalações antiga e nova como consumidores independentes do mesmo CNPJ.

Crie uma pasta privada fora do projeto, por exemplo **C:\VindexBackups**. Com os processos de escrita parados, no Windows:

```powershell
.\.venv\Scripts\python.exe manage.py conferir_dados > C:\VindexBackups\antes.json
.\.venv\Scripts\python.exe manage.py migrar_dados_protegidos --exportar --arquivo C:\VindexBackups\migracao.vfx
```

O primeiro comando gera somente contagens e hashes de identidades/vínculos, verificando abertura dos certificados sem exibir segredo. O segundo exporta os registros cifrados com a chave original para fora do projeto; não substitui arquivo existente. Sessões são excluídas, exigindo novo login. Notas, histórico, usuários/permissões, credenciais de API protegidas, certificados cifrados, autorizações e cursores são preservados.

Transfira o backup cifrado por canal privado e a chave por canal separado; não os coloque no repositório. Copie o backup para um contêiner web de preparação (ainda sem captura ativa):

```sh
docker compose -f deploy/compose.yaml run --rm -v /caminho/privado:/backup:ro web python manage.py migrar_dados_protegidos --importar --arquivo /backup/migracao.vfx --confirmar-banco-vazio
docker compose -f deploy/compose.yaml run --rm web python manage.py conferir_dados
```

Novas exportações usam VFX2: JSONL cifrado em blocos autenticados, com identificação, ordem e verificação integral antes da carga. Datas preservam microssegundos para não reduzir esperas fiscais. Não há a antiga limitação global de 512 MB para esse formato; o consumo é por registro/bloco, mas o volume real precisa de ensaio de desempenho e espaço temporário privado. Backups legados continuam sujeitos ao limite antigo.

O comando de importação recusa banco com usuários/registros da aplicação. Faz carga transacional e restaura relações com migrações/permissões já preparadas. Usa arquivo temporário privado fora do código e o remove ao terminar. O teste de restauração usa somente banco descartável e dados fictícios; não houve restauração sobre os dados reais.

Compare o resultado com `antes.json`: contagens, hashes de IDs e vínculos, e zero falhas de abertura dos certificados. Confira amostras privadas no painel correto, previsões, autorizações, NSUs e intervalos. Só então:

```sh
docker compose -f deploy/compose.yaml up -d web capture proxy
docker compose -f deploy/compose.yaml exec web python manage.py verificar_captura
docker compose -f deploy/compose.yaml exec web python manage.py verificar_producao --estrito
```

No banco importado, use sua conta existente. Para criar um master novo num banco sem master:

```sh
docker compose -f deploy/compose.yaml run --rm web python manage.py criar_admin_master
```

Não envie senha por argumento. A concessão é interativa e auditada.

## Supervisão, backup e recuperação

Compose reinicia os processos encerrados com `restart: unless-stopped`. A captura tem healthcheck de banco/heartbeat; falha persistente deve gerar alerta na infraestrutura. Um contêiner `unhealthy` precisa de acompanhamento: healthcheck sozinho não reinicia um processo travado. Endpoint `/saude/` retorna somente prontidão do banco, sem dados de clientes. Não equivale a sucesso fiscal.

```sh
docker compose -f deploy/compose.yaml ps
docker compose -f deploy/compose.yaml logs --tail 100 capture
docker compose -f deploy/compose.yaml exec web python manage.py verificar_captura
```

Os logs operacionais não imprimem XML/A1/senhas/tokens. Respostas oficiais ficam no banco privado. Não habilite log de parâmetros SQL ou corpos HTTP em produção. Access log do proxy está desligado no exemplo. Faça retenção protegida dos logs da infraestrutura.

Para backups periódicos, pause escritas durante exportação lógica protegida ou use snapshot/`pg_dump` consistente do PostgreSQL e cifre o arquivo fora do código. Guarde chaves separadamente e teste restauração em banco novo. A restauração de produção e os controles PostgreSQL/concorrência devem ser homologados no servidor escolhido antes de receber clientes externos.

O SMTP é necessário para recuperação por e-mail. Configure domínio/remetente e faça teste real de entrega. Enquanto não configurado, a aplicação mostra a causa; o administrador local pode executar `manage.py changepassword` interativamente. Cadastro público em produção fica sujeito à aprovação por padrão. Não use runserver como servidor de produção.

## Roteiro de homologação da infraestrutura

1. `check --deploy` sem erros; HTTPS/cookies/CSRF/domínio e estáticos conferidos.
2. Manifestos de migração iguais; certificados abrem com a chave preservada; rollback disponível.
3. Master e usuário comum testados, inclusive duas abas de supervisão, API e downloads privados.
4. Reinício de web/captura/host retoma a fila, sem duplicação ou redução de espera.
5. Leases/CAS testados com dois processos em PostgreSQL e contas de serviços restritas.
6. Alertas para processo parado, certificado vencido, rejeição/erro recorrente e backup sem restauração recente.

Fontes: [Django — publicação](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/), [Django — bancos e transações SQLite](https://docs.djangoproject.com/en/5.2/ref/databases/), [Docker Compose — serviços](https://docs.docker.com/reference/compose-file/services/).
