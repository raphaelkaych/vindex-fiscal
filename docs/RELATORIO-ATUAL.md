# Relatório do Vindex Fiscal — 21/10/2026

> Registro histórico da etapa anterior. A retomada posterior, conectores novos e gestão master estão no [relatório mais recente](ENTREGA-CONECTORES-MASTER.md).

Conferência às **14:43 (Brasília)**, com atualização posterior da margem de espera. Este relatório substitui o estado pendente do registro histórico em ENTREGA-CAPTURA.md. Contagens podem aumentar nas próximas consultas; o painel privado é a referência atual.

## Resultado real da Alpha Pet

Empresa piloto: **Alpha Pet LTDA — 55.737.823/0001-96**. Ambiente: **produção**, serviço oficial **NFeDistribuicaoDFe**, autenticação pelo A1 cifrado existente e validação TLS. Certificado conferido com CNPJ compatível e validade até 23/03/2027, sem expor senha ou chave.

| Documento recebido | Quantidade acumulada |
|---|---:|
| Resumos de NF-e | 28 |
| XMLs completos de NF-e | 4 |
| Eventos | 2.325 |
| Resumos de eventos | 2.843 |
| Total de documentos | 5.200 |
| NF-e importadas no painel correto | **4** |

Não há erro de processamento nos documentos recebidos nesta conferência. Nenhum exemplo fictício foi contado como consulta real. O download privado de DANFE das quatro notas retornou PDF/HTTP 200, gerado em memória; os XMLs originais permaneceram iguais.

O worker retomou automaticamente às **14:25:48**, após a espera anterior, recebeu diversas respostas **138 — Documento(s) localizado(s)** e importou novas notas sem consulta manual. O último lote aceito foi a consulta local 106, solicitado com NSU **000000000089917**, que retornou **000000000089967**. O máximo da última resposta aceita é **000000000133740**: a fila ainda não terminou.

## Situação atual e impedimento

A consulta seguinte foi realmente executada. Resposta oficial de **21/10/2026, 14:42:23, Brasília**, **656**, motivo exato:

> Rejeicao: Consumo Indevido (Deve ser utilizado o ultNSU nas solicitacoes subsequentes. Tente apos 1 hora)

Ela foi enviada com **000000000089967**, igual ao último NSU aceito e ao NSU informativo da própria rejeição. A auditoria das **107 consultas registradas** não encontrou sobreposição nem divergência entre o NSU de continuação e o retorno anterior. O XML de requisição produzido pelo transporte contém o cursor salvo. Isso não comprova a causa interna da rejeição na SEFAZ; não há evidência para atribuí-la a outro programa, e o proprietário informou que não utiliza outro consumidor.

O sistema mantém a captura habilitada e aguarda até **15:43:23 de 21/10/2026**. A margem de um minuto, calculada também pelo relógio oficial, evita antecipar a hora mínima por diferença entre relógios. O worker foi reiniciado com a correção e conserva o cursor e a espera. Nenhuma consulta antecipada foi feita. A resposta posterior a esse horário ainda precisa de acompanhamento; **não está comprovada a estabilidade contínua nem a conclusão de toda a fila**.

As [regras oficiais de consumo](https://www.nfe.fazenda.gov.br/portal/informe.aspx?AspxAutoDetectCookieSupport=1&ehCTG=false&page=48&pagesize=5) exigem aguardar uma hora após 656. Não foi zerado, adiantado ou substituído o cursor por informação de rejeição. A falha antiga de parser de NSU não reapareceu nessa rodada; rejeição oficial e erro local são apresentados separadamente.

## O que está implementado

- Transporte SOAP oficial com A1 e TLS validado; validação dos schemas, preservação privada da resposta e diagnóstico.
- Ao vincular A1 válido e autorizar a leitura na aplicação, a empresa entra automaticamente na fila. Renovação conserva histórico, NSU e intervalos. Isso vale para todos os clientes/Workspaces, com autorização e credencial próprias.
- Processo periódico, reserva por CNPJ/ambiente contra consultas simultâneas, progresso persistente, retomada e prevenção de duplicidades. XMLs completos são importados; resumos e eventos recebem tratamento separado.
- Painel com atividade do processo, última consulta/resposta oficial, motivo, contagens e próxima tentativa permitida.
- **Ciência da Emissão** implementada com autorização específica por documento. Nenhum evento fiscal real foi enviado nesta entrega; testes de assinatura/transporte usam dados sintéticos. Ciência não confirma operação comercial e pode permitir distribuição posterior do XML, sem garantir disponibilização imediata.
- **Baixar XML** e **Baixar DANFE (PDF)** nas notas. O DANFE é gerado do XML completo com protocolo e dados suficientes, sem buscar o PDF original do fornecedor. Quando não for possível gerar fielmente, o motivo aparece e o XML permanece disponível. Veja [DANFE](DANFE.md).
- Tema único claro/escuro, padrão do sistema e preferência persistente mantidos, assim como a identidade visual e o isolamento entre clientes.

## Integrações e limites

| Recurso | Estado |
|---|---|
| Captura NF-e modelo 55 e documentos associados | Conexão de produção comprovada; atualmente aguardando liberação após 656 |
| DANFE das NF-e completas | Geração e download implementados; quatro notas reais verificadas |
| Ciência da Emissão | Implementada e testada sinteticamente; envio real depende de autorização específica na aplicação |
| API própria Vindex | Implementada, com credenciais e escopos por empresa; não depende da Qive |
| Boletos | Importação/revisão/vínculo existentes; sem captura bancária DDA |
| NFS-e de serviços, CT-e, DDA e OCR | Sem conector implementado; precisam de desenvolvimento e validação próprios |

Certificado válido não garante todos os XMLs históricos: a SEFAZ decide o que está disponível, conforme interesse, janela e regras de distribuição. Resumo não é nota completa; manifestação e decisão comercial continuam explícitas. DANFE gerado não comprova pagamento nem situação fiscal atual.

## O que depende de você

Para a Alpha Pet, **nenhum novo certificado, senha, clique de consulta ou comando por lote** é necessário. Mantenha o computador ligado, com internet e esta conta Windows conectada. Consulte **Captura SEFAZ** após o horário informado para conferir a retomada. Se a rejeição se repetir, será necessário investigar a sequência com os registros privados; não tente forçar consulta ou reiniciar NSU.

Para outra empresa, cadastre o CNPJ, vincule A1 válido na aplicação e marque a autorização de captura. O processo utilizará os dados e permissões daquela empresa. Para um resumo que exija manifestação, a autorização por documento cabe ao responsável na aplicação; não envie certificado ou senha pelo chat.

Para funcionamento sem depender deste computador, a próxima etapa é implantar web e captura em servidor supervisionado. Novos conectores de serviços/transportes/bancos exigem implementação e, conforme o serviço escolhido, credenciamento ou autorização específicos. Não há comando que ative uma integração ainda não desenvolvida.

## Windows

Abra o terminal nesta pasta e execute:

```powershell
py iniciar.py
```

O comando prepara dependências/migrações e abre o servidor em **http://127.0.0.1:8000**; inicia a captura ou aproveita o processo de segundo plano já ativo. Atualize a página para ver os botões de download.

A tarefa **Vindex Fiscal - Captura** já está registrada e foi confirmada em execução nesta máquina. Ela inicia no logon e não exige abrir o portal. Para instalar novamente em outra instalação preparada, uma única vez:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\configurar-captura-windows.ps1
```

Esse comando registra/inicia a tarefa do usuário atual; não solicita senha de A1 nem exige elevação automática. Consulte [o guia de captura](CAPTURA-SEFAZ.md) para manutenção. Encerrar o terminal do portal não encerra a tarefa independente já ativa.

## Conferências realizadas

- Suíte completa: **265 testes aprovados**, executados por `py iniciar.py --testar` (antes da última correção de margem do relógio).
- Após as correções finais: **57 testes de captura e DANFE aprovados**, incluindo novo teste de relógio oficial adiantado. Total atual descoberto: 266 testes; não foi repetida toda a suíte após essa correção localizada.
- **32 verificações de tema/interações/DOM/CSS aprovadas**. Não equivalem a inspeção visual no navegador.
- PDF sintético renderizado e inspecionado em retrato, paisagem e páginas de continuação; identificação fictícia e rodapé conferidos. Quatro DANFEs reais gerados em memória pelo endpoint privado, sem exportar documentos para a pasta do código.
- Portal local respondeu HTTP 200; tarefa Windows e sinal de atividade do worker conferidos. Auditoria dos NSUs e ausência de erros locais de processamento.

Não foram realizados: reinício real do Windows, implantação pública, envio fiscal real de Ciência, validação de conectores não implementados, conferência completa da interface em navegador nesta etapa ou consulta posterior à espera das 15:43:23. Nenhum documento fiscal real, banco, .env, senha ou certificado faz parte dos arquivos desta entrega.
