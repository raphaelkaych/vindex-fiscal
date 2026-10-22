# Identidade visual aplicada

Referência: imagem da Vindex enviada pelo usuário nesta conversa. O arquivo original é uma peça institucional, não um arquivo vetorial do logotipo.

## Direção

- Fundo institucional em azul quase preto: `#050B1D`.
- Azul principal: `#0756FF`.
- Azul complementar: `#1470FF`.
- Superfície do aplicativo: `#F5F7FB`.
- Texto principal: `#14213D`.
- Cartões brancos, bordas sutis e estados visuais discretos.
- Tipografia do sistema: Inter quando disponível; Segoe UI e Arial como alternativas. Nenhuma fonte externa é carregada.

A marca do aplicativo utiliza um monograma vetorial inspirado na referência e o nome VINDEX. Não se trata de uma extração ou reprodução vetorial oficial do logotipo. Quando houver SVG/PNG oficial em boa resolução, basta substituir `templates/portal/wordmark.html` e `static/portal/favicon.svg`.

As cores principais estão concentradas em variáveis no início de `static/portal/app.css` para facilitar ajustes. A aplicação usa menu escuro e conteúdo claro, mantendo o destaque da marca e a leitura dos dados financeiros. Login/cadastro e faixa institucional usam a composição escura da referência.

O rótulo FISCAL identifica este módulo independente e pode ser alterado sem modificar a estrutura de dados.

## Tema escuro

O painel master usa `static/portal/admin.css`, com os mesmos tokens dos temas: indicadores, situação do processo, busca e tabela de clientes. O botão “Ver painel” reutiliza as telas do cliente, com faixa de supervisão e contexto persistido na URL. Cartões adaptam-se em quatro/duas/uma colunas; filtros ocupam a largura no celular e tabelas mantêm rolagem interna. Movimentos discretos dos indicadores respeitam redução de movimento.

`static/portal/theme.css` complementa os tokens originais sem alterar o azul principal `#0756FF`, o azul complementar `#1470FF` ou o fundo institucional `#050B1D`. O tema escuro usa superfície `#080F20`, cartões `#111D32`, texto `#E6EDFA`, texto secundário `#A4B3CD` e bordas `#293953`. Links usam `#8DB3FF` para leitura sobre fundos escuros; os botões primários mantêm o azul da marca. Avisos, erros, sucesso e alertas têm cores próprias para os dois temas.

`static/portal/theme.js` aplica a escolha antes do carregamento dos estilos para evitar o clarão de fundo claro. O botão reutilizável em `templates/portal/theme_toggle.html` tem rótulo em português, estado acessível por `aria-pressed` e foco de teclado. A preferência é local ao navegador, acompanha o sistema até uma escolha manual e se propaga entre abas. Sem JavaScript, o CSS acompanha o tema do sistema. Os formulários nativos também acompanham o tema por `color-scheme`.

## Refinamento de 21/10/2026

`static/portal/refinement.css` complementa os estilos existentes: texto secundário mais legível, avisos com contraste revisado, bordas e foco dos campos, espaçamentos e tipografia dos componentes. O azul principal e a composição institucional permanecem. O cabeçalho se reorganiza no celular, os indicadores financeiros ocupam uma coluna em telas estreitas e as tabelas mantêm rolagem interna.

Um único botão de tema alterna entre ação de lua/sol com texto. Por padrão, a aparência acompanha o sistema até uma escolha manual pelo botão. As escolhas permanecem locais ao navegador. Menu, cópia e estados de envio são tratados em app.js, sem persistência de dados de formulários. Movimentos curtos respeitam prefers-reduced-motion.

Verificação automatizada e limitação de inspeção visual estão em `docs/QA-VISUAL.md`; a automação do navegador foi bloqueada pela ferramenta, portanto os layouts responsivos ainda precisam de conferência visual real.
