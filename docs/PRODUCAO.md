# Preparação para produção

Receita executável desta etapa: [IMPLANTACAO.md](IMPLANTACAO.md), com Docker Compose, web/captura separados, cadastro por aprovação, backup cifrado e validação de migração. Preserve a chave original dos A1. Não houve publicação nem homologação PostgreSQL real nesta máquina.

A aplicação continua preparada para uso local. O transporte SEFAZ e o worker estão implementados, com consulta piloto real e importação de XML documentadas em [INTEGRACAO-SEFAZ.md](../INTEGRACAO-SEFAZ.md). PostgreSQL e Redis são configuráveis, mas não houve implantação pública nem validação desta instalação nesses serviços. DDA e operações bancárias continuam sem integração.

## Ambiente local preservado

`py iniciar.py` instala dependências, aplica migrações aditivas e inicia o portal em 127.0.0.1 e o worker de captura das empresas com leitura autorizada. O inicializador supervisiona o worker e o reinicia se encerrar inesperadamente; Ctrl+C encerra os processos. O progresso e os consentimentos ficam no banco. `py iniciar.py --testar` executa a suíte sintética, sem iniciar o worker. SQLite e cache local continuam sendo os padrões. No Windows, o inicializador usa a implementação Python do PyYAML quando precisar compilar a dependência; não é necessário instalar Visual C++ para ela. Não há novas chaves obrigatórias em `.env` para usar API e boletos locais.

## Captura e operação contínua

No uso local, mantenha o terminal de `py iniciar.py` aberto. Vincular um certificado válido e autorizar a captura de leitura na empresa agenda automaticamente a primeira consulta. Renovar o A1 de uma captura autorizada retoma os requisitos e o agendamento, sem reiniciar NSU nem antecipar o intervalo permitido. Retomar a aplicação também retoma a fila.

Para executar apenas a captura local, preservando o preparo feito pelo inicializador:

```powershell
py iniciar.py --capturar
```

Em uma implantação com servidor WSGI/ASGI próprio, configure o worker como um processo separado e supervisionado, com o mesmo banco e acesso protegido às configurações e à chave Fernet. Depois do preparo e das migrações, o comando é:

```powershell
.\.venv\Scripts\python.exe manage.py capturar_sefaz --interval 15 --limit 20
```

`--interval` regula a verificação local da fila. Os prazos efetivos da SEFAZ permanecem no banco: esse comando não consulta o governo a cada 15 segundos para um CNPJ em espera. A paginação disponível é processada respeitando o cursor e os limites. O worker não envia manifestações fiscais.

No Windows, um serviço ou tarefa do Agendador de Tarefas pode manter esse comando em execução e reiniciá-lo em caso de falha. Configure a pasta do projeto como diretório inicial e use a conta de serviço que possui acesso ao banco e às configurações protegidas. Teste o início após reiniciar o Windows e a parada/reinicialização do worker. Sem um processo ativo, a autorização permanece salva, mas nenhuma nova consulta é realizada. O worker contínuo atualiza a cada 10 segundos um sinal local atômico em `tmp/capture-heartbeat.json`, contendo somente PID e horário. O painel considera o sinal recente por até 90 segundos e distingue processo em execução de processo parado, sem confundir esse sinal com uma resposta oficial da SEFAZ. Uma consulta `--once` não anuncia execução contínua. O sinal é local à pasta da aplicação; não substitui alertas centralizados nem monitoramento de múltiplas máquinas.

O cursor, o cooldown e o lease são compartilhados internamente por CNPJ/ambiente para evitar consumidores simultâneos mesmo quando o CNPJ aparece em mais de um Workspace. A entrega local exige consentimento e certificado válido de cada empresa autorizada; a interface nunca expõe a caixa de documentos de outro cliente. Essa coordenação cobre a instalação e seu banco. Softwares externos e instalações com bancos independentes precisam coordenar sequência e intervalos por outro meio.

O transporte usa endpoints oficiais fixos, A1 do armazenamento cifrado, mTLS e validação do servidor com TLS 1.2 ou superior. `SEFAZ_EXTRA_CA_FILE` permite indicar um arquivo de autoridades adicionais quando a cadeia do ambiente exigir; use somente autoridades conferidas a partir de fonte oficial e mantenha a configuração sob controle técnico. Um erro de confiança deve ser corrigido na cadeia, sem desativar a verificação TLS. A chave temporária exigida pela biblioteca é cifrada, escrita em diretório privado e removida antes da conexão. Nunca encaminhe certificado, senha, chave Fernet ou arquivo privado de autenticação para logs.

Ciência da Emissão exige sessão do proprietário, CSRF e autorização específica por documento na aplicação. É um evento real, separado da leitura e sem confirmação da operação. Confirmação da Operação, Desconhecimento e Operação não Realizada continuam sem envio implementado. A manifestação conclusiva e seus prazos exigem acompanhamento fiscal próprio.

## PostgreSQL opcional

Instale as dependências opcionais no ambiente Python do servidor:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-production.txt
```

Configure em um gerenciador de segredos ou ambiente protegido: `VINDEX_DB_ENGINE=postgresql`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `PGHOST`, `PGPORT` (padrão 5432) e `PGSSLMODE` (padrão require). O servidor deve possuir PostgreSQL provisionado e autorizado. Para SQLite use `VINDEX_DB_ENGINE=sqlite` ou omita a variável.

Mudar a variável seleciona outro banco, **não transfere os dados existentes**. Não troque o banco de uma instalação com clientes sem planejar backup, migração de dados, validação e restauração. Novas migrações devem ser aplicadas com `manage.py migrate` no banco escolhido. Não envie dumps, documentos, `.env` ou certificados ao repositório.

## Cache e limites

Produção com vários processos exige cache compartilhado. `VINDEX_REDIS_URL` ativa o backend Redis mantido pelo Django e deve apontar a um serviço privado/autenticado. Não coloque a URL com senha em logs. Sem a variável, os limites da API/login são locais ao processo; não há proteção distribuída garantida. Os throttles são limites operacionais, não proteção completa contra ataques; configure também limites de tamanho, frequência e tempo no proxy.

## HTTP e credenciais

Defina `DJANGO_DEBUG=0`, `DJANGO_ALLOWED_HOSTS` explícitos, HTTPS, servidor WSGI/ASGI adequado e armazenamento persistente. A API exige HTTPS com DEBUG=False e não usa cookies de sessão como autenticação. Nunca desative essa exigência para resolver erros de proxy. O proxy precisa encaminhar corretamente a informação de conexão segura; configure `SECURE_PROXY_SSL_HEADER` somente após definir um proxy confiável que remova cabeçalhos enviados pelo consumidor. A base não confia nesses cabeçalhos por padrão.

O esquema e Swagger/ReDoc são públicos e contêm somente contratos, sem documentos de clientes. Seus arquivos JavaScript/CSS vêm de `drf-spectacular-sidecar` local, sem CDN; use `collectstatic` na publicação. A interface do portal mantém tema claro/escuro. Não foi habilitado CORS: a API destina-se inicialmente a integração servidor a servidor. Se necessário no futuro, defina origens explícitas após análise.

Credenciais opacas são geradas individualmente, têm validade/escopos/empresas e guardam apenas hash PBKDF2 do segredo. O proprietário pode revogar ou emitir outra. A criptografia A1 é independente. O cabeçalho Authorization, corpos e segredos não devem entrar em access logs/APM; o filtro de erros da aplicação adiciona proteção, mas não configura os logs do proxy/infraestrutura.

## Antes de atender clientes externos

Validar isolamento e concorrência em PostgreSQL, limites com cache compartilhado, upload sob carga e timeouts, backup e restauração (incluindo a chave Fernet protegida), TLS, monitoramento, gestão de acesso ao admin global e política de retenção. Revise dependências e execute `manage.py check --deploy` com o ambiente de produção. Recuperação de senha por e-mail, validação de e-mail e múltiplos responsáveis por cliente continuam fora desta entrega.

O piloto de distribuição real não substitui a validação de todos os cenários fiscais e da infraestrutura de produção. Monitore última tentativa/resposta, cStat/xMotivo, impedimentos de importação, validade dos A1, fila, falhas repetidas e intervalos. Teste recuperação entre o recebimento durável e a entrega dos documentos, sem repetir a consulta nem cruzar clientes. Revise também a coordenação com outros consumidores do mesmo CNPJ. DDA permanece ausente. As regras vigentes, fontes e limites da captura estão em [INTEGRACAO-SEFAZ.md](../INTEGRACAO-SEFAZ.md).

Fontes: [bancos no Django 5.2](https://docs.djangoproject.com/en/5.2/ref/databases/), [cache Redis do Django](https://docs.djangoproject.com/en/5.2/topics/cache/#redis), [checklist de publicação](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/), [configuração mantida do PyYAML](https://github.com/yaml/pyyaml/blob/6.0.3/setup.py).
