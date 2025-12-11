# ECS Processor - Gerador de Documentos Técnicos

Processador ECS Fargate que transforma transcrições de vídeos em documentos técnicos estruturados de treinamento e troubleshooting usando AWS Bedrock (Claude Sonnet 4).

---

## 📋 Índice

1. [Visão Geral](#visão-geral)
2. [Arquitetura](#arquitetura)
3. [Pipeline de 6 Etapas](#pipeline-de-6-etapas)
4. [Componentes](#componentes)
5. [Configuração](#configuração)
6. [Uso](#uso)
7. [Desenvolvimento Local](#desenvolvimento-local)
8. [Deploy](#deploy)
9. [Monitoramento](#monitoramento)
10. [Troubleshooting](#troubleshooting)

---

## Visão Geral

### Responsabilidades

O processador ECS é responsável por:

1. **Carregar transcrições** do S3 (formato JSON do AWS Transcribe)
2. **Chunking adaptativo** para vídeos longos (>200K tokens)
3. **Processar via LLM** usando Claude Sonnet 4 na AWS Bedrock
4. **Gerar documentos** em Markdown e DOCX
5. **Upload no S3** e atualização do DynamoDB

### Características

- ✅ Pipeline de 6 etapas granulares
- ✅ Suporte a transcrições longas (até 3 horas de vídeo)
- ✅ Chunking inteligente com overlap
- ✅ Rate limiting e retry logic
- ✅ Multi-formato: Markdown + DOCX
- ✅ Tracking completo de custos e tokens
- ✅ Error handling robusto

---

## Arquitetura

### Componentes Principais

```
┌─────────────────────────────────────────┐
│           main.py                       │
│   (Entry Point & Orchestration)         │
└───────────┬─────────────────────────────┘
            │
            ├──────────────┬──────────────┬─────────────┐
            │              │              │             │
    ┌───────▼─────┐  ┌────▼──────┐  ┌───▼────────┐ ┌──▼──────┐
    │transcription│  │llm_client │  │document_   │ │__init__ │
    │  _parser    │  │           │  │ generator  │ │         │
    └─────────────┘  └───────────┘  └────────────┘ └─────────┘
```

### Fluxo de Dados

```
S3 Transcription → Parse → Chunk → Stage 1-5 (LLM) → Stage 6 (Output) → S3
                                                                         ↓
                                                                    DynamoDB
```

---

## Pipeline de 6 Etapas

### Etapa 1: Limpeza da Transcrição

- Parse do JSON do AWS Transcribe
- Formatação com timestamps e speakers
- Remoção de ruído (conversas não técnicas)

**Input**: JSON do Transcribe  
**Output**: Texto limpo formatado  
**LLM**: Não (processamento local)

### Etapa 2: Extração de Conteúdo Técnico

- Identificação de erros e diagnósticos
- Extração de soluções e comandos
- Riscos de ambiente
- Regras de negócio
- Configurações

**Input**: Texto limpo  
**Output**: JSON estruturado  
**LLM**: Sim (Claude Sonnet 4)

### Etapa 3: Mapeamento de Soluções

- Criação de matriz problema → solução
- Medidas preventivas
- Passos de debugging

**Input**: JSON técnico da Etapa 2  
**Output**: JSON com mapeamentos  
**LLM**: Sim (Claude Sonnet 4)

### Etapa 4: Estruturação do Documento

- Criação do outline do documento
- Organização em seções lógicas
- Definição de estrutura (sem conteúdo)

**Input**: JSON de soluções da Etapa 3  
**Output**: Outline estruturado  
**LLM**: Sim (Claude Sonnet 4)

### Etapa 5: Redação do Conteúdo

- Escrita completa do documento em Markdown
- Tom profissional e didático
- Formatação rica (code blocks, tabelas, listas)

**Input**: Outline da Etapa 4  
**Output**: Documento Markdown completo  
**LLM**: Sim (Claude Sonnet 4, max_tokens=8192)

### Etapa 6: Geração de Outputs

- Salvar Markdown no S3
- Conversão Markdown → DOCX (python-docx)
- Salvar DOCX no S3
- Validação de outputs

**Input**: Markdown da Etapa 5  
**Output**: Arquivos `.md` e `.docx` no S3  
**LLM**: Não (processamento local)

---

## Componentes

### 1. `transcription_parser.py`

**Classe Principal**: `TranscriptionParser`

**Funcionalidades**:
- Parse de JSON do AWS Transcribe
- Identificação de speakers
- Extração de timestamps
- Chunking adaptativo para transcrições longas
- Contagem de tokens

**Exemplo de Uso**:

```python
from transcription_parser import TranscriptionParser

parser = TranscriptionParser(max_tokens_per_chunk=100000)

# Parse JSON
parsed = parser.parse_transcribe_json(json_data)

# Chunk se necessário
chunks = parser.chunk_transcription(parsed)
print(f"Created {len(chunks)} chunk(s)")
```

### 2. `llm_client.py`

**Classe Principal**: `BedrockLLMClient`

**Funcionalidades**:
- Cliente LangChain para AWS Bedrock
- Retry com exponential backoff
- Rate limiting (10 req/min, 100K tokens/min)
- Streaming support
- Token tracking e cálculo de custos

**Exemplo de Uso**:

```python
from llm_client import BedrockLLMClient

client = BedrockLLMClient(
    model_id="anthropic.claude-sonnet-4-5-20250929-v1:0",
    temperature=0.7,
    max_tokens=4096
)

# Invocar modelo
response, usage = client.invoke(prompt)
print(f"Tokens: {usage.total_tokens}, Cost: ${usage.calculate_cost()}")

# Com JSON output
json_response, usage = client.invoke_with_json_output(prompt)
```

### 3. `document_generator.py`

**Classe Principal**: `DocumentGenerator`

**Funcionalidades**:
- Orquestração completa do pipeline
- Processamento single-chunk e multi-chunk
- Geração de Markdown e DOCX
- Merge de resultados de chunks

**Exemplo de Uso**:

```python
from document_generator import DocumentGenerator

generator = DocumentGenerator(llm_client, parser, s3_client)

result = generator.generate_document(
    execution_id="uuid-123",
    transcription_s3_uri="s3://bucket/transcription.json",
    output_bucket="output-bucket"
)

print(f"Document generated: ${result.total_cost_usd:.4f}")
print(f"Markdown: {result.markdown_s3_uri}")
print(f"DOCX: {result.docx_s3_uri}")
```

### 4. `main.py`

**Função Principal**: `lambda_handler(event, context)`

**Responsabilidades**:
- Entry point do ECS task
- Configuração e validação
- Inicialização de componentes
- Orquestração do fluxo
- Error handling
- Update do DynamoDB

---

## Configuração

### Variáveis de Ambiente

**Obrigatórias**:

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `TRACKING_TABLE` | Nome da tabela DynamoDB | `ai-techne-academy-tracking-dev` |
| `OUTPUT_BUCKET` | Bucket S3 para outputs | `ai-techne-academy-output-dev` |

**Opcionais** (com defaults):

| Variável | Descrição | Default |
|----------|-----------|---------|
| `AWS_REGION` | Região AWS | `us-east-1` |
| `BEDROCK_MODEL_ID` | ID do modelo Bedrock | `anthropic.claude-sonnet-4-5-20250929-v1:0` |
| `LOG_LEVEL` | Nível de log | `INFO` |
| `MAX_TOKENS_PER_CHUNK` | Max tokens por chunk | `100000` |

### IAM Permissions

O ECS Task Role precisa das seguintes permissões:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": [
        "arn:aws:s3:::input-bucket/*",
        "arn:aws:s3:::transcription-bucket/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject"
      ],
      "Resource": [
        "arn:aws:s3:::output-bucket/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": [
        "arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-5-*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem"
      ],
      "Resource": [
        "arn:aws:dynamodb:*:*:table/tracking-table-name"
      ]
    }
  ]
}
```

---

## Uso

### Event Format (Input)

```json
{
  "execution_id": "550e8400-e29b-41d4-a716-446655440000",
  "video_s3_uri": "s3://input-bucket/video.mp4",
  "transcription_s3_uri": "s3://transcription-bucket/uuid/transcription.json",
  "video_metadata": {
    "duration": 10800,
    "size_bytes": 2147483648
  }
}
```

### Response Format (Output)

**Sucesso** (statusCode: 200):

```json
{
  "statusCode": 200,
  "body": {
    "execution_id": "550e8400-e29b-41d4-a716-446655440000",
    "markdown_s3_uri": "s3://output-bucket/uuid/document.md",
    "docx_s3_uri": "s3://output-bucket/uuid/document.docx",
    "tokens_used": {
      "input": 150000,
      "output": 8000,
      "total": 158000
    },
    "cost_usd": 0.57,
    "duration_seconds": 185,
    "chunks_processed": 2,
    "stages_completed": 6
  }
}
```

**Erro** (statusCode: 400/500):

```json
{
  "statusCode": 500,
  "body": {
    "error": "ProcessingError",
    "message": "Failed to invoke Bedrock: ThrottlingException"
  }
}
```

---

## Desenvolvimento Local

### 1. Instalar Dependências

```bash
cd src/processor
pip install -r requirements.txt
```

### 2. Configurar Ambiente

```bash
export TRACKING_TABLE=ai-techne-academy-tracking-dev
export OUTPUT_BUCKET=ai-techne-academy-output-dev
export AWS_REGION=us-east-1
export AWS_PROFILE=your-profile
```

### 3. Executar Localmente

```bash
python main.py '{
  "execution_id": "test-123",
  "video_s3_uri": "s3://bucket/video.mp4",
  "transcription_s3_uri": "s3://bucket/transcription.json"
}'
```

### 4. Teste com JSON File

```bash
python main.py "$(cat test-event.json)"
```

---

## Deploy

### 🐳 Docker

O processador é containerizado usando Docker multi-stage build para otimização de tamanho e performance.

#### Dockerfile

O [`Dockerfile`](./Dockerfile) implementa:
- ✅ Multi-stage build (builder + runtime)
- ✅ Python 3.12 slim
- ✅ Otimização de camadas com cache
- ✅ Imagem final ~200-300MB

#### Build Local

Use o script automatizado:

```bash
# Build da imagem
./scripts/build-processor.sh

# Ou manualmente
cd src/processor
docker build -t ai-techne-processor:latest .
```

#### Desenvolvimento Local com Docker Compose

O [`docker-compose.yml`](./docker-compose.yml) fornece ambiente completo para desenvolvimento:

```bash
# Iniciar container em background
cd src/processor
docker-compose up -d

# Ver logs
docker-compose logs -f

# Executar comandos no container
docker-compose exec processor python -c "import boto3; print('✓ AWS SDK loaded')"

# Parar e remover
docker-compose down
```

**Configuração**:
```yaml
services:
  processor:
    build: .
    environment:
      - AWS_REGION=us-east-1
      - TRACKING_TABLE=ai-techne-academy-tracking-dev
      - OUTPUT_BUCKET=ai-techne-academy-output-dev-<account-id>
    volumes:
      - ~/.aws:/root/.aws:ro  # AWS credentials
      - ./:/app               # Hot reload
    resources:
      limits:
        cpus: '2.0'
        memory: 8G
```

#### Push para ECR

**Pré-requisito**: Repositório ECR criado via SAM template

```bash
# Deploy da stack SAM (cria ECR repository)
cd infrastructure
sam deploy --guided

# Push da imagem usando script automatizado
./scripts/push-processor.sh
```

O script [`push-processor.sh`](../../scripts/push-processor.sh) automatiza:
1. ✅ Login no ECR
2. ✅ Tag da imagem (latest + timestamp)
3. ✅ Push para ECR
4. ✅ Verificações de segurança

**URI da Imagem**:
```
<account-id>.dkr.ecr.us-east-1.amazonaws.com/ai-techne-academy/processor:latest
```

#### Teste do Container

```bash
# Teste de dependências
docker run --rm ai-techne-processor:latest \
  python -c "import boto3, langchain, docx; print('✓ All dependencies loaded')"

# Teste com event mock (com AWS credentials)
docker run --rm \
  -v ~/.aws:/root/.aws:ro \
  -e AWS_REGION=us-east-1 \
  -e TRACKING_TABLE=test-table \
  -e OUTPUT_BUCKET=test-bucket \
  ai-techne-processor:latest \
  python main.py '{"execution_id":"test-123","video_s3_uri":"s3://bucket/video.mp4","transcription_s3_uri":"s3://bucket/transcript.json"}'
```

### 📦 ECR Repository

O repositório ECR é gerenciado via SAM template ([`template.yaml`](../../infrastructure/template.yaml)):

```yaml
ProcessorRepository:
  Type: AWS::ECR::Repository
  Properties:
    RepositoryName: ai-techne-academy/processor
    ImageScanningConfiguration:
      ScanOnPush: true
    LifecyclePolicy:
      # Mantém últimas 5 imagens
      # Expira untagged após 7 dias
```

**Lifecycle Policy**:
- Mantém últimas 5 imagens tagged
- Remove imagens untagged após 7 dias
- Scan automático de vulnerabilidades

### 🚀 ECS Task Definition

Para criar ECS Task Definition usando a imagem:

```json
{
  "family": "ai-techne-processor",
  "taskRoleArn": "arn:aws:iam::<account>:role/ai-techne-academy-ecs-task-dev",
  "executionRoleArn": "arn:aws:iam::<account>:role/ai-techne-academy-ecs-execution-dev",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "2048",
  "memory": "8192",
  "containerDefinitions": [{
    "name": "processor",
    "image": "<account>.dkr.ecr.us-east-1.amazonaws.com/ai-techne-academy/processor:latest",
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "/ecs/ai-techne-academy-processor-dev",
        "awslogs-region": "us-east-1",
        "awslogs-stream-prefix": "ecs"
      }
    },
    "environment": [
      {"name": "TRACKING_TABLE", "value": "ai-techne-academy-tracking-dev"},
      {"name": "OUTPUT_BUCKET", "value": "ai-techne-academy-output-dev-<account>"},
      {"name": "AWS_REGION", "value": "us-east-1"},
      {"name": "LOG_LEVEL", "value": "INFO"}
    ]
  }]
}
```

---

## Monitoramento

### CloudWatch Logs

Logs são enviados para `/ecs/ai-techne-academy-processor-dev`

**Exemplo de Log**:

```
2024-12-11 14:00:00 - main - INFO - Starting document generation for execution abc-123
2024-12-11 14:00:01 - transcription_parser - INFO - Parsing AWS Transcribe JSON output
2024-12-11 14:00:02 - transcription_parser - INFO - Parsed: 150000 chars, 1200 segments, 3 speakers
2024-12-11 14:00:02 - transcription_parser - INFO - Chunking transcription: 180000 tokens
2024-12-11 14:00:02 - transcription_parser - INFO - Creating 2 chunks (~90000 tokens each)
2024-12-11 14:01:15 - llm_client - INFO - Bedrock response: 2500 chars, 8000 tokens, $0.135
2024-12-11 14:03:05 - document_generator - INFO - Stage 5 complete: 28000 tokens, 35000 chars
2024-12-11 14:03:10 - main - INFO - Document generation complete: 185.3s, $0.57, 35000 chars
```

### Métricas

- **Tokens processados**: Total input + output
- **Custo por execução**: USD
- **Duração**: Segundos
- **Chunks processados**: Número de chunks
- **Taxa de sucesso**: % de execuções bem-sucedidas

---

## Troubleshooting

### Erro: "ThrottlingException"

**Causa**: Rate limit do Bedrock excedido (10 req/min ou 100K tokens/min)

**Solução**:
- Rate limiter já implementado
- Se persistir, solicitar aumento de quota AWS
- Reduzir `MAX_TOKENS_PER_CHUNK`

### Erro: "OutOfMemoryError"

**Causa**: Transcrição muito grande para memória disponível

**Solução**:
- Aumentar memória do ECS task (de 8GB para 16GB)
- Reduzir `MAX_TOKENS_PER_CHUNK` para mais chunks menores

### Erro: "DynamoDB UpdateItem failed"

**Causa**: Permissões insuficientes ou table não existe

**Solução**:
- Verificar IAM role do ECS task
- Confirmar nome da tabela em `TRACKING_TABLE`
- Verificar região AWS

### Documento Gerado Incompleto

**Causa**: `max_tokens` insuficiente na Stage 5

**Solução**:
- Stage 5 usa `max_tokens=8192` (já aumentado)
- Se necessário, editar `document_generator.py` linha ~600

---

## Custos

### Estimativa por Execução

**Vídeo 3 horas** (~270K palavras → ~360K tokens):

| Componente | Custo |
|------------|-------|
| Input tokens (~150K) | $0.45 |
| Output tokens (~10K) | $0.15 |
| **Total Bedrock** | **~$0.60** |
| S3 + DynamoDB | < $0.01 |
| ECS Fargate (3min) | $0.01 |
| **Total** | **~$0.62** |

### Otimização

- ✅ Chunking inteligente reduz tokens processados
- ✅ Rate limiting evita custos de retry
- ✅ Cache de resultados (se implementado)

---

## Próximos Passos

- [ ] Implementar testes unitários
- [ ] Adicionar cache de resultados intermediários
- [ ] Melhorar conversão Markdown → DOCX (formatação avançada)
- [ ] Suporte a templates DOCX customizados
- [ ] Métricas CloudWatch customizadas
- [ ] Streaming de progresso via WebSocket

---

## Links Relacionados

- [Design Técnico Completo](../../docs/PROCESSOR_DESIGN.md)
- [Especificação do Projeto](../../docs/SPECIFICATION.md)
- [Lambda Functions](../functions/)
- [Infraestrutura SAM](../../infrastructure/)

---

**Versão**: 1.0.0  
**Última Atualização**: 2024-12-11  
**Autor**: AI Techne Academy Team