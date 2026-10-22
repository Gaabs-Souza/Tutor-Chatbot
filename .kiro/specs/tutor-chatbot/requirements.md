# Documento de Requisitos

## Introdução

O Tutor é um chatbot de estudos construído em Python com Flask que conversa com o usuário pela rota de chat e gera respostas por meio do Amazon Bedrock. A personalidade do Tutor é rígida e exigente, e sua função é tutorar o usuário nas matérias dele, avaliar o desempenho relatado, orientar a organização das horas de estudo da semana com base em datas de provas, prazos de trabalhos e notas, e aplicar os métodos de repetição espaçada e da técnica de Feynman.

Por restrição do projeto, não há banco de dados nem qualquer persistência. O Tutor é um endpoint de chat sem estado: cada requisição recebe uma mensagem e devolve uma resposta. Portanto, toda a lógica de tutoria, avaliação e organização de estudos é expressa pelo comportamento conversacional definido na constante SYSTEM_PROMPT do app.py e pelo conteúdo que o usuário fornece na própria mensagem. O Tutor não armazena cronogramas, notas ou histórico entre requisições; ele trabalha com as informações presentes na conversa atual.

## Glossário

- **Tutor**: O chatbot de estudos, personagem que responde ao usuário. Possui personalidade rígida e exigente.
- **Aplicacao**: O servidor Flask definido em app.py que expõe as rotas e intermedia a comunicação com o Bedrock.
- **Rota_Chat**: A rota HTTP POST `/chat` que recebe `{"message": "..."}` e devolve `{"reply": "..."}`.
- **Rota_Pagina**: A rota HTTP GET `/` que exibe a página de chat em `templates/index.html`.
- **Bedrock**: O serviço Amazon Bedrock, acessado via boto3 (`bedrock-runtime`, `invoke_model`), na região `us-east-1`.
- **System_Prompt**: A constante `SYSTEM_PROMPT` em app.py que define a personalidade, o tom e os limites do Tutor.
- **Repeticao_Espacada**: Método de estudo em que a revisão do conteúdo é distribuída em intervalos crescentes ao longo do tempo.
- **Tecnica_Feynman**: Método de estudo em que o estudante explica um conceito em linguagem simples para identificar e corrigir lacunas de entendimento.
- **Mensagem_Vazia**: Uma mensagem cujo conteúdo é ausente, nulo ou composto apenas por espaços em branco.
- **Plano_Semanal**: A distribuição sugerida pelo Tutor das horas de estudo ao longo dos dias da semana corrente da conversa.

## Requisitos

### Requisito 1: Exibição da página de chat

**User Story:** Como usuário, quero acessar uma página de chat no navegador, para que eu possa conversar com o Tutor.

#### Acceptance Criteria

1. WHEN o usuário acessa a Rota_Pagina por meio de requisição GET, THE Aplicacao SHALL retornar o conteúdo de `templates/index.html` com status HTTP 200.

### Requisito 2: Recebimento de mensagens do usuário

**User Story:** Como usuário, quero enviar uma mensagem de texto ao Tutor, para que eu receba uma resposta de tutoria.

#### Acceptance Criteria

1. WHEN a Rota_Chat recebe uma requisição POST contendo `{"message": "..."}` com conteúdo de texto não vazio e com no máximo 4000 caracteres, THE Aplicacao SHALL encaminhar o texto da mensagem ao Bedrock e retornar a resposta no formato `{"reply": "..."}` com status HTTP 200.
2. IF a Rota_Chat recebe uma Mensagem_Vazia, THEN THE Aplicacao SHALL retornar status HTTP 400 com um corpo JSON contendo um campo de erro indicando que a mensagem é obrigatória, sem encaminhar a requisição ao Bedrock.
3. IF a Rota_Chat recebe uma requisição POST cujo conteúdo de texto excede 4000 caracteres, THEN THE Aplicacao SHALL retornar status HTTP 400 com um corpo JSON contendo um campo de erro indicando que a mensagem excede o tamanho máximo permitido, sem encaminhar a requisição ao Bedrock.
4. IF o Bedrock falha ao processar a mensagem ou não retorna resposta dentro de 30 segundos, THEN THE Aplicacao SHALL retornar status HTTP 200 com um corpo JSON no formato `{"reply": "..."}` contendo uma mensagem amigável informando que a resposta de tutoria não pôde ser gerada no momento.
5. THE Aplicacao SHALL serializar as respostas JSON com acentos legíveis definindo `app.json.ensure_ascii = False`.

### Requisito 3: Integração com Amazon Bedrock

**User Story:** Como usuário, quero que as respostas do Tutor sejam geradas por um modelo de linguagem, para que a tutoria seja contextual e útil.

#### Acceptance Criteria

1. WHEN a Aplicacao gera uma resposta do Tutor, THE Aplicacao SHALL invocar o Bedrock usando o cliente `bedrock-runtime` da boto3 por meio da operação `invoke_model` na região `us-east-1`.
2. THE Aplicacao SHALL usar o Model ID `us.anthropic.claude-haiku-4-5-20251001-v1:0` ao invocar o Bedrock.
3. THE Aplicacao SHALL obter as credenciais AWS exclusivamente a partir de variáveis de ambiente.
4. IF a invocação do Bedrock falha ou excede 30 segundos, THEN THE Aplicacao SHALL retornar status HTTP 200 com um corpo JSON no formato `{"reply": "..."}` contendo uma mensagem amigável informando que a resposta não pôde ser gerada no momento.

### Requisito 4: Personalidade rígida do Tutor

**User Story:** Como usuário, quero que o Tutor seja rígido e exigente, para que eu mantenha disciplina nos estudos.

#### Acceptance Criteria

1. THE System_Prompt SHALL instruir o Tutor a, em cada resposta de orientação de estudos, usar linguagem direta e imperativa, estabelecer ao menos uma meta ou ação de estudo objetiva e evitar elogios sem evidência de desempenho relatada pelo usuário.
2. WHEN o usuário relata falta de dedicação ou não cumprimento de metas de estudo, THE Tutor SHALL, na resposta, apontar explicitamente o não cumprimento relatado e indicar ao menos uma ação corretiva concreta de estudo.
3. THE System_Prompt SHALL restringir o escopo do Tutor a assuntos de estudo, tutoria e organização acadêmica.
4. IF o usuário envia uma mensagem cujo conteúdo não trata de estudo, tutoria ou organização acadêmica, THEN THE Tutor SHALL recusar-se a tratar o assunto na resposta e redirecionar o usuário para assuntos de estudo.

### Requisito 5: Tutoria nas matérias

**User Story:** Como usuário, quero que o Tutor me tutore nas minhas matérias, para que eu compreenda melhor os conteúdos.

#### Acceptance Criteria

1. WHEN o usuário informa uma matéria ou um conteúdo de estudo, THE Tutor SHALL fornecer explicações, orientações e questionamentos relacionados a essa matéria na resposta.
2. WHEN o usuário demonstra dúvida sobre um conceito, THE Tutor SHALL explicar o conceito e propor uma forma de o usuário verificar o próprio entendimento.

### Requisito 6: Técnica de Feynman

**User Story:** Como usuário, quero que o Tutor use a técnica de Feynman, para que eu identifique lacunas no meu entendimento ao explicar os conteúdos.

#### Acceptance Criteria

1. WHEN o usuário inicia o estudo de um conceito com o Tutor, THE Tutor SHALL solicitar que o usuário explique o conceito com as próprias palavras em linguagem simples, apresentando uma única solicitação explícita por conceito.
2. WHEN o usuário apresenta uma explicação de um conceito, THE Tutor SHALL comparar a explicação com a definição de referência do conceito e identificar as lacunas, considerando como lacuna qualquer elemento essencial da definição de referência que esteja ausente, incorreto ou incompleto na explicação.
3. WHEN o Tutor identifica uma ou mais lacunas na explicação do usuário, THE Tutor SHALL apresentar cada lacuna identificada e indicar, para cada uma, o conteúdo específico que deve ser revisado.
4. WHEN o Tutor não identifica nenhuma lacuna na explicação do usuário, THE Tutor SHALL confirmar que a explicação está completa e correta em relação à definição de referência do conceito.
5. IF o usuário não fornece uma explicação ou fornece uma explicação vazia quando solicitado, THEN THE Tutor SHALL reiterar a solicitação de explicação e informar que a explicação é necessária para aplicar a técnica de Feynman.

### Requisito 7: Repetição espaçada

**User Story:** Como usuário, quero que o Tutor aplique repetição espaçada, para que eu retenha o conteúdo a longo prazo.

#### Acceptance Criteria

1. WHEN o Tutor orienta a revisão de um conteúdo, THE Tutor SHALL propor, na mensagem atual, uma sequência de no mínimo 3 intervalos de revisão em que cada intervalo é estritamente maior que o anterior, seguindo o método de repetição espaçada.
2. WHEN o usuário informa a data de uma prova ou prazo, THE Tutor SHALL distribuir as revisões do conteúdo relacionado em uma sequência de intervalos estritamente crescentes entre a data atual e a data informada, utilizando apenas as informações presentes na mensagem atual.
3. IF o usuário informa uma data de prova ou prazo anterior ou igual à data atual, THEN THE Tutor SHALL recusar a geração do cronograma e responder com uma mensagem indicando que a data informada é inválida por não estar no futuro.
4. IF o intervalo entre a data atual e a data informada não comporta pelo menos 2 revisões em intervalos crescentes, THEN THE Tutor SHALL propor um cronograma de revisão intensiva de no mínimo 2 revisões dentro do período disponível e indicar que o prazo é curto para repetição espaçada completa.

### Requisito 8: Avaliação de desempenho

**User Story:** Como usuário, quero que o Tutor avalie meu desempenho, para que eu saiba quais pontos preciso reforçar.

#### Acceptance Criteria

1. WHEN o usuário informa, na mensagem atual, notas, resultados de exercícios ou autoavaliações, THE Tutor SHALL analisar exclusivamente os dados presentes nessa mensagem e indicar ao menos um ponto forte na resposta.
2. WHEN o usuário informa, na mensagem atual, notas, resultados de exercícios ou autoavaliações, THE Tutor SHALL indicar ao menos um ponto a melhorar na resposta, considerando ponto a melhorar como todo tópico cujos dados informados fiquem abaixo do critério de acerto ou domínio declarado pelo usuário.
3. WHEN o Tutor identifica ao menos um ponto a melhorar a partir dos dados informados na mensagem atual, THE Tutor SHALL ordenar as orientações de estudo da resposta do ponto a melhorar de menor desempenho para o de maior desempenho.
4. IF a mensagem atual não contém dados de desempenho avaliáveis (notas, resultados de exercícios ou autoavaliações), THEN THE Tutor SHALL responder solicitando que o usuário informe esses dados na mensagem e SHALL informar que não mantém histórico de interações anteriores.
5. IF os dados informados na mensagem atual são insuficientes para identificar pontos fortes ou pontos a melhorar, THEN THE Tutor SHALL informar quais dados adicionais são necessários e SHALL abster-se de apresentar uma avaliação de desempenho.

### Requisito 9: Organização das horas de estudo da semana

**User Story:** Como usuário, quero que o Tutor organize minhas horas de estudo na semana, para que eu estude de forma equilibrada conforme provas, trabalhos e notas.

#### Acceptance Criteria

1. WHEN o usuário informa, na mensagem atual, datas de provas, prazos de trabalhos, notas e o total de horas semanais disponíveis para estudo, THE Tutor SHALL sugerir um Plano_Semanal que distribua exatamente esse total de horas entre as matérias ao longo dos dias da semana corrente.
2. WHEN o Tutor monta o Plano_Semanal, THE Tutor SHALL alocar proporcionalmente mais horas às matérias com notas mais baixas e aos prazos mais próximos informados na mensagem atual, apresentando as matérias em ordem decrescente de prioridade.
3. IF o usuário solicita um Plano_Semanal sem informar datas de provas, prazos de trabalhos, notas ou o total de horas semanais disponíveis, THEN THE Tutor SHALL solicitar ao usuário, de forma explícita, as informações faltantes antes de sugerir o Plano_Semanal.
4. IF o usuário solicita um Plano_Semanal informando provas, prazos e notas mas sem informar o total de horas semanais disponíveis, THEN THE Tutor SHALL solicitar ao usuário o total de horas semanais disponíveis antes de sugerir o Plano_Semanal.

### Requisito 10: Operação sem persistência

**User Story:** Como mantenedor do projeto, quero que o Tutor funcione sem banco de dados, para que o projeto atenda às restrições de arquitetura.

#### Acceptance Criteria

1. THE Aplicacao SHALL processar cada requisição da Rota_Chat utilizando apenas as informações presentes na requisição atual e no System_Prompt.
2. WHERE o usuário precisa que o Tutor considere datas, notas ou histórico de estudo, THE Tutor SHALL orientar o usuário a incluir essas informações na mensagem enviada.
