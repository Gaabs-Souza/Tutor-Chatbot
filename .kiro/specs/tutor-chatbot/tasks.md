# Plano de Implementação: Tutor Chatbot

## Visão Geral

A implementação segue a estrutura obrigatória do projeto: uma aplicação Flask stateless em `app.py` na raiz, com a página de chat em `templates/index.html`, dependências em `requirements.txt` (flask, boto3) e integração com o Amazon Bedrock via boto3 (`bedrock-runtime`, `invoke_model`, região `us-east-1`).

A ordem de construção é incremental: primeiro a estrutura e as dependências, depois a camada de validação pura (testável isoladamente), em seguida a integração com o Bedrock e a camada de rotas, a configuração do app (`ensure_ascii = False`), o `SYSTEM_PROMPT` com todo o comportamento pedagógico, a página de chat e, por fim, os testes de propriedade (Hypothesis, Bedrock mockado) e os testes de exemplo/integração/smoke. Cada passo integra o código do passo anterior, sem código órfão.

As propriedades de correção (Property 1 a 6) cobrem a camada determinística (validação, contratos HTTP, tratamento de erros, serialização e ausência de estado). Os comportamentos pedagógicos (Requisitos 4–9, 10.2) vivem no `SYSTEM_PROMPT` e são verificados qualitativamente, não por asserções automatizadas (ver a seção de revisão não-codificável ao final).

## Tarefas

- [x] 1. Configurar estrutura do projeto e dependências
  - Criar `requirements.txt` na raiz com as dependências `flask` e `boto3`.
  - Criar a pasta `templates/` para a página de chat.
  - Criar o arquivo `app.py` na raiz com o esqueleto da aplicação Flask (instância `app = Flask(__name__)`) e a configuração `app.json.ensure_ascii = False` para serializar acentos legíveis.
  - Adicionar o bloco `if __name__ == "__main__": app.run(host="localhost", port=5000)` para rodar com `python app.py` em `localhost:5000`.
  - _Requisitos: 2.5, 10.1_

- [x] 2. Implementar camada de validação de entrada
  - [x] 2.1 Implementar a função pura `validar_mensagem(payload) -> (texto | None, erro | None, status)`
    - Tolerar payload ausente ou não-dict (tratar como `Mensagem_Vazia`).
    - Extrair o campo `message`; retornar erro de obrigatoriedade (`"A mensagem é obrigatória."`, status 400) quando ausente, nulo, não-string ou composto apenas por espaços em branco.
    - Retornar erro de tamanho (`"A mensagem excede o tamanho máximo de 4000 caracteres."`, status 400) quando o comprimento exceder 4000 caracteres.
    - Retornar o texto válido (com status indicando sucesso) sem jamais chamar o Bedrock.
    - _Requisitos: 2.2, 2.3_

  - [ ]* 2.2 Escrever teste de propriedade para rejeição de mensagem vazia
    - **Property 2: Mensagem vazia é rejeitada sem atingir o Bedrock**
    - Gerador: strings só com espaços/tabs/quebras de linha + casos `None`/ausente/não-string.
    - Verificar status HTTP 400, presença do campo `error` e que o mock do Bedrock NÃO foi chamado.
    - Usar Hypothesis com `@settings(max_examples=100)`; anotar com `# Feature: tutor-chatbot, Property 2: ...`.
    - **Validates: Requirements 2.2**

  - [ ]* 2.3 Escrever teste de propriedade para rejeição de mensagem acima do limite
    - **Property 3: Mensagem acima do limite é rejeitada sem atingir o Bedrock**
    - Gerador: `st.text(min_size=4001)`.
    - Verificar status HTTP 400, presença do campo `error` e que o mock do Bedrock NÃO foi chamado.
    - Usar Hypothesis com `@settings(max_examples=100)`; anotar com `# Feature: tutor-chatbot, Property 3: ...`.
    - **Validates: Requirements 2.3**

- [x] 3. Implementar integração com o Amazon Bedrock
  - [x] 3.1 Criar o cliente `bedrock-runtime` e a função `gerar_resposta(texto_usuario) -> str`
    - Criar o cliente boto3 `bedrock-runtime` com `region_name="us-east-1"` e `Config(read_timeout=30, connect_timeout=10, retries={"max_attempts": 0})`.
    - Resolver credenciais exclusivamente via variáveis de ambiente (não passar `aws_access_key_id`/`aws_secret_access_key` no código).
    - Construir o corpo da requisição (Anthropic Messages API): `anthropic_version="bedrock-2023-05-31"`, `max_tokens`, campo `system` com o `SYSTEM_PROMPT` e turno `user` com a mensagem.
    - Invocar `invoke_model` com `modelId="us.anthropic.claude-haiku-4-5-20251001-v1:0"`.
    - Fazer o parsing de `content[0].text` do corpo retornado.
    - Capturar qualquer exceção (`ClientError`, `BotoCoreError`, `ReadTimeoutError`, erro de parsing de corpo malformado) e retornar uma string de fallback amigável em português.
    - _Requisitos: 2.1, 2.4, 3.1, 3.2, 3.3, 3.4_

  - [ ]* 3.2 Escrever teste de propriedade de resiliência a falhas/timeout do Bedrock
    - **Property 4: Falha ou timeout do Bedrock nunca quebra o endpoint**
    - Gerador: mensagem válida × `st.sampled_from([ClientError, ReadTimeoutError, corpo malformado, ...])` configurando o mock para levantar cada exceção.
    - Verificar status HTTP 200, campo `reply` do tipo string e que nunca ocorre status 5xx.
    - Usar Hypothesis com `@settings(max_examples=100)`; anotar com `# Feature: tutor-chatbot, Property 4: ...`.
    - **Validates: Requirements 2.4, 3.4**

- [x] 4. Implementar o `SYSTEM_PROMPT` com os comportamentos de tutoria
  - Definir a constante `SYSTEM_PROMPT` em `app.py` codificando em linguagem natural os blocos instrucionais do design:
    - Persona rígida e exigente, linguagem direta/imperativa, meta/ação objetiva por orientação, sem elogios sem evidência, apontar não cumprimento relatado com ação corretiva (Requisito 4).
    - Escopo restrito a estudo/tutoria/organização acadêmica, recusar e redirecionar fora do escopo (Requisito 4.3, 4.4).
    - Tutoria de matérias: explicações, orientações, questionamentos e verificação de entendimento (Requisito 5).
    - Técnica de Feynman: solicitação única de explicação, comparação com definição de referência, listar lacunas com conteúdo a revisar, confirmar ausência de lacunas, reiterar se explicação vazia (Requisito 6).
    - Repetição espaçada: mínimo de 3 intervalos estritamente crescentes, distribuição entre hoje e data informada, recusar datas no passado/iguais a hoje, cronograma intensivo (≥2 revisões) quando prazo curto (Requisito 7).
    - Avaliação de desempenho: analisar só a mensagem atual, ao menos um ponto forte e um a melhorar, ordenar do menor ao maior desempenho, pedir dados quando ausentes/insuficientes e avisar que não há histórico (Requisito 8).
    - Organização semanal: distribuir exatamente o total de horas, mais horas para notas baixas/prazos próximos, ordem decrescente de prioridade, pedir informações faltantes antes do plano (Requisito 9).
    - Operação sem memória: deixar claro que não guarda histórico e que datas/notas/contexto devem vir na mensagem (Requisito 10.2).
  - _Requisitos: 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3, 7.4, 8.1, 8.2, 8.3, 8.4, 8.5, 9.1, 9.2, 9.3, 9.4, 10.2_

- [x] 5. Implementar as rotas Flask e integrar as camadas
  - [x] 5.1 Implementar a rota `GET /` (Rota_Pagina)
    - Retornar `render_template("index.html")` com status HTTP 200.
    - _Requisitos: 1.1_

  - [x] 5.2 Implementar a rota `POST /chat` (Rota_Chat) integrando validação e geração
    - Ler o corpo com `request.get_json(silent=True)` (JSON inválido/sem Content-Type vira `None`, tratado como `Mensagem_Vazia`).
    - Chamar `validar_mensagem`; se inválido, retornar HTTP 400 com `{"error": ...}` sem chamar o Bedrock.
    - Para mensagem válida, chamar `gerar_resposta` e retornar HTTP 200 com `{"reply": ...}` (inclusive o fallback amigável em caso de falha do Bedrock).
    - _Requisitos: 2.1, 2.2, 2.3, 2.4, 3.4, 10.1_

  - [ ]* 5.3 Escrever teste de propriedade para mensagem válida (invocação correta do Bedrock)
    - **Property 1: Mensagem válida invoca o Bedrock corretamente e retorna 200 com reply**
    - Gerador: `st.text(min_size=1, max_size=4000).filter(lambda s: s.strip())`.
    - Verificar status 200, `reply` string, mock chamado exatamente 1x com `modelId="us.anthropic.claude-haiku-4-5-20251001-v1:0"` e `SYSTEM_PROMPT` no campo `system`.
    - Usar Hypothesis com `@settings(max_examples=100)`; anotar com `# Feature: tutor-chatbot, Property 1: ...`.
    - **Validates: Requirements 2.1, 3.1, 3.2**

  - [ ]* 5.4 Escrever teste de propriedade para serialização JSON de acentos
    - **Property 5: Serialização JSON preserva caracteres não-ASCII**
    - Gerador: `reply` com `st.text()` incluindo caracteres não-ASCII (acentos do português).
    - Verificar que os bytes do corpo contêm os caracteres literais (não escapados como `\uXXXX`) e que `json.loads` reconstrói exatamente o mesmo texto (round-trip).
    - Usar Hypothesis com `@settings(max_examples=100)`; anotar com `# Feature: tutor-chatbot, Property 5: ...`.
    - **Validates: Requirements 2.5**

  - [ ]* 5.5 Escrever teste de propriedade para ausência de estado entre requisições
    - **Property 6: Ausência de estado entre requisições**
    - Gerador: `st.lists(mensagem_valida)`.
    - Verificar que o corpo enviado ao Bedrock para cada mensagem M depende exclusivamente de M e do `SYSTEM_PROMPT`, sendo idêntico independentemente de sequência/ordem anterior.
    - Usar Hypothesis com `@settings(max_examples=100)`; anotar com `# Feature: tutor-chatbot, Property 6: ...`.
    - **Validates: Requirements 10.1**

- [x] 6. Checkpoint - Garantir que todos os testes passam
  - Garanta que todos os testes passam; pergunte ao usuário se surgirem dúvidas.

- [x] 7. Implementar a página de chat e os testes de exemplo/integração
  - [x] 7.1 Criar `templates/index.html` com a interface de chat
    - Página HTML com área de conversa, campo de entrada e envio que faz `POST /chat` com `{"message": "..."}` e exibe o `reply` retornado.
    - Tratar e exibir mensagens de erro (`error`) retornadas em respostas 400.
    - _Requisitos: 1.1, 2.1, 2.2, 2.3_

  - [ ]* 7.2 Escrever teste de exemplo/smoke da Rota_Pagina
    - Via test client do Flask, verificar que `GET /` retorna 200 e serve o HTML.
    - _Requisitos: 1.1_

  - [ ]* 7.3 Escrever teste de integração do wiring do Bedrock
    - Com o cliente mockado, verificar a criação do cliente `bedrock-runtime` com `region_name="us-east-1"` e o uso da operação `invoke_model`.
    - _Requisitos: 3.1_

  - [ ]* 7.4 Escrever teste de exemplo/smoke de credenciais por ambiente
    - Confirmar que o cliente é criado sem `aws_access_key_id`/`aws_secret_access_key` explícitos (credenciais resolvidas do ambiente) e que nenhuma chave está escrita no código.
    - _Requisitos: 3.3_

  - [ ]* 7.5 Escrever teste estrutural de envio do `SYSTEM_PROMPT`
    - Confirmar que, para toda mensagem válida, o `SYSTEM_PROMPT` é enviado no campo `system` da requisição ao Bedrock (garante que as instruções pedagógicas sempre acompanham a conversa).
    - _Requisitos: 4.1, 5.1, 6.1, 7.1, 8.1, 9.1, 10.2_

- [x] 8. Checkpoint final - Garantir que todos os testes passam
  - Garanta que todos os testes passam; pergunte ao usuário se surgirem dúvidas.
  - Observação de execução: rodar os testes em invocação única (sem modo watch), por exemplo `python -m pytest`. A aplicação roda manualmente com `python app.py` em `localhost:5000`; não iniciar servidores de desenvolvimento automaticamente.

## Notas

- Tarefas marcadas com `*` são opcionais (testes) e podem ser puladas para um MVP mais rápido.
- Cada tarefa referencia requisitos e/ou propriedades específicas para rastreabilidade.
- Os checkpoints garantem validação incremental.
- Os testes de propriedade (Hypothesis) usam o cliente Bedrock mockado, com no mínimo 100 iterações e uma única função de teste por propriedade de correção.
- Os testes unitários/de exemplo validam casos específicos, wiring e edge cases (`len == 4000` válida vs `len == 4001` rejeitada; whitespace-only; acentos/multibyte).

### Itens de revisão não-codificáveis (verificação qualitativa, fora do escopo automatizável)

Os Requisitos 4–9 e 10.2 descrevem comportamento conversacional gerado pelo LLM a partir do `SYSTEM_PROMPT` e não possuem saída determinística testável automaticamente. Eles devem ser verificados por revisão qualitativa manual (checklist, não asserções automatizadas), executando roteiros representativos:

- Pedir plano semanal sem informar horas disponíveis (deve solicitar as horas antes do plano) — Requisito 9.3, 9.4.
- Enviar explicação de um conceito para aplicar Feynman (deve comparar com a definição de referência e listar lacunas) — Requisito 6.2, 6.3.
- Informar data de prova no passado/igual a hoje (deve recusar como data inválida) — Requisito 7.3.
- Relatar notas/resultados para avaliação (deve indicar ponto forte e ponto a melhorar, ordenado do menor ao maior desempenho) — Requisito 8.1, 8.2, 8.3.
- Enviar mensagem fora do escopo acadêmico (deve recusar e redirecionar) — Requisito 4.4.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["2.1", "3.1"] },
    { "id": 1, "tasks": ["2.2", "2.3", "3.2", "5.1", "5.2", "7.1"] },
    { "id": 2, "tasks": ["5.3", "5.4", "5.5", "7.2", "7.3", "7.4", "7.5"] }
  ]
}
```
