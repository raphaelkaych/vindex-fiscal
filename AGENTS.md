# Vindex Fiscal

Projeto local em Django 5.2. Preserve a arquitetura e o isolamento de clientes.

- Um Workspace pertence ao usuário; todas as leituras e ações devem ser limitadas ao Workspace autenticado.
- Exceção explícita: a supervisão master autorizada usa /gestao/clientes/{id}/painel/, escopo por URL, leitura e auditoria. Não trocar request.user nem guardar o cliente selecionado em sessão. O escopo da API normal não é ampliado pelo papel master.
- Gerenciamento fora da supervisão, em /gestao/clientes/{id}/gerenciar/ e /empresas/{id}/gerenciar/, exige admin_master + operate_clients, confirmação e auditoria. Exclusão definitiva só de cadastro vazio; nunca cascata de documentos, autorizações ou auditoria. Filas globais não são apagadas por esses controles.
- Company.deactivated_at desativa apenas o vínculo; conta suspensa/dono inativo também impedem novas consultas. Não inferir elegibilidade somente de config.enabled. A1 renovado não reinicia histórico ou NSU.
- Empresas têm identidade por CNPJ. Certificados são renováveis e não são donos do histórico.
- Nunca incluir .env, banco, documentos reais, chaves privadas ou certificados em código/commits/ZIPs.
- Não registrar senha de certificado, chave de cifra ou payload PKCS#12 em logs.
- Nunca apresentar dados fictícios como consulta real.
- Previsões, conferência de parcelas, situação fiscal e pagamento são conceitos separados.
- Não inventar parcelas, datas, linha digitável ou situação de pagamento.
- O importador NF-e aceita XML completo modelo 55. NFS-e e CT-e possuem modelos/importadores tipados próprios em fiscal_*. Eventos e resumos exigem tratamento próprio; não usar o parser de NF-e para outros tipos.
- A captura SEFAZ usa transporte oficial e worker com autorização de leitura por empresa; Ciência da Emissão exige autorização específica por documento. DDA continua sem integração; não ocultar esse limite nas telas.
- Execute os testes relevantes ao alterar autenticação, escopo, importação ou certificados.
- Para rodar os testes: python iniciar.py --testar.
- Para a interface, preserve os tokens de IDENTIDADE-VISUAL.md, os rótulos em português e os comportamentos responsivos.
