# Instalação Linux com PM2 e SQLite persistente

Este roteiro prepara uma implantação futura. Não houve deploy a partir desta entrega. O perfil PM2 usa Django/Gunicorn, um worker de captura e um processo de backup. Não existe frontend Node separado; Node é usado pelo PM2. O roteiro Docker/PostgreSQL anterior permanece em `IMPLANTACAO.md`.

## 1. Servidor e diretórios

Exemplo para Ubuntu/Debian, com Node.js LTS instalado por um método oficial. Ajuste o domínio e o IP. Execute como administrador somente a preparação de pacotes/diretórios:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-dev build-essential tcl-dev curl nginx redis-server git
sudo npm install -g pm2@6
sudo useradd --system --create-home --shell /bin/bash vindex
sudo install -d -o vindex -g vindex -m 750 /opt/vindex /etc/vindex
sudo install -d -o vindex -g vindex -m 700 /var/lib/vindex/data /var/lib/vindex/runtime /var/backups/vindex
sudo install -d -o vindex -g www-data -m 750 /var/lib/vindex/static
sudo systemctl enable --now redis-server
sudo -iu vindex
git clone https://github.com/raphaelkaych/vindex-fiscal.git /opt/vindex/app
cd /opt/vindex/app
cp deploy/pm2.env.example /etc/vindex/vindex.env
chmod 600 /etc/vindex/vindex.env
nano /etc/vindex/vindex.env
```

Preencha domínio, origens CSRF, SMTP e **as chaves originais do computador**. Não gere outra `CERTIFICATE_ENCRYPTION_KEY`: os A1 existentes dependem dela. Transfira os valores por canal privado, sem terminal compartilhado, chat, Git, captura de tela ou histórico de comandos. Não transfira `.venv`, caches, `tmp` nem o `.env` local para o repositório. O usuário `vindex` precisa ler o ambiente; o Nginx só precisa ler os estáticos.

Use Python 3.13 ou posterior compatível com as dependências. Confira a biblioteca SQLite efetivamente carregada pelo Python, não apenas a versão do programa `sqlite3`. O perfil recusa versões sem a correção oficial WAL-reset. Se necessário, o script abaixo instala uma biblioteca SQLite privada 3.54.1 com SHA3 conferido contra o pacote oficial, sem substituir a biblioteca do sistema:

```bash
cd /opt/vindex/app
bash deploy/install-sqlite.sh
export LD_LIBRARY_PATH=/opt/vindex/sqlite/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
python3 -c "import sqlite3; print(sqlite3.sqlite_version)"
```

PM2 já passa esse caminho aos três processos. Se personalizar o prefixo, exporte `VINDEX_SQLITE_LIB_DIR` antes da instalação e do `pm2 start`. A compilação exige rede HTTPS, compilador e `make`; falha de checksum interrompe a instalação. Se usar uma biblioteca da distribuição com backport de segurança e numeração diferente, valide o backport com o fornecedor; não remova a proteção só para iniciar o sistema.

## 2. Transferência segura da instalação atual

**Nunca mantenha Windows e Linux consultando ao mesmo tempo com bancos separados.** Antes da cópia final, feche o `py iniciar.py`, pare a tarefa de captura no Windows e confirme que não existe requisição em andamento. Preserve os intervalos, NSUs, autorizações e a hora do servidor (NTP).

No PowerShell, na pasta do projeto:

```powershell
Stop-ScheduledTask -TaskName 'Vindex Fiscal - Captura'
# Feche também o terminal que estiver executando py iniciar.py.
.\.venv\Scripts\python.exe manage.py verificar_captura
.\.venv\Scripts\python.exe manage.py backup_sqlite --criar --arquivo C:\Users\user\VindexBackups\transferencia-linux.vdb
.\.venv\Scripts\python.exe manage.py backup_sqlite --verificar --arquivo C:\Users\user\VindexBackups\transferencia-linux.vdb
scp C:\Users\user\VindexBackups\transferencia-linux.vdb SEU_USUARIO@IP_DO_SERVIDOR:/PASTA_PRIVADA/
```

O nome do backup precisa ser novo. Copie o arquivo para `/var/backups/vindex/transferencia-linux.vdb` no servidor, com dono `vindex` e modo 600. Ele contém banco, XMLs, histórico e A1 cifrados; **a chave de cifra é transferida separadamente**. O snapshot usa a API oficial de backup SQLite, incluindo transações do WAL. Não copie apenas `dados.sqlite3` enquanto algum processo escreve e não descarte os arquivos `-wal`/`-shm` manualmente.

`Stop-ScheduledTask` pode deixar um Python filho ativo. Se `verificar_captura` continuar mostrando atividade, confira os processos desta pasta e encerre o worker correspondente depois da operação corrente. Não inicie o consumidor Linux antes de confirmar a parada do Windows. O comando de saúde pode levar até 90 segundos para reconhecer um heartbeat antigo; ele não deve ser usado como único comprovante de que uma requisição em andamento terminou.

No Linux, como `vindex`, antes de instalar/buildar um banco vazio:

```bash
cd /opt/vindex/app
python3 -m venv .venv
.venv/bin/pip install -r requirements-production.txt
export DJANGO_SETTINGS_MODULE=config.production
export VINDEX_ENV_FILE=/etc/vindex/vindex.env
export LD_LIBRARY_PATH=/opt/vindex/sqlite/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
.venv/bin/python manage.py backup_sqlite --verificar --arquivo /var/backups/vindex/transferencia-linux.vdb
.venv/bin/python manage.py backup_sqlite --restaurar --arquivo /var/backups/vindex/transferencia-linux.vdb --destino /var/lib/vindex/data/dados.sqlite3
bash deploy/install-linux.sh
```

A restauração só aceita arquivo de destino **inexistente**. Se um banco já existe, preserve-o e restaure para outro caminho; não o apague nem o substitua para facilitar a operação. O build faz snapshot prévio quando encontra banco existente, executa verificações Django, migrações, indexação local e coleta de estáticos. Não cria clientes ou certificados e não consulta o fisco. Confirme as contagens com `manage.py conferir_dados` antes e depois; o comando pode mostrar dados privados, portanto guarde sua saída fora de logs públicos.

Após `collectstatic`, como administrador, permita ao Nginx ler somente os estáticos:

```bash
sudo chgrp -R www-data /var/lib/vindex/static
sudo find /var/lib/vindex/static -type d -exec chmod 750 {} \;
sudo find /var/lib/vindex/static -type f -exec chmod 640 {} \;
```

## 3. HTTPS, domínio e inicialização

Prepare DNS e certificado HTTPS (por exemplo, Certbot). Edite `deploy/nginx-pm2.conf` com o domínio e caminhos reais. Depois instale a configuração no Nginx, execute `sudo nginx -t` e recarregue o serviço. Abra somente SSH, 80 e 443 no firewall; Gunicorn escuta em `127.0.0.1:8000` e Redis deve escutar somente localmente. Não exponha o arquivo de ambiente, dados, backups ou runtime pelo proxy. O proxy substitui `X-Forwarded-Proto`, sem confiar nesse cabeçalho vindo da internet.

Como `vindex`:

```bash
cd /opt/vindex/app
pm2 start ecosystem.config.js
pm2 status
pm2 logs --lines 40
pm2 save
pm2 startup
```

Execute **exatamente o comando com sudo que o `pm2 startup` imprimir**, incluindo usuário e diretório dele. Depois volte ao usuário `vindex` e execute `pm2 save`. Isso instala a retomada no boot. Não execute os processos da aplicação como root. Não use `pm2 scale`, cluster ou `watch` para a captura. A trava persistente fica em `/var/lib/vindex/runtime/capture-worker.lock`; o banco também reserva cada CNPJ/ambiente/serviço. O polling local não significa chamada fiscal a cada 15 segundos.

```bash
curl --fail http://127.0.0.1:8000/saude/
.venv/bin/python manage.py verificar_captura
.venv/bin/python manage.py verificar_producao --estrito
# Somente se precisar criar/conceder master: pergunta e-mail e senha sem exibi-la.
.venv/bin/python manage.py criar_admin_master
```

Acesse `https://SEU_DOMINIO/entrar/`, depois `/gestao/`. Use **Ver painel** para supervisionar um cliente em leitura, com escopo/auditoria por URL. Configuração completa não substitui validação de DNS, SMTP, TLS, carga e nova emissão real.

## 4. Operação, atualização e backups

```bash
pm2 status
pm2 logs vindex-captura --lines 80
pm2 logs vindex-backup --lines 40
pm2 restart vindex-web
pm2 restart vindex-captura
```

O processo `vindex-backup` cria snapshot cifrado e autenticado ao iniciar e a cada 24 horas. Falha provoca saída com erro e reinício supervisionado. Preserve a chave original em cofre separado e copie os backups cifrados para armazenamento externo; uma cópia no próprio servidor não cobre perda do disco. Não há eliminação automática de backups nesta entrega: monitore espaço e defina retenção conforme suas obrigações. Instale `deploy/vindex-logrotate` em `/etc/logrotate.d/vindex` para rotacionar logs; ajuste o usuário se necessário. Logs operacionais omitem XMLs, payloads, senhas e tracebacks fiscais.

Para atualizar código, **espere a consulta corrente terminar**, pare os três processos, salve backup, atualize e faça o build. O limite de encerramento do PM2 permite finalização de operação em andamento; mantenha o cursor e intervalos do banco:

```bash
pm2 stop ecosystem.config.js
git pull --ff-only
bash deploy/install-linux.sh
pm2 restart ecosystem.config.js --update-env
pm2 save
```

Para ensaiar restauração, mantenha os processos parados e use um caminho inexistente de teste. Nunca aponte um worker para a cópia restaurada enquanto a instalação original estiver ativa. Compare integridade, contagens e abertura local do A1 antes da transferência definitiva.

## 5. Limites e conferência obrigatória

- SQLite é adequado para **piloto em um servidor, disco local, baixo volume de gravações concorrentes**, com WAL/FULL, timeout de 30 segundos e transações IMMEDIATE curtas. Tamanho do banco não é o único critério: meça latência, filas, disco e SQLITE_BUSY com a carga real. Não homologamos capacidade para uma quantidade arbitrária de clientes. PostgreSQL é a evolução indicada para múltiplos servidores e concorrência maior; não use SQLite em NFS/SMB.
- A instalação local foi testada no Windows. A integração contínua adicionada executa testes, build e PM2 em Linux **com banco vazio e sem certificados reais**. Veja o resultado em GitHub Actions; não confunda workflow preparado com execução aprovada. O smoke de PM2 reinicia processos, não testa boot do servidor nem TLS público.
- Valide cadastro/aprovação, login/recuperação por SMTP, tenant e supervisão master; pesquise documentos/itens e abra o Excel; confira XML/PDF de cada tipo suportado; confira temas, teclado e celular no navegador real.
- Confira o heartbeat, última consulta, próximo horário, respostas e documentos de cada conector. Um 656 exige espera e investigação do cursor/consumidores; recuperação pontual aceita não prova distribuição completa. Não resetar NSU, trocar A1/IP ou enviar manifestações para tentar desbloquear.
- Confirme uma nova emissão real em outra empresa autorizada e o retorno após reinício. Resumos podem depender de autorização fiscal específica; a plataforma não envia eventos automaticamente. NFS-e fora do ADN/nacional depende de conector municipal; PDF local não é um PDF oficial recuperado. NFC-e e DDA não possuem integração.

Fontes: [PM2/ecosystem](https://pm2.keymetrics.io/docs/usage/application-declaration/), [PM2/boot](https://pm2.keymetrics.io/docs/usage/startup/), [Django/SQLite](https://docs.djangoproject.com/en/5.2/ref/databases/#sqlite-notes), [SQLite/WAL e correção](https://www.sqlite.org/wal.html), [pacote SQLite e SHA3](https://www.sqlite.org/download.html).
