# Tutorial e refinamento dos filtros

## Uso

O menu lateral agora tem **Como usar o Vindex** (`/tutorial/`), com primeiros passos, empresas, certificado, captura, XML/PDF, pesquisa, Excel, indicadores, agenda, boletos, API, conta e dúvidas frequentes. O master também vê orientações de gestão e supervisão. Os filtros têm links diretos ao assunto correspondente no guia.

Em **Documentos consolidados**, os campos mais usados aparecem primeiro: empresa, tipo, produto/serviço e período. **Mais filtros** organiza documento, participantes e itens/valores. O refinamento abre automaticamente quando há campos preenchidos ou erros. Campos inválidos mantêm os valores informados e recebem mensagem junto ao rótulo.

Depois de pesquisar, as escolhas aplicadas aparecem em etiquetas removíveis. Cada etiqueta remove somente o filtro escolhido e preserva os demais; a paginação é reiniciada. **Exportar estes resultados** fica no cabeçalho da lista e usa os filtros já aplicados, sem confundir escolhas ainda não enviadas no formulário com o resultado atual.

Em **Indicadores fiscais**, empresa/tipo/ambiente e período têm grupos próprios. Os atalhos **Este mês**, **Últimos 30 dias** e **Este ano** mantêm empresa, tipo e ambiente já aplicados. Campos manuais continuam usando o botão **Atualizar indicadores**.

## Visual e acesso

Os componentes usam os tokens existentes nos temas claro/escuro, a tipografia do sistema, ícones SVG e foco visível. Os campos se reorganizam no celular, com datas em uma coluna em telas estreitas; as tabelas continuam com rolagem interna. A expansão de filtros e as dúvidas usam controles HTML nativos, acessíveis por teclado e sem dependência adicional. Movimentos discretos respeitam redução de movimento.

O tutorial exige autenticação, aceita somente leitura e mantém o cliente da URL durante a supervisão master. Não cria autorizações, não executa consultas fiscais e não amplia o escopo da API. Links de importação ficam ocultos na supervisão. O conteúdo explica limites de cobertura, resumos, PDFs locais, manifestação e a diferença entre previsão e pagamento.

Uma conta master é um registro privado no banco, com senha armazenada pelo mecanismo de hash do Django. O repositório não inclui contas prontas ou credenciais de acesso. Para conservar o mesmo login na transferência ao servidor, transfira o banco/backup protegido conforme [LINUX-PM2.md](LINUX-PM2.md). Para criar ou conceder outro master explicitamente:

```powershell
.\.venv\Scripts\python.exe manage.py criar_admin_master
```

O comando solicita e-mail e senha interativamente. Não há argumento de senha, seed público ou senha padrão. A supervisão é acessada em `/gestao/`, pelo botão **Ver painel** do cliente.

## Conferência

Foram acrescentadas verificações de autenticação/leitura do tutorial, acesso master por URL, limites entre clientes, filtros refinados, preservação/removal de filtros, escape de texto e atalhos de período. Também foram conferidos HTML, rótulos, identificadores e âncoras das páginas, sintaxe CSS e os testes de tema existentes.

O navegador não estava disponível para automação nesta sessão (`Browser is not available: iab`). A conferência de HTML/CSS não substitui inspeção visual real de claro/escuro e diferentes dispositivos; essa validação permanece indicada antes da publicação.

Para iniciar no Windows, na pasta do projeto: `py iniciar.py`. Em uma instalação já aberta, atualize o navegador com **Ctrl+F5** para buscar os estilos novos. Não há nova migração de banco nesta alteração visual.
