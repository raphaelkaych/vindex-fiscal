# Refinamento do portal — 21/10/2026

## Implementado

- Tema com texto e ícone correspondentes à próxima ação: lua/“Ativar modo escuro” e sol/“Ativar modo claro”. Um único botão; por padrão, acompanha o sistema até uma escolha manual.
- Preferência local persistente entre páginas/recarregamentos e sincronizada entre abas. O modo sistema reage à configuração do dispositivo. O script aplica a aparência antes dos estilos; sem JavaScript o CSS acompanha o sistema.
- Camada `static/portal/refinement.css` compartilhada pelo portal, login/cadastro e tela de limite, mantendo os azuis institucionais e o tema escuro.
- Tipografia mais legível, espaçamentos, alinhamento, estados de documentos, indicadores, campos, filtros, tabelas e uploads padronizados. Cabeçalho se reorganiza em telas estreitas; tabelas extensas têm rolagem interna e foco de teclado.
- Menu móvel com botão de fechar, fundo clicável, Escape, foco inicial, contenção de Tab e devolução de foco. Menu fechado fica fora da navegação assistiva em celular; desktop permanece acessível. Navegação ativa usa `aria-current` no HTML do servidor.
- Estados de envio nos formulários nativos: texto de carregamento durante a operação, prevenção de clique/submissão repetidos e restauração ao voltar pelo histórico. Não são usados atrasos para simular processamento nem são desabilitados campos/submitters, preservando seus dados.
- Botões de cópia para chave da NF-e, linha digitável existente e credencial recém-gerada. “Copiado” aparece somente após confirmação da API de área de transferência. Se ela estiver indisponível, o conteúdo é selecionado para cópia manual, sem falso sucesso.
- Erros renderizados recebem foco e descrição acessível; valores não sensíveis continuam no formulário Django. Arquivos precisam ser selecionados novamente e senhas de certificado não são renderizadas no erro. Nenhum dado de formulário ou credencial foi adicionado ao armazenamento local.
- Transições curtas de cores, botões, mensagens e gráficos de dados já carregados. `prefers-reduced-motion` desativa movimentos; o feedback textual permanece.

Não houve mudança nos modelos, migrações, regras de autenticação, escopo de clientes ou integrações fiscais/bancárias.

## Verificações efetivamente realizadas

| Verificação | Resultado |
|---|---|
| `python iniciar.py --testar` | 153 testes Django aprovados, incluindo os 147 anteriores e 6 novos de interface renderizada |
| `tools/check_theme.cjs` | 13 verificações de estado, persistência, troca de modo, eventos do sistema/abas e armazenamento bloqueado |
| `tools/ui-checks/check_interactions.cjs` | 19 verificações de DOM/CSS em memória, sem navegador |
| Sintaxe JavaScript e parser CSS | Aprovados para os scripts/folhas usados |
| Contraste dos tokens revisados | Amostragem de 12 pares de texto com pelo menos 4,5:1 e 4 pares de borda/foco com pelo menos 3:1 |
| `manage.py check` | Sem problemas |
| `manage.py makemigrations --check --dry-run` | Nenhuma alteração de modelo |
| OpenAPI com `--validate --fail-on-warn` | Aprovado sem avisos |

Os novos testes Django verificam carregamento dos recursos e controles em 16 telas do portal, navegação ativa única, valores não sensíveis mantidos em erros, senha não reapresentada, acesso anônimo e preservação do escopo no controle de cópia.

Os testes de DOM usam jsdom e geometria simulada para exercitar eventos e foco. Conferem Escape/Tab, fechar/fundo, mudança do modo móvel para desktop, preservação dos campos e submitter, envio duplicado, cancelamento, retorno pelo histórico, cópia assíncrona com sucesso/falha, uploads, erros e tabelas acessíveis. Eles **não renderizam pixels, não medem layout real e não equivalem à validação visual de um navegador**.

## Inspeção visual que não foi possível concluir

A tentativa de controle do navegador retornou inventário vazio no CUA. O fallback oficial da habilidade [computer-use](C:/Users/user/.codex/plugins/cache/openai-bundled/computer-use/26.1013.40934/skills/computer-use/SKILL.md), por `@oai/sky`, encontrou o Chrome e abriu uma janela exclusiva vazia, mas a ferramenta interrompeu a automação porque não conseguiu determinar o endereço do navegador com confiança para aplicar suas políticas. A instrução recebida foi: “Computer Use has been stopped for this turn because it could not determine the current browser URL on Windows with enough confidence to enforce policy.”

O bloqueio foi respeitado. Nenhuma tela do Vindex foi inspecionada visualmente, nenhuma captura foi produzida e não foi tentado contornar o bloqueio por outro controlador. A janela vazia de QA pode permanecer aberta. O servidor auxiliar usou somente dados fictícios em banco de memória, sem documentos/certificados reais do cliente.

Portanto, ficam pendentes os testes visuais de login, painel, empresas, notas, parcelas, boletos, certificados, perfil, integrações, mensagens e erros nos dois temas e nos tamanhos sugeridos 360, 768 e 1440 pixels. Também falta validar manualmente leitor de tela, comportamento de seletores nativos, zoom 200%, redução de movimento real, área de transferência do dispositivo e foco/rolagem no navegador. As regras responsivas foram implementadas; não há garantia de ausência de todo problema visual sem essa conferência.

## Como conferir no Windows

1. Se o servidor estiver rodando, encerre-o com Ctrl+C. Execute `py iniciar.py` nesta pasta.
2. Abra `http://127.0.0.1:8000` e use Ctrl+F5 para renovar os arquivos estáticos.
3. Em um navegador sem preferência salva, confira se a aparência acompanha o sistema. Alterne pelo botão de lua/sol. Navegue, recarregue e confira o estado em outra aba.
4. Em uma janela estreita, abra o menu e use Tab, Shift+Tab e Escape. Ao fechar, o foco deve retornar ao botão que abriu o menu.
5. Confira formulários com campos vazios/incorretos e uploads fictícios. Mensagens devem orientar a correção; nenhum teste deve afirmar captura bancária/fiscal.
6. Teste “Copiar” e a alternativa manual se o navegador negar a área de transferência. Nunca envie credencial, senha ou certificado ao chat.

Repetir testes Django: `py iniciar.py --testar`. Os testes adicionais de JavaScript são opcionais para desenvolvedores com Node 24 ou superior:

```powershell
npm --prefix tools/ui-checks ci --ignore-scripts
npm --prefix tools/ui-checks test
```

As dependências jsdom/PostCSS ficam somente em `tools/ui-checks` para testes; Node não é necessário para executar o portal por `py iniciar.py`. Os diretórios `node_modules` e temporários estão ignorados. Consulte as fontes mantidas de [jsdom](https://github.com/jsdom/jsdom) e [PostCSS](https://github.com/postcss/postcss) para os limites dessas ferramentas.

## Certificados e próxima etapa independente

Cadastrar A1 continua apenas conferindo arquivo/senha/validade/CNPJ e cifrando o material no banco. Não há consulta SEFAZ ou DDA ao salvar e não há como garantir aceitação por um serviço externo ainda não homologado. A raiz de CNPJ deve ser compatível e o usuário precisa estar autorizado. A cadeia ICP-Brasil e a revogação não são verificadas nesta conferência local.

A Qive continua referência funcional; nenhuma dependência ou integração com ela foi adicionada. Para a etapa de captura própria, será necessário combinar empresa piloto, autorização e uso local protegido de certificado adequado, além de implementar/homologar transporte e worker conforme `INTEGRACAO-SEFAZ.md`. Certificado/senha não devem ser enviados ao chat. O refinamento visual não depende dessa etapa.
