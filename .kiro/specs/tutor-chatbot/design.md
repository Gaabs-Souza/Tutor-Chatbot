# Documento de Design

## Visão Geral

O Tutor é um chatbot de estudos implementado como uma aplicação Flask **sem estado** (stateless) em Python, que gera respostas por meio do Amazon Bedrock. A aplicação expõe duas rotas: uma página de chat (`GET /`) e um endpoint de conversação (`POST /chat`). Cada requisição ao endpoint de chat é independente: recebe uma mensagem, valida-a, encaminha o texto ao modelo de linguagem junto com um prompt de sistema fixo e devolve a resposta gerada. Não há banco de dados, sessão, cache ou qualquer forma de persistência entre requisições (Requisito 10).

Toda a inteligência de tutoria — personalidade rígida, técnica de Feynman, repetição espaçada, avaliação de desempenho e organização semanal de estudos — é **comportamental** e vive na constante `SYSTEM_PROMPT` (Requisitos 4 a 9). O servidor Flask em si é responsável apenas pela mecânica de transporte: roteamento HTTP, validação de entrada, construção da chamada ao Bedrock, tratamento de erros e serialização JSON. Essa separação é deliberada: as regras de negócio pedagógicas são expressas em linguagem natural no prompt, enquanto o código Python garante contratos de interface determinísticos e testáveis.

### Decisões-chave de design

| Decisão | Rationale | Requisito |
|---|---|---|
| App Flask stateless, sem persistência | Restrição de arquitetura do projeto; cada mensagem carrega todo o contexto necessário | 10.1, 10.2 |
| Comportamento pedagógico no `SYSTEM_PROMPT` | Sem estado, a única forma de codificar tutoria é via instruções fixas ao modelo + conteúdo da mensagem | 4–9 |
| Validação de entrada antes de qualquer chamada ao Bedrock | Evita custo e latência para entradas inválidas; garante contratos de status HTTP determinísticos | 2.2, 2.3 |
| Falhas do Bedrock devolvem HTTP 200 com `reply` amigável | O chat nunca deve "quebrar" para o usuário final; erros de infraestrutura viram mensagem conversacional | 2.4, 3.4 |
| Credenciais AWS apenas via variáveis de ambiente | Segurança; nunca expor chaves no código | 3.3 |
| `app.json.ensure_ascii = False` | Acentos em português devem aparecer legíveis no JSON | 2.5 |

## Arquitetura

A aplicação segue um fluxo linear de camadas dentro de um único processo Flask. Não há serviços externos além do Amazon Bedrock.

```mermaid
flowchart TD
    Browser["Navegador (templates/index.html)"]
    subgraph Flask["Aplicação Flask (app.py)"]
        RotaPagina["Rota GET / — serve index.html"]
        RotaChat["Rota POST /chat"]
        Validacao["Validação de entrada\n(vazia -> 400, >4000 -> 400)"]
        BuildReq["Construção do corpo da requisição Bedrock\n(SYSTEM_PROMPT + mensagem)"]
        Invoke["Invocação invoke_model\n(timeout 30s)"]
        Parse["Parsing da resposta"]
        ErrHandler["Tratamento de erro\n(falha/timeout -> 200 + reply amigável)"]
    end
    Bedrock["Amazon Bedrock\nbedrock-runtime / invoke_model\nregião us-east-1\nmodelo claude-haiku-4-5"]

    Browser -->|GET /| RotaPagina
    RotaPagina -->|HTML 200| Browser
    Browser -->|POST /chat {message}| RotaChat
    RotaChat --> Validacao
    Validacao -->|inválida| ErrResp400["HTTP 400 {error}"]
    ErrResp400 --> Browser
    Validacao -->|válida| BuildReq
    BuildReq --> Invoke
    Invoke -->|sucesso| Parse
    Parse -->|HTTP 200 {reply}| Browser
    Invoke -->|exceção/timeout| ErrHandler
    ErrHandler -->|HTTP 200 {reply amigável}| Browser
```

### Componentes da arquitetura

1. **Camada de roteamento (Flask):** define `GET /` e `POST /chat`. Configura `app.json.ensure_ascii = False` para serialização de acentos.
2. **Camada de validação:** verifica a presença, o tipo e o tamanho do campo `message` antes de qualquer interação com o Bedrock. É a guarda que garante os contratos de status HTTP (400 para entradas inválidas).
3. **Cliente Bedrock (boto3):** cliente `bedrock-runtime` criado na região `us-east-1`, configurado com timeout de leitura de 30 segundos. Credenciais são resolvidas automaticamente pelo boto3 a partir das variáveis de ambiente.
4. **Construtor de requisição:** monta o corpo JSON esperado pelo modelo Claude (Messages API da Anthropic no Bedrock), combinando `SYSTEM_PROMPT` com a mensagem do usuário.
5. **Parser de resposta:** extrai o texto gerado do corpo retornado pelo `invoke_model`.
6. **Tratador de erros:** captura exceções do boto3 (incluindo timeout) e transforma-as em uma resposta HTTP 200 com um `reply` amigável, de modo que o endpoint nunca retorne 5xx ao cliente por falha do Bedrock.

### Fluxo detalhado de `POST /chat`

1. A requisição chega com corpo JSON `{"message": "..."}`.
2. Extrai-se `message`. Se ausente, nulo, não-string ou composto apenas por espaços em branco (`Mensagem_Vazia`), retorna **HTTP 400** com `{"error": "..."}` sem chamar o Bedrock (Requisito 2.2).
3. Se o texto, após considerado, exceder 4000 caracteres, retorna **HTTP 400** com `{"error": "..."}` sem chamar o Bedrock (Requisito 2.3).
4. Para mensagens válidas (não vazias e com até 4000 caracteres), constrói-se o corpo da requisição ao Bedrock com o `SYSTEM_PROMPT` e a mensagem (Requisito 2.1).
5. Invoca-se `invoke_model` no modelo `us.anthropic.claude-haiku-4-5-20251001-v1:0`, região `us-east-1`, com timeout de 30 segundos (Requisitos 3.1, 3.2).
6. Em caso de sucesso, faz-se o parsing e retorna-se **HTTP 200** com `{"reply": "..."}` (Requisito 2.1).
7. Em caso de qualquer exceção (falha de serviço, erro de parsing, timeout de 30s), retorna-se **HTTP 200** com `{"reply": "<mensagem amigável>"}` (Requisitos 2.4, 3.4).

## Componentes e Interfaces

### Rota `GET /` (Rota_Pagina)

- **Entrada:** requisição GET sem corpo.
- **Saída:** conteúdo renderizado de `templates/index.html`, status HTTP 200 (Requisito 1.1).
- **Implementação:** `return render_template("index.html")`.

### Rota `POST /chat` (Rota_Chat)

- **Entrada:** corpo JSON `{"message": "<texto>"}`.
- **Saídas possíveis:**
  - `200` + `{"reply": "<texto gerado>"}` para mensagem válida processada com sucesso (Requisito 2.1).
  - `200` + `{"reply": "<mensagem amigável>"}` quando o Bedrock falha ou excede 30s (Requisitos 2.4, 3.4).
  - `400` + `{"error": "A mensagem é obrigatória."}` para `Mensagem_Vazia` (Requisito 2.2).
  - `400` + `{"error": "A mensagem excede o tamanho máximo de 4000 caracteres."}` para mensagem acima do limite (Requisito 2.3).

### Função de validação `validar_mensagem(payload) -> (texto | None, erro | None, status)`

Função pura (sem efeitos colaterais) que concentra toda a lógica de validação, isolando-a para teste. Responsabilidades:

1. Extrair `message` do payload (tolerando payload ausente/não-dict).
2. Retornar erro de obrigatoriedade quando a mensagem for ausente, nula, não-string ou só espaços em branco.
3. Retornar erro de tamanho quando o comprimento exceder 4000 caracteres.
4. Retornar o texto quando válido.

Essa função **nunca** chama o Bedrock. Isso garante, por construção, que entradas inválidas jamais atinjam o serviço externo.

### Função `gerar_resposta(texto_usuario) -> str`

Responsável por construir o corpo da requisição, chamar `invoke_model` e fazer o parsing. Encapsula o cliente boto3 e o tratamento de exceções, retornando sempre uma string (o texto do Tutor ou a mensagem amigável de fallback).

### Cliente Bedrock

```python
import boto3
from botocore.config import Config

bedrock = boto3.client(
    "bedrock-runtime",
    region_name="us-east-1",
    config=Config(read_timeout=30, connect_timeout=10, retries={"max_attempts": 0}),
)
```

- Região fixa `us-east-1` (Requisito 3.1).
- `read_timeout=30` implementa o limite de 30 segundos (Requisitos 2.4, 3.4).
- Credenciais resolvidas por boto3 a partir das variáveis de ambiente `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` (e opcionalmente `AWS_SESSION_TOKEN`). Nenhuma chave no código (Requisito 3.3).

## Modelos de Dados

Como a aplicação é stateless e sem banco de dados, não há entidades persistidas. Os modelos de dados são os contratos de troca de mensagens HTTP e o formato de requisição/resposta do Bedrock.

### Requisição de entrada (`POST /chat`)

```json
{ "message": "string, obrigatória, 1..4000 caracteres após trim" }
```

### Resposta de sucesso / fallback

```json
{ "reply": "string" }
```

### Resposta de erro de validação

```json
{ "error": "string descrevendo o motivo" }
```

### Corpo da requisição ao Bedrock (Anthropic Messages API)

O modelo Claude no Bedrock usa o esquema de mensagens da Anthropic. O `SYSTEM_PROMPT` vai no campo `system`, e a mensagem do usuário vira um turno `user`.

```json
{
  "anthropic_version": "bedrock-2023-05-31",
  "max_tokens": 1024,
  "system": "<SYSTEM_PROMPT>",
  "messages": [
    { "role": "user", "content": [ { "type": "text", "text": "<mensagem do usuário>" } ] }
  ]
}
```

### Corpo da resposta do Bedrock

```json
{
  "content": [ { "type": "text", "text": "<resposta gerada>" } ],
  "stop_reason": "end_turn"
}
```

O parsing extrai `content[0].text`. Se a estrutura não corresponder ao esperado, o parsing lança exceção e cai no fallback amigável (HTTP 200).

### Projeto do `SYSTEM_PROMPT`

O `SYSTEM_PROMPT` é o artefato central que codifica os Requisitos 4 a 9. Ele é uma constante de texto em `app.py` estruturada nos seguintes blocos instrucionais:

1. **Persona e tom (Requisito 4):** instrui o Tutor a ser rígido e exigente; usar linguagem direta e imperativa; estabelecer ao menos uma meta/ação de estudo objetiva em cada orientação; não elogiar sem evidência de desempenho relatada; apontar explicitamente não cumprimento relatado e indicar ação corretiva concreta.
2. **Escopo restrito (Requisito 4.3, 4.4):** limita o Tutor a estudo, tutoria e organização acadêmica; se a mensagem fugir desse escopo, recusar o assunto e redirecionar para estudo.
3. **Tutoria de matérias (Requisito 5):** ao receber uma matéria/conteúdo, fornecer explicações, orientações e questionamentos; ao detectar dúvida, explicar o conceito e propor forma de o usuário verificar o próprio entendimento.
4. **Técnica de Feynman (Requisito 6):** ao iniciar um conceito, fazer **uma única** solicitação explícita para o usuário explicar com as próprias palavras; comparar com a definição de referência; listar lacunas (elemento essencial ausente/incorreto/incompleto) e indicar o conteúdo a revisar para cada uma; confirmar quando não houver lacunas; se a explicação vier vazia, reiterar a solicitação informando que ela é necessária.
5. **Repetição espaçada (Requisito 7):** propor sempre uma sequência de no mínimo 3 intervalos estritamente crescentes; quando houver data de prova/prazo, distribuir revisões em intervalos crescentes entre hoje e a data; recusar datas no passado ou iguais a hoje como inválidas; quando o prazo for curto demais, propor cronograma intensivo de no mínimo 2 revisões e avisar que o prazo é curto.
6. **Avaliação de desempenho (Requisito 8):** analisar apenas os dados da mensagem atual; indicar ao menos um ponto forte e ao menos um ponto a melhorar; ordenar as orientações do menor para o maior desempenho; se não houver dados avaliáveis, pedir os dados e avisar que não mantém histórico; se os dados forem insuficientes, dizer o que falta e abster-se de avaliar.
7. **Organização semanal (Requisito 9):** ao receber datas, prazos, notas e total de horas semanais, montar um `Plano_Semanal` que distribui exatamente esse total entre as matérias nos dias da semana corrente, alocando mais horas às notas mais baixas e prazos mais próximos, em ordem decrescente de prioridade; se faltar informação, pedir explicitamente o que falta antes de sugerir o plano.
8. **Operação sem memória (Requisito 10):** deixar claro ao usuário que o Tutor não guarda histórico e que datas, notas e contexto devem ser incluídos na própria mensagem.

> Nota: os Requisitos 4–9 definem comportamento conversacional de um LLM. Eles são endereçados por instruções no `SYSTEM_PROMPT`, e não por lógica determinística em Python. Por isso, conforme a análise de testabilidade a seguir, eles não geram propriedades de teste automatizadas — são verificados por revisão qualitativa das respostas do modelo.

## Correctness Properties

*Uma propriedade é uma característica ou comportamento que deve ser verdadeiro em todas as execuções válidas de um sistema — essencialmente, uma afirmação formal sobre o que o sistema deve fazer. As propriedades servem de ponte entre especificações legíveis por humanos e garantias de correção verificáveis por máquina.*

As propriedades abaixo cobrem a **camada determinística** da aplicação (validação de entrada, contratos de status HTTP, tratamento de erros, serialização e ausência de estado). Os comportamentos pedagógicos dos Requisitos 4 a 9 (e 10.2) são gerados pelo modelo de linguagem a partir do `SYSTEM_PROMPT` e não possuem saída estruturada determinística no nosso código; por isso são verificados qualitativamente (ver Estratégia de Testes) e não produzem propriedades automatizadas. Todas as propriedades são testadas com o cliente Bedrock **mockado**, para isolar a lógica do nosso código do serviço externo e manter o custo baixo.

### Property 1: Mensagem válida invoca o Bedrock corretamente e retorna 200 com reply

*Para toda* string de mensagem não vazia (após remoção de espaços nas bordas) com no máximo 4000 caracteres, ao enviá-la em `POST /chat`, a Aplicacao SHALL invocar o Bedrock exatamente uma vez com o `modelId` igual a `us.anthropic.claude-haiku-4-5-20251001-v1:0` e com o `SYSTEM_PROMPT` no campo `system`, e SHALL retornar status HTTP 200 com um corpo JSON contendo um campo `reply` do tipo string.

**Validates: Requirements 2.1, 3.1, 3.2**

### Property 2: Mensagem vazia é rejeitada sem atingir o Bedrock

*Para toda* entrada em que `message` esteja ausente, nula, não seja string ou seja composta apenas por espaços em branco (`Mensagem_Vazia`), ao enviá-la em `POST /chat`, a Aplicacao SHALL retornar status HTTP 400 com um corpo JSON contendo um campo `error`, e SHALL NÃO invocar o Bedrock.

**Validates: Requirements 2.2**

### Property 3: Mensagem acima do limite é rejeitada sem atingir o Bedrock

*Para toda* string de mensagem com comprimento estritamente maior que 4000 caracteres, ao enviá-la em `POST /chat`, a Aplicacao SHALL retornar status HTTP 400 com um corpo JSON contendo um campo `error`, e SHALL NÃO invocar o Bedrock.

**Validates: Requirements 2.3**

### Property 4: Falha ou timeout do Bedrock nunca quebra o endpoint

*Para toda* mensagem válida e *para toda* falha do Bedrock (qualquer exceção do cliente, incluindo erro de serviço, timeout de leitura de 30 segundos ou corpo de resposta malformado), a Aplicacao SHALL retornar status HTTP 200 com um corpo JSON contendo um campo `reply` do tipo string (mensagem amigável), e SHALL NÃO retornar um status de erro 5xx.

**Validates: Requirements 2.4, 3.4**

### Property 5: Serialização JSON preserva caracteres não-ASCII

*Para toda* resposta do Tutor contendo caracteres não-ASCII (por exemplo, acentos do português), o corpo HTTP serializado SHALL conter os caracteres literais (não escapados na forma `\uXXXX`), e a desserialização do corpo SHALL reconstruir exatamente o mesmo texto (round-trip).

**Validates: Requirements 2.5**

### Property 6: Ausência de estado entre requisições

*Para toda* sequência de mensagens válidas processadas pela Aplicacao, o corpo da requisição enviado ao Bedrock para uma dada mensagem M SHALL depender exclusivamente de M e do `SYSTEM_PROMPT`, sendo idêntico independentemente de quais e quantas mensagens tenham sido processadas anteriormente (nenhuma informação de requisições anteriores influencia a requisição atual).

**Validates: Requirements 10.1**

## Tratamento de Erros

| Situação | Detecção | Resposta | Requisito |
|---|---|---|---|
| `message` ausente, nula, não-string ou só espaços | Camada de validação, antes do Bedrock | HTTP 400 `{"error": "A mensagem é obrigatória."}` | 2.2 |
| `message` com mais de 4000 caracteres | Camada de validação, antes do Bedrock | HTTP 400 `{"error": "A mensagem excede o tamanho máximo de 4000 caracteres."}` | 2.3 |
| Falha do Bedrock (`ClientError`, `BotoCoreError`) | `try/except` em `gerar_resposta` | HTTP 200 `{"reply": "<mensagem amigável>"}` | 2.4, 3.4 |
| Timeout de 30s (`ReadTimeoutError`) | `read_timeout=30` + `try/except` | HTTP 200 `{"reply": "<mensagem amigável>"}` | 2.4, 3.4 |
| Corpo da resposta do Bedrock malformado | Exceção no parsing, capturada no mesmo `try/except` | HTTP 200 `{"reply": "<mensagem amigável>"}` | 2.4, 3.4 |
| JSON de entrada inválido / Content-Type ausente | `request.get_json(silent=True)` retorna `None`, tratado como `Mensagem_Vazia` | HTTP 400 `{"error": ...}` | 2.2 |

Princípios:

- **Nunca retornar 5xx por causa do Bedrock.** Qualquer exceção na geração de resposta é convertida em um `reply` amigável com status 200, para que a experiência de chat não quebre (Requisitos 2.4, 3.4).
- **Falhar rápido na validação.** Entradas inválidas são rejeitadas antes de qualquer custo de rede/modelo (Requisitos 2.2, 2.3).
- **Mensagens de erro em português e legíveis**, coerentes com `ensure_ascii = False` (Requisito 2.5).
- **Sem retries automáticos** (`retries={"max_attempts": 0}`) para respeitar o orçamento de 30 segundos de forma previsível.

## Estratégia de Testes

### Abordagem dupla

A estratégia combina testes de propriedade (validação universal da camada determinística) com testes de exemplo/integração (casos específicos, wiring e comportamento conversacional).

### Testes baseados em propriedade (PBT)

- **Biblioteca:** [Hypothesis](https://hypothesis.readthedocs.io/) para Python. Não implementar PBT do zero.
- **Cliente Bedrock mockado** em todos os testes de propriedade (via `unittest.mock`/monkeypatch), isolando a lógica do nosso código do serviço externo e eliminando custo/latência.
- **Mínimo de 100 iterações por teste de propriedade** (`@settings(max_examples=100)`).
- **Uma única função de teste de propriedade por propriedade de correção.**
- Cada teste anotado com um comentário referenciando a propriedade do design, no formato:
  `# Feature: tutor-chatbot, Property {número}: {texto da propriedade}`

Mapa de propriedades para geradores:

| Propriedade | Gerador Hypothesis | Verificação |
|---|---|---|
| P1 | `st.text(min_size=1, max_size=4000).filter(lambda s: s.strip())` | 200, `reply` é string, mock chamado 1x com `modelId` correto e `SYSTEM_PROMPT` em `system` |
| P2 | whitespace-only + casos `None`/ausente/não-string | 400, `error` presente, mock NÃO chamado |
| P3 | `st.text(min_size=4001)` | 400, `error` presente, mock NÃO chamado |
| P4 | mensagem válida × `st.sampled_from([ClientError, ReadTimeoutError, body malformado, ...])` | 200, `reply` string, nunca 5xx |
| P5 | reply com `st.text()` incluindo caracteres não-ASCII | bytes contêm caracteres literais; `json.loads` reconstrói o texto |
| P6 | listas de mensagens válidas `st.lists(mensagem_valida)` | corpo enviado ao Bedrock para cada M depende só de M + SYSTEM_PROMPT (idêntico entre ordens/sequências) |

Edge cases explícitos cobertos pelos geradores: `len == 4000` (válida) vs `len == 4001` (rejeitada); strings com apenas espaços, tabs e quebras de linha; texto com acentos e caracteres multibyte.

### Testes de exemplo e integração

- **Rota_Pagina (Requisito 1.1):** teste de exemplo via test client do Flask — `GET /` retorna 200 e serve o HTML (SMOKE).
- **Wiring do Bedrock (Requisito 3.1):** teste de exemplo que verifica a criação do cliente `bedrock-runtime` com `region_name="us-east-1"` e o uso da operação `invoke_model` (INTEGRATION com mock).
- **Credenciais por ambiente (Requisito 3.3):** verificação estática/revisão de que nenhuma chave é escrita no código e de que o boto3 resolve credenciais do ambiente; teste de exemplo confirmando que o client é criado sem `aws_access_key_id`/`aws_secret_access_key` explícitos (SMOKE).

### Verificação qualitativa do comportamento pedagógico (Requisitos 4–9, 10.2)

Esses requisitos descrevem o conteúdo conversacional gerado pelo LLM a partir do `SYSTEM_PROMPT` e não possuem saída determinística testável automaticamente. A estratégia:

- **Teste estrutural automatizado:** confirmar que, para toda mensagem válida, o `SYSTEM_PROMPT` é de fato enviado no campo `system` da requisição ao Bedrock (garante que as instruções pedagógicas sempre acompanham a conversa).
- **Avaliação qualitativa manual:** executar roteiros representativos (ex.: pedir plano semanal sem informar horas; enviar explicação para aplicar Feynman; informar data de prova no passado; relatar notas para avaliação) e revisar se as respostas aderem às regras dos Requisitos 4–9. Esses roteiros servem como checklist de revisão, não como asserções determinísticas.

### Observações de execução

- Rodar os testes com uma invocação única (sem modo watch), por exemplo `pytest` ou `python -m pytest`.
- A aplicação é executada manualmente com `python app.py` em `localhost:5000`; servidores de desenvolvimento não devem ser iniciados automaticamente pelos testes.
