"""Tutor Chatbot - aplicação Flask com memória de conversa por sessão.

A aplicação mantém o histórico de cada conversa isolado por sessão (via cookie
assinado do Flask) e o envia ao Amazon Bedrock a cada mensagem, dentro de uma
janela limitada para não estourar o contexto do modelo. Reúne a validação de
entrada, a integração com o Bedrock, o SYSTEM_PROMPT e as rotas.
"""

import json
import os
import uuid

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from flask import Flask, jsonify, render_template, request, session

# --------------------------------------------------------------------------- #
# Configuração da aplicação Flask
# --------------------------------------------------------------------------- #
app = Flask(__name__)

# Serializa respostas JSON com acentos legíveis (Requisito 2.5).
app.json.ensure_ascii = False

# Chave usada para assinar o cookie de sessão do Flask. Em produção, defina a
# variável de ambiente FLASK_SECRET_KEY; o fallback aleatório abaixo serve
# apenas para desenvolvimento (invalida as sessões a cada reinício do processo).
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(32)


# --------------------------------------------------------------------------- #
# SYSTEM_PROMPT (Tarefa 4) — comportamento pedagógico do Tutor.
# --------------------------------------------------------------------------- #
# Toda a inteligência de tutoria é comportamental e vive neste prompt
# (Requisitos 4 a 10.2). O prompt é enviado no campo `system` de cada
# invocação do Bedrock. O histórico da conversa atual é mantido por sessão e
# enviado junto, dentro de uma janela limitada (ver conversation_histories).
SYSTEM_PROMPT = """Você é o Tutor, um chatbot de estudos gentil, acolhedor e motivador. Sua função é tutorar o usuário nas matérias dele, aplicar os métodos de estudo da técnica de Feynman e da repetição espaçada, avaliar o desempenho relatado e organizar as horas de estudo da semana. Responda sempre em português do Brasil.

# 0. FORMATO DAS RESPOSTAS
- Escreva sempre em parágrafos curtos, de no máximo 3 linhas cada. Se precisar dizer mais, quebre em vários parágrafos curtos separados por uma linha em branco.
- Nunca use bullet points, listas com marcadores, listas numeradas ou travessões para enumerar itens. Expresse tudo em texto corrido, dentro dos parágrafos.
- Quando precisar apresentar uma sequência (por exemplo, intervalos de revisão ou um plano de horas), descreva-a em prosa, dentro dos parágrafos curtos, sem transformá-la em lista.

# 1. PERSONA E TOM (gentil e motivador)
- Seja gentil, acolhedor e encorajador. Trate o usuário com paciência e empatia, como um tutor que torce pelo progresso dele e o apoia nos momentos difíceis.
- Use linguagem calorosa e convidativa. Em vez de ordens ríspidas, faça convites e sugestões ("que tal revisarmos...", "podemos começar por..."), sempre deixando claro o próximo passo de estudo.
- Em toda orientação de estudos, proponha ao menos uma ação de estudo concreta e alcançável (o que fazer, sobre o quê e com qual propósito), apresentada de forma motivadora.
- Reconheça o esforço do usuário e motive-o a continuar. Pode oferecer incentivo e palavras de ânimo mesmo sem dados de desempenho; apenas não afirme resultados ou méritos específicos que o usuário não tenha relatado.
- Quando o usuário relatar falta de dedicação, atraso ou procrastinação, acolha a dificuldade sem julgar, ajude-o a entender o que atrapalhou e sugira com gentileza um próximo passo pequeno e concreto para retomar os estudos.
- Nunca faça perguntas conversacionais, retóricas ou de acompanhamento ao usuário (por exemplo, "E você, como se sente?", "Quer que eu continue?", "Faz sentido?", "Posso seguir?"). Responda, apresente a orientação ou o próximo passo e aguarde a próxima mensagem do usuário, sem devolver a palavra com uma pergunta. Em vez de encerrar com uma pergunta, encerre com uma afirmação ou um convite à ação (por exemplo, "Quando terminar, é só me contar o resultado.").
- Exceção: quando uma tarefa exigir obrigatoriamente um dado que não está na conversa, você pode e deve solicitá-lo de forma objetiva, pois sem ele a tarefa não pode ser executada. Isso vale apenas para a solicitação de explicação da técnica de Feynman (seção 4) e para os dados indispensáveis de repetição espaçada, avaliação de desempenho e plano semanal (seções 5, 6 e 7). Faça a solicitação como um pedido direto e necessário, não como pergunta conversacional, e limite-se ao dado estritamente faltante.

# 2. ESCOPO RESTRITO (apenas assuntos acadêmicos)
- Seu escopo é exclusivamente estudo, tutoria e organização acadêmica.
- Se a mensagem do usuário não tratar de estudo, tutoria ou organização acadêmica, recuse-se a tratar o assunto e redirecione o usuário de volta para os estudos, propondo uma ação de estudo concreta. Não responda a perguntas fora do escopo acadêmico (por exemplo, entretenimento, fofoca, opiniões pessoais, assuntos aleatórios).

# 3. TUTORIA DAS MATÉRIAS
- Quando o usuário informar uma matéria ou um conteúdo de estudo, forneça explicações do conteúdo, orientações de como estudá-lo e questionamentos que levem o usuário a raciocinar sobre o tema.
- Quando o usuário demonstrar dúvida sobre um conceito, explique o conceito de forma clara e proponha uma forma concreta de o usuário verificar o próprio entendimento (por exemplo, resolver um exercício, explicar o conceito com as próprias palavras ou responder a uma pergunta de checagem).

# 4. TÉCNICA DE FEYNMAN
- Ao iniciar o estudo de um conceito com o usuário, faça UMA ÚNICA solicitação explícita para que ele explique o conceito com as próprias palavras, em linguagem simples. Não faça múltiplas solicitações simultâneas para o mesmo conceito.
- Quando o usuário apresentar uma explicação, compare-a com a definição de referência correta do conceito e identifique as lacunas. Considere lacuna qualquer elemento essencial da definição de referência que esteja ausente, incorreto ou incompleto na explicação do usuário.
- Quando identificar uma ou mais lacunas, apresente cada lacuna de forma clara e, para cada uma, indique o conteúdo específico que o usuário deve revisar para corrigi-la. Descreva as lacunas em prosa, dentro de parágrafos curtos, sem transformá-las em lista.
- Quando a explicação do usuário não tiver nenhuma lacuna, confirme explicitamente que ela está completa e correta em relação à definição de referência do conceito.
- Se o usuário não fornecer uma explicação, ou fornecer uma explicação vazia quando solicitado, reitere a solicitação de explicação e informe que a explicação é necessária para aplicar a técnica de Feynman.

# 5. REPETIÇÃO ESPAÇADA
- Ao orientar a revisão de um conteúdo, proponha sempre uma sequência de no mínimo 3 intervalos de revisão, em que cada intervalo seja estritamente maior que o anterior (intervalos crescentes), seguindo o método de repetição espaçada. Descreva essa sequência em prosa, dentro de parágrafos curtos, sem usar lista.
- Quando o usuário informar a data de uma prova ou prazo, distribua as revisões do conteúdo relacionado em uma sequência de intervalos estritamente crescentes entre a data atual e a data informada, usando apenas as informações presentes na mensagem atual. Peça ao usuário a data de hoje se precisar dela e ela não estiver na mensagem.
- Se o usuário informar uma data de prova ou prazo anterior ou igual à data atual, recuse a geração do cronograma e responda que a data informada é inválida por não estar no futuro.
- Se o intervalo entre a data atual e a data informada for curto demais para comportar pelo menos 2 revisões em intervalos crescentes, proponha um cronograma de revisão intensiva com no mínimo 2 revisões dentro do período disponível e avise explicitamente que o prazo é curto para uma repetição espaçada completa.

# 6. AVALIAÇÃO DE DESEMPENHO
- Analise os dados de desempenho (notas, resultados de exercícios ou autoavaliações) presentes na conversa atual, considerando tanto a mensagem atual quanto as mensagens anteriores desta mesma conversa.
- Quando o usuário informar dados de desempenho, destaque com sinceridade ao menos um ponto forte, celebrando o progresso, e aponte com delicadeza ao menos um ponto a melhorar. Considere ponto a melhorar todo tópico cujos dados informados fiquem abaixo do critério de acerto ou domínio declarado pelo usuário.
- Seja sempre honesto sobre os pontos a melhorar: não esconda nem suavize a ponto de omitir uma dificuldade real. Apresente-os de forma encorajadora, começando pelo tópico de menor desempenho e tratando-o como a prioridade onde um pouco de atenção trará o maior ganho.
- Se não houver, em nenhum ponto da conversa atual, dados de desempenho avaliáveis (notas, resultados de exercícios ou autoavaliações), convide gentilmente o usuário a compartilhá-los. Não invente uma avaliação.
- Se os dados informados forem insuficientes para identificar pontos fortes ou pontos a melhorar, informe com gentileza exatamente quais dados adicionais ajudariam e abstenha-se de apresentar uma avaliação de desempenho.

# 7. ORGANIZAÇÃO DAS HORAS DE ESTUDO DA SEMANA (Plano Semanal)
- Quando o usuário informar, na mensagem atual, datas de provas, prazos de trabalhos, notas e o total de horas semanais disponíveis para estudo, sugira um Plano Semanal que distribua EXATAMENTE esse total de horas entre as matérias ao longo dos dias da semana corrente. A soma das horas alocadas deve ser igual ao total informado — nem mais, nem menos.
- Ao montar o Plano Semanal, aloque proporcionalmente mais horas às matérias com notas mais baixas e aos prazos mais próximos informados na mensagem atual. Apresente as matérias em ordem decrescente de prioridade (da mais prioritária para a menos prioritária), descrevendo o plano em prosa dentro de parágrafos curtos, sem usar lista ou tabela.
- Se o usuário pedir um Plano Semanal sem informar datas de provas, prazos de trabalhos, notas ou o total de horas semanais disponíveis, solicite explicitamente as informações faltantes ANTES de sugerir o plano. Não monte o plano com dados inventados.
- Se o usuário informar provas, prazos e notas, mas não informar o total de horas semanais disponíveis, solicite esse total de horas antes de sugerir o plano.

# 8. MEMÓRIA DA CONVERSA ATUAL
- Você mantém a memória das mensagens trocadas ao longo da conversa atual. Use o que o usuário já informou antes nesta conversa (datas, notas, prazos, matérias e contexto de estudo) para dar continuidade, sem pedir novamente o que já foi dito.
- Sua memória se limita à conversa atual: você não tem acesso a conversas anteriores encerradas. Se precisar de uma informação que não apareceu em nenhum momento desta conversa, peça-a explicitamente ao usuário.
- Para economizar contexto, as mensagens mais antigas de conversas muito longas podem não estar mais disponíveis. Se perceber que um dado relevante já citado não está mais acessível, peça ao usuário que o reinforme.
"""


# --------------------------------------------------------------------------- #
# Cliente Bedrock e geração de resposta (Tarefa 3)
# --------------------------------------------------------------------------- #

# Model ID do Claude no Bedrock (Requisito 3.2).
BEDROCK_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

# Versão do esquema de mensagens da Anthropic no Bedrock.
ANTHROPIC_VERSION = "bedrock-2023-05-31"

# Limite de tokens gerados na resposta do Tutor.
MAX_TOKENS = 1024

# Mensagem amigável de fallback (Requisitos 2.4, 3.4): qualquer falha do
# Bedrock (serviço, timeout de 30s ou corpo malformado) vira esta resposta,
# de modo que o endpoint de chat nunca quebre para o usuário.
MENSAGEM_FALLBACK = (
    "Desculpe, não consegui gerar a resposta de tutoria agora. "
    "Tente novamente em instantes."
)

# Cliente boto3 bedrock-runtime na região us-east-1 (Requisito 3.1).
# - read_timeout=30 implementa o limite de 30 segundos (Requisitos 2.4, 3.4).
# - retries max_attempts=0 evita retries para respeitar o orçamento de 30s.
# - Credenciais são resolvidas automaticamente pelo boto3 a partir das
#   variáveis de ambiente (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY e,
#   opcionalmente, AWS_SESSION_TOKEN). Nenhuma chave é escrita no código
#   (Requisito 3.3).
bedrock = boto3.client(
    "bedrock-runtime",
    region_name="us-east-1",
    config=Config(read_timeout=30, connect_timeout=10, retries={"max_attempts": 0}),
)

# --------------------------------------------------------------------------- #
# Memória de conversa por sessão
# --------------------------------------------------------------------------- #
# Cada usuário (identificado por um id guardado no cookie de sessão assinado do
# Flask) tem seu próprio histórico. Assim as conversas não se misturam nem
# vazam entre usuários diferentes, mesmo com várias requisições simultâneas.
#
# Observação: este dicionário vive na memória do processo. Com múltiplos
# workers/processos o histórico não é compartilhado entre eles; para isso seria
# necessário um armazenamento externo (ex.: Redis). Para um único processo de
# desenvolvimento, é suficiente.
conversation_histories: dict[str, list] = {}

# Tetos da janela de histórico. São deliberadamente conservadores para que o
# total enviado ao Bedrock fique muito abaixo da janela de contexto do modelo
# (Claude Haiku 4.5: 200.000 tokens de entrada), tornando o estouro de contexto
# improvável na prática.
#   - MAX_HISTORY_MESSAGES: nº máximo de mensagens (usuário + assistente)
#     mantidas. 20 mensagens = 10 trocas completas.
#   - MAX_HISTORY_CHARS: orçamento total de caracteres do histórico. Com a
#     mensagem do usuário limitada a 4000 caracteres, 40.000 caracteres
#     (~10 mil tokens) deixam folga enorme em relação aos 200k de contexto.
MAX_HISTORY_MESSAGES = 20
MAX_HISTORY_CHARS = 40_000


def _texto_da_mensagem(mensagem: dict) -> str:
    """Extrai o texto concatenado dos blocos de conteúdo de uma mensagem."""
    return "".join(
        bloco.get("text", "") for bloco in mensagem.get("content", [])
    )


def _aparar_historico(historico: list) -> list:
    """Reduz o histórico para respeitar os tetos de mensagens e caracteres.

    Remove as mensagens mais antigas até que o histórico caiba em
    ``MAX_HISTORY_MESSAGES`` e ``MAX_HISTORY_CHARS``, preservando sempre as
    trocas mais recentes (que são as mais relevantes para a continuidade da
    conversa). Mantém o histórico começando por uma mensagem de usuário para
    não enviar um bloco iniciado por ``assistant`` ao Bedrock.
    """
    # Teto por número de mensagens.
    if len(historico) > MAX_HISTORY_MESSAGES:
        historico = historico[-MAX_HISTORY_MESSAGES:]

    # Teto por caracteres: descarta as mais antigas enquanto estourar.
    total = sum(len(_texto_da_mensagem(m)) for m in historico)
    while len(historico) > 1 and total > MAX_HISTORY_CHARS:
        removida = historico.pop(0)
        total -= len(_texto_da_mensagem(removida))

    # Garante que o histórico comece por uma mensagem de usuário.
    while historico and historico[0].get("role") != "user":
        historico.pop(0)

    return historico


def _obter_historico_da_sessao() -> list:
    """Retorna (criando se necessário) o histórico da sessão atual.

    Usa um id de sessão guardado no cookie assinado do Flask para isolar o
    histórico por usuário/navegador. Deve ser chamado dentro de um contexto de
    requisição.
    """
    sid = session.get("sid")
    if not sid:
        sid = uuid.uuid4().hex
        session["sid"] = sid
    return conversation_histories.setdefault(sid, [])


def gerar_resposta(texto_usuario: str, historico: list) -> str:
    """Gera a resposta do Tutor invocando o Amazon Bedrock.

    Constrói o corpo da requisição no esquema de mensagens da Anthropic
    (Messages API) usando o histórico de conversa fornecido, invoca
    ``invoke_model`` no modelo Claude e extrai o texto gerado. Qualquer falha
    (erro de serviço, timeout de leitura de 30s ou corpo de resposta malformado)
    é capturada e convertida em uma string de fallback amigável em português,
    garantindo que a função sempre retorne uma string.

    A mensagem do usuário é anexada a ``historico`` antes da chamada e, em caso
    de sucesso, a resposta do Tutor também é anexada. O histórico é aparado
    para respeitar os tetos de janela (número de mensagens e caracteres), de
    modo que o conteúdo enviado ao Bedrock permaneça muito abaixo da janela de
    contexto do modelo.

    Args:
        texto_usuario: a mensagem do usuário já validada (não vazia, até
            4000 caracteres após trim).
        historico: a lista de mensagens da sessão atual, no esquema de
            mensagens da Anthropic. É modificada in-place.

    Returns:
        O texto gerado pelo Tutor, ou ``MENSAGEM_FALLBACK`` em caso de
        qualquer falha na invocação ou no parsing (Requisitos 2.4, 3.4).
    """
    # Adiciona a mensagem do usuário ao histórico antes de chamar o Bedrock.
    historico.append(
        {
            "role": "user",
            "content": [{"type": "text", "text": texto_usuario}],
        }
    )

    # Apara o histórico para respeitar a janela antes de montar o corpo.
    historico[:] = _aparar_historico(historico)

    corpo = {
        "anthropic_version": ANTHROPIC_VERSION,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "messages": historico,
    }

    try:
        resposta = bedrock.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            body=json.dumps(corpo),
        )
        corpo_resposta = json.loads(resposta["body"].read())
        texto_resposta = corpo_resposta["content"][0]["text"]
        # Adiciona a resposta do Tutor ao histórico de conversa.
        historico.append(
            {
                "role": "assistant",
                "content": [{"type": "text", "text": texto_resposta}],
            }
        )
        return texto_resposta
    except (
        ClientError,
        BotoCoreError,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
    ):
        # ClientError/BotoCoreError cobrem falhas de serviço e o
        # ReadTimeoutError de 30s (subclasse de BotoCoreError). As demais
        # exceções cobrem corpo de resposta ausente/malformado no parsing.
        return MENSAGEM_FALLBACK


# --------------------------------------------------------------------------- #
# Validação de entrada (Tarefa 2)
# --------------------------------------------------------------------------- #

# Limite máximo de caracteres aceitos para a mensagem (Requisito 2.3).
TAMANHO_MAXIMO_MENSAGEM = 4000

# Mensagens de erro de validação (em português, legíveis com ensure_ascii=False).
ERRO_MENSAGEM_OBRIGATORIA = "A mensagem é obrigatória."
ERRO_MENSAGEM_LONGA = "A mensagem excede o tamanho máximo de 4000 caracteres."


def validar_mensagem(payload):
    """Valida o payload de entrada da Rota_Chat.

    Função pura (sem efeitos colaterais): não chama o Bedrock, não lê nem
    escreve estado externo. Concentra toda a lógica de validação para que
    entradas inválidas jamais atinjam o serviço externo.

    Args:
        payload: corpo da requisição já desserializado. Pode ser ``None`` ou
            qualquer tipo (JSON inválido/sem Content-Type chega como ``None``).

    Returns:
        Uma tupla ``(texto, erro, status)``:
          * mensagem válida  -> ``(texto, None, 200)``
          * Mensagem_Vazia   -> ``(None, "A mensagem é obrigatória.", 400)``
          * acima do limite  -> ``(None, "A mensagem excede o tamanho máximo
            de 4000 caracteres.", 400)``

    Regras (Requisitos 2.2, 2.3):
      * Payload ausente ou não-dict é tratado como ``Mensagem_Vazia``.
      * ``message`` ausente, nula, não-string ou composta apenas por espaços
        em branco gera erro de obrigatoriedade (400).
      * Mensagem cujo comprimento (após remoção de espaços nas bordas) excede
        4000 caracteres gera erro de tamanho (400). ``len == 4000`` é válida;
        ``len == 4001`` é rejeitada.
    """
    # Tolera payload ausente ou não-dict: tratado como Mensagem_Vazia.
    if not isinstance(payload, dict):
        return None, ERRO_MENSAGEM_OBRIGATORIA, 400

    message = payload.get("message")

    # Ausente, nula ou não-string -> obrigatoriedade.
    if not isinstance(message, str):
        return None, ERRO_MENSAGEM_OBRIGATORIA, 400

    texto = message.strip()

    # Composta apenas por espaços em branco -> obrigatoriedade.
    if texto == "":
        return None, ERRO_MENSAGEM_OBRIGATORIA, 400

    # Acima do limite máximo -> erro de tamanho.
    if len(texto) > TAMANHO_MAXIMO_MENSAGEM:
        return None, ERRO_MENSAGEM_LONGA, 400

    # Mensagem válida: retorna o texto (após trim) com status de sucesso.
    return texto, None, 200


# --------------------------------------------------------------------------- #
# Rotas (Tarefa 5)
# --------------------------------------------------------------------------- #


@app.route("/")
def pagina():
    """Rota_Pagina (GET /): exibe a página de chat.

    Renderiza e retorna o conteúdo de ``templates/index.html`` com status
    HTTP 200 (Requisito 1.1). O Flask define o status 200 por padrão quando a
    view retorna apenas o corpo da resposta.
    """
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    """Rota_Chat (POST /chat): recebe a mensagem e devolve a resposta do Tutor.

    Fluxo:
      1. Lê o corpo com ``request.get_json(silent=True)``. JSON inválido ou
         ausência de ``Content-Type`` resulta em ``None``, que ``validar_mensagem``
         trata como ``Mensagem_Vazia``.
      2. Chama ``validar_mensagem``. Se inválido (``erro`` não-``None``), retorna
         HTTP 400 com ``{"error": ...}`` sem jamais chamar o Bedrock
         (Requisitos 2.2, 2.3).
      3. Para mensagem válida, recupera o histórico da sessão atual e chama
         ``gerar_resposta``, retornando HTTP 200 com ``{"reply": ...}``. O
         histórico é isolado por sessão e aparado para caber na janela de
         contexto. Como ``gerar_resposta`` sempre retorna uma string (inclusive
         o fallback amigável em caso de falha/timeout do Bedrock), o endpoint
         nunca retorna 5xx por causa do Bedrock (Requisitos 2.1, 2.4, 3.4).
    """
    payload = request.get_json(silent=True)

    texto, erro, status = validar_mensagem(payload)
    if erro is not None:
        return jsonify({"error": erro}), status

    historico = _obter_historico_da_sessao()
    resposta = gerar_resposta(texto, historico)
    return jsonify({"reply": resposta}), 200


if __name__ == "__main__":
    app.run(host="localhost", port=5000)
