# Tutor — Chatbot de Estudos

O Tutor é um chatbot de estudos construído em Python com Flask que conversa com o usuário por uma página web e gera respostas usando o Amazon Bedrock. Ele atua como um tutor gentil e motivador: tutora o usuário nas matérias, aplica a técnica de Feynman e a repetição espaçada, avalia o desempenho relatado e organiza as horas de estudo da semana.

Toda a inteligência pedagógica vive na constante `SYSTEM_PROMPT` do `app.py`. A aplicação mantém a memória da conversa por sessão (via cookie assinado do Flask) e a envia ao modelo a cada mensagem, dentro de uma janela limitada de contexto.

## Tecnologias

- Python
- Flask
- boto3
- Amazon Bedrock (Claude Haiku 4.5 — `us.anthropic.claude-haiku-4-5-20251001-v1:0`)

## Contexto

Projeto criado no II Workshop de Ciência da Computação da UNIFAL-MG, em outubro de 2026.

## Como executar

1. Clone o repositório.
2. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```
3. Configure as variáveis de ambiente AWS (requer credenciais próprias):
   ```bash
   export AWS_ACCESS_KEY_ID=...
   export AWS_SECRET_ACCESS_KEY=...
   export AWS_SESSION_TOKEN=...        # opcional, se usar credenciais temporárias
   ```
4. Inicie a aplicação:
   ```bash
   python app.py
   ```
5. Acesse http://127.0.0.1:5000 no navegador.

## Nota

Requer uma conta AWS com acesso ao Amazon Bedrock (modelo Claude Haiku 4.5 habilitado na região `us-east-1`). As credenciais são obtidas exclusivamente por variáveis de ambiente — nenhuma chave é escrita no código.

## Demonstração

[Screencast from 2026-10-22 15-18-58.webm](https://github.com/user-attachments/assets/1e1034aa-2ab6-4e8c-a149-8aaf6763930a)
