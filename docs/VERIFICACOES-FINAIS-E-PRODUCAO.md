# Verificações finais e preparação para publicação — 23/10/2026

## Entregas

- Pesquisa em Documentos consolidados por empresa, participantes, número/série/chave, tipo/ambiente, emissão/período, valores e situação informada. Busca em produtos/serviços/códigos, NCM e CFOP; múltiplos critérios de item precisam corresponder à mesma linha.
- Índice reconstruível alimentado pelas importações existentes, preservando XML, histórico e isolamento. Normalização de acentos/maiúsculas sem modificar o texto original. Migrações aditivas `0017`/`0018`; preenchimento local retomável.
- Excel `.xlsx` dos mesmos filtros, com documentos, itens individualizados, fornecedor, empresa, período e critérios. Datas/valores tipados; identificadores como texto; conteúdo externo sem fórmulas; números extensos preservados em texto quando excedem a precisão numérica do Excel. Sem dependência adicional no servidor para gerar o arquivo.
- Indicadores com rosca/legenda, barras e linha SVG, destaque por foco/mouse, informações dos pontos, acesso aos documentos do mês, comparação de quantidades com período anterior e movimentos que respeitam redução de animação. Valores fiscais continuam separados de pagamentos e entre tipos/ambientes.
- Status da captura mostra a próxima tentativa considerando o intervalo/bloqueio compartilhado. Distingue última operação de recuperação e última distribuição; 656 é apresentado como limitação com retomada agendada, sem declarar bloqueio definitivo ou sucesso geral por um XML pontual.
- Perfil Linux `config.production`, PM2 com web/captura/backup em processos separados, diretórios persistentes, Gunicorn em loopback, Nginx/HTTPS, ambiente privado e logs sem traceback fiscal. Um único worker, sem cluster/watch.
- Snapshot SQLite cifrado e verificado via API de backup (compatível com WAL), restauração somente para destino inexistente, backup diário supervisionado e build com cópia anterior à migração. Biblioteca SQLite privada com pacote/hash oficial e proteção contra versões sem a correção WAL-reset.
- Integração contínua preparada para testes, build e reinício PM2 em Linux, com banco vazio e sem certificados reais. Não efetua deploy nem consulta o fisco.
- Incluídas também as entregas anteriores ainda locais: recuperação oficial por chave, retomada controlada após 656, exclusão específica de conta com confirmação e retenção das filas/auditoria globais. O gerenciamento rotineiro de cadastro não passou a permitir cascata indiscriminada.

## Conferência local

- `python iniciar.py --testar`: **461 testes, 458 aprovados e três ignorados por dependerem de PostgreSQL real**. Após a última proteção de precisão Excel, 13 testes focados de pesquisa/exportação aprovados.
- `manage.py check`, `makemigrations --check --dry-run`, `pip check`, sintaxe Node dos scripts, sintaxe Bash dos scripts de instalação/CI e leitura do YAML.
- Arquivo Excel conferido por leitor independente (`openpyxl`, somente na conferência), incluindo abas, datas, textos, filtros, congelamento e ausência de fórmulas originadas dos documentos.
- Conferência HTTP de documentos, indicadores, captura, NFS-e, CT-e e exportação no acesso normal/master; downloads de XML/DANFE das notas recuperadas. Esses testes não equivalem a inspeção visual em navegador real.
- SQLite real: `quick_check=ok`, nenhuma violação de chave estrangeira na auditoria. Backups anteriores às migrações criados e autenticados. Restauração sobre o banco real não foi executada; testes de restauração usam banco descartável.
- Investigação das entradas fiscais realizada inicialmente por logs/banco/código, sem novas chamadas de teste. O worker autorizado permaneceu seguindo a agenda persistida. Resultados e dados da empresa piloto ficam no relatório privado e na própria aplicação, fora do GitHub.

## Situação para publicação

O código e o roteiro de transferência estão preparados; **não há declaração de homologação irrestrita de produção**. Confira o resultado efetivo da execução Linux em GitHub Actions e execute o checklist de [LINUX-PM2.md](LINUX-PM2.md) no servidor escolhido. Boot real, domínio/TLS público, SMTP, carga, permissões, cópia externa de backup e nova emissão real em outro cliente dependem dessa etapa.

SQLite serve ao piloto em um servidor com disco local e concorrência moderada, sujeito a medição. Não foi estabelecida capacidade para uma carteira arbitrária nem para múltiplos servidores. O perfil PostgreSQL permanece disponível; seus três testes de concorrência continuam pendentes de ambiente real.

Uma recuperação aceita por chave conhecida não garante todas as notas do período nem elimina a pendência de distribuição sequencial com 656. Conferir consumidores externos com a empresa/contador e eventual suporte oficial continua necessário quando a rejeição persiste. A captura automática exige certificado válido, autorizações/configurações do serviço, conta/empresa elegíveis e worker ativo. NFS-e municipal fora do ADN, NFC-e e DDA continuam sem integração; PDFs locais não são apresentados como PDFs oficiais recuperados.

## Usar no Windows

```powershell
py iniciar.py
```

O inicializador prepara o ambiente, migrações e processos locais; a tarefa independente já ativa é reaproveitada. Depois de atualizar uma cópia existente, execute `indexar_documentos` caso haja aviso de índice pendente; nesta instalação a indexação já foi realizada. Abra `/documentos/`, `/indicadores/` e `/gestao/`. Para criar/conceder master explicitamente: `.\.venv\Scripts\python.exe manage.py criar_admin_master` (senha interativa, não informada por argumento).

Guias: [filtros e Excel](PESQUISA-FISCAL-E-EXCEL.md), [transferência/PM2/backup/HTTPS](LINUX-PM2.md), [recuperação por chave e exclusão](RECUPERACAO-POR-CHAVE-E-EXCLUSAO.md).
