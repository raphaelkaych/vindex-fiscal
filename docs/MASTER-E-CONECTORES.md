# Gestão master e conectores fiscais

**Complemento atual:** [recuperação parcial, indicadores, pendências e produção](NFSE-RECUPERACAO-PRODUCAO.md). No painel do cliente ou na supervisão master estão disponíveis `/indicadores/` e `/documentos/pendentes/`. Documentos parciais são visíveis, mas excluídos dos valores elegíveis.

## Ver o mesmo painel do cliente

Em `/gestao/`, clique em **Ver painel**. O endereço `/gestao/clientes/ID/painel/` reutiliza as views e templates do portal do cliente, incluindo visão geral, empresas, notas, agenda/CSV, boletos, documentos, certificados, captura e integrações. O menu mantém esse prefixo e seus filtros. A faixa de supervisão identifica cliente e administrador e permite voltar à gestão.

Esse modo é de leitura: não autoriza cadastro, upload, mudança de credenciais, alterações financeiras ou eventos fiscais. O bloqueio é aplicado no servidor, além da apresentação. Downloads e relatórios continuam vinculados ao cliente indicado na URL. Duas abas de clientes diferentes não mudam o contexto uma da outra; o login e a sessão permanecem do master. A API normal conserva seu escopo original.

**Operação e cadastros** mantém os controles administrativos explícitos de acesso/captura/API, separados da visualização do cliente. O acesso já criado para o master continua válido; não é preciso recriar sua conta.

Estado técnico e limites atuais: [GESTAO-E-DIAGNOSTICO.md](GESTAO-E-DIAGNOSTICO.md).

## Criar seu acesso no Windows

No terminal aberto na pasta do Vindex:

```powershell
py iniciar.py --preparar
.\.venv\Scripts\python.exe manage.py criar_admin_master
py iniciar.py
```

O primeiro comando instala/prepara sem iniciar consultas. O segundo solicita seu e-mail e senha no próprio terminal; a senha não aparece ao digitar. Não passe senha por argumento nem a envie no chat. Se a conta já existe, o comando exige digitar **CONCEDER** e informa que concederá o acesso master, ajustará o login para o e-mail e definirá nova senha. Contas ambíguas são recusadas. Não existe senha padrão ou promoção do primeiro usuário.

Entre em **http://127.0.0.1:8000/entrar/**; o master é direcionado a **http://127.0.0.1:8000/gestao/**. A permissão `portal.admin_master` dá supervisão, e `portal.operate_clients` permite ações operacionais. O comando concede ambas, sem transformar a conta em superusuário Django.

Em **Acessar painel do cliente**, a URL identifica o Workspace. Não há troca de usuário nem seleção de cliente guardada globalmente na sessão: abas distintas conservam seus contextos. O banner mostra o cliente e a identidade administrativa. A supervisão é de leitura; aprovar/suspender acesso web, pausar/retomar captura e revogar API são ações separadas, por POST/CSRF, com auditoria. Retomar não cria autorização fiscal e nenhuma ação master envia Ciência.

Para trocar a própria senha, use **Minha conta > Alterar senha**. Para recuperação local:

```powershell
.\.venv\Scripts\python.exe manage.py changepassword seu-email@dominio.com
```

Substitua `seu-email@dominio.com` pelo seu login master. A senha será solicitada de forma oculta, sem argumento. Em produção, `/recuperar-senha/` utiliza SMTP configurado; sem servidor de e-mail, mostra a pendência em vez de afirmar envio. Não houve envio de e-mail real nesta entrega.

## Cadastros e suspensão

`VINDEX_REGISTRATION_MODE` aceita `open`, `approval` e `closed`. Localmente o padrão é `open`; com `DEBUG=False`, é `approval`. Contas existentes permanecem ativas. Novas contas no modo de aprovação entram como pendentes e não podem usar o portal até aprovação do master. `closed` fecha o cadastro público; não implementa envio automático de convites.

Suspensão de acesso web não revoga uma credencial de API nem pausa a captura automaticamente. Esses controles independentes preservam histórico e tornam os efeitos explícitos. A API continua limitada ao Workspace e às empresas da credencial, mesmo que seu proprietário seja master.

## Certificado e rotina automática

1. Cadastre o CNPJ correto em **Minhas empresas**.
2. Vincule um A1 válido da mesma raiz, informando a senha somente na aplicação.
3. No formulário, autorize cada serviço desejado: NF-e, NFS-e nacional e/ou CT-e. **CT-e exige UF do estabelecimento**. Serviços desmarcados não recebem autorização pelo simples armazenamento do certificado.
4. Para um A1 já existente, use **Captura de NF-e** e **Minhas empresas > Conectores** para habilitar os serviços.
5. Acompanhe **Documentos consolidados**, com filtros por CNPJ e tipo, e a captura específica da empresa.

Depois dessa configuração, o worker consulta periodicamente e importa os documentos disponibilizados, sem depender de novos comandos por consulta ou de conversar com o desenvolvedor. Renovação preserva NSU, intervalos e documentos. Desmarcar um serviço na renovação pausa esse serviço. Os requisitos são conferidos antes de usar cada A1; revogação/aceitação efetiva depende também da origem governamental.

`py iniciar.py` inicia web e captura ou aproveita a tarefa Windows já ativa. Nesta máquina, **Vindex Fiscal - Captura** já está registrada e em execução. O uso local exige computador ligado, internet e a conta Windows conectada. Para instalar a tarefa em outra instalação preparada:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\configurar-captura-windows.ps1
Start-ScheduledTask -TaskName 'Vindex Fiscal - Captura'
```

O registro permite iniciar no logon; `Start-ScheduledTask` inicia neste logon. Não há comandos repetidos para cada CNPJ ou lote.

## Segunda empresa real

Não foi criada uma segunda empresa artificial. Após cadastrá-la, confira o ID na URL e execute, substituindo **12** pelo ID real:

```powershell
.\.venv\Scripts\python.exe manage.py diagnosticar_empresa --empresa 12
```

O diagnóstico é local e não consulta o governo. Verifica acesso ao A1 e requisitos; confira consentimento por conector na aplicação e aguarde a primeira resposta. NF-e, CT-e e ADN permitem a raiz compatível conforme suas regras; isso não permite consultar CNPJ de outra raiz. A disponibilidade real e os papéis de interesse continuam sendo decididos pela origem.

## Cobertura, originais e pagamento

- **NF-e:** importador modelo 55 e transporte existente preservados. Resumos e eventos ficam separados. Ciência exige autorização por chave na aplicação e não confirma operação.
- **NFS-e:** API **ADN Contribuintes**, com `cnpjConsulta` e lote, em mTLS. Importação prioriza documentos em que o CNPJ seja tomador. Emissões municipais não compartilhadas com o ADN exigem outro conector; não há integração municipal universal. O manual consultado não estabelece uma janela histórica universal para prometer ao usuário.
- **CT-e:** distribuição nacional por NSU, CT-e completo modelo 57 padrão, papéis de interesse declarados. A NT prevê até três meses após recepção nacional. CT-e OS, GTV-e e CT-e simplificado não recebem importação como modelo 57 padrão.
- Cada serviço tem configuração, cursor, reserva, espera, resposta privada e entrega por cliente separados. A espera da NF-e não bloqueia CT-e ou NFS-e. O mesmo CNPJ/serviço/ambiente é coordenado internamente, sem entregar documentos a outro Workspace sem autorização e A1 próprio válido.
- **XML** é sempre o original recebido. **DANFE** é para NF-e; **DACTE**, para CT-e. **NFS-e tem PDF de conferência** gerado do XML validado, inclusive no master, identificado como espelho e sem arredondamentos adicionais. Não substitui o DANFSe oficial nem o XML. Nenhum desses arquivos confirma pagamento ou situação fiscal atual. Se a geração fiel não for possível, o XML permanece disponível. As [atualizações oficiais](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/atualizacoes-e-implantacoes) registram a desativação da antiga API ADN de DANFSe em 03/08/2026, após prorrogações. A recuperação automática de PDF oficial ainda depende de adaptador homologado; o PDF de conferência não assume esse nome.
- Eventos de cancelamento recebidos pelos novos conectores são preservados e identificados. CT-e exige retorno aceito correspondente; não altera pagamentos ou parcelas automaticamente. Eventos não são emitidos pelos novos conectores.

**Dados de pagamento do documento** mostram campos estruturados e candidatos explicitamente rotulados no texto, com fonte, método, trecho e necessidade de revisão. Fatura, duplicatas, vencimentos, meios/valores declarados, retenções e instruções são exibidos quando presentes. Agência, conta, beneficiário, Pix e código de cobrança não são deduzidos de números soltos. Dados de adquirente/cartão não viram conta do fornecedor. Sem informação: **Não informado no documento**.

As previsões existentes de NF-e continuam baseadas nas duplicatas e revisões. A captura dos outros tipos não inventa parcelas nem soma referências entre documentos. Não há confirmação bancária, consulta a URLs/QR de pagamento, DDA, execução de pagamentos ou OCR.

## API

As credenciais existentes e seus escopos permanecem. Novas leituras:

```text
GET /api/v1/documentos-fiscais/?service=nfse&company=12
GET /api/v1/documentos-fiscais/?service=cte&company=12
GET /api/v1/documentos-fiscais/{id}/
GET /api/v1/documentos-fiscais/{id}/xml/
GET /api/v1/conectores/?company=12
GET /api/v1/capturas-nfe/?company=12
```

Os detalhes de NF-e incluem `payment_evidence`; os novos documentos incluem `payment_data`. Valores financeiros são strings decimais; dados extraídos preservam o texto declarado. A API não habilita captura nem envia eventos. Swagger atualizado: **http://127.0.0.1:8000/api/v1/docs/**. Consulte também [API.md](API.md).

## Demonstrações e verificação

Os botões e endpoints de carregar exemplos foram retirados do uso normal. Notas marcadas `is_demo` não entram nas listagens, totais ou downloads normais. Empresas comprovadamente ligadas somente a notas/certificados de demonstração são ocultadas das listagens operacionais, sem classificação por nome e sem apagar banco ou auditoria. Não houve limpeza destrutiva. Fixtures continuam em banco de testes isolado.

```powershell
py iniciar.py --testar
.\.venv\Scripts\python.exe manage.py verificar_captura
.\.venv\Scripts\python.exe manage.py spectacular --file docs/openapi.yaml --validate
```

Para produção e migração protegida, veja [IMPLANTACAO.md](IMPLANTACAO.md). Resultados reais e limitações da conferência estão em [ENTREGA-CONECTORES-MASTER.md](ENTREGA-CONECTORES-MASTER.md).
