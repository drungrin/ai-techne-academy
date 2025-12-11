# Lambda Finalizer Function

## Descrição

Função Lambda que finaliza o pipeline de processamento de vídeos, atualizando status final, enviando notificações e registrando métricas.

## Responsabilidades

1. **Receber Resultados**: Recebe resultados completos do Step Functions
2. **Determinar Status Final**: Analisa resultados e determina status (COMPLETED, FAILED, PARTIAL_SUCCESS)
3. **Atualizar DynamoDB**: Atualiza registro de tracking com retry exponential backoff
4. **Enviar Notificação SNS**: Publica notificação detalhada com links de download
5. **Registrar Métricas**: Grava métricas customizadas no CloudWatch
6. **Calcular Custos**: Estima custo total do processamento
7. **Graceful Degradation**: Continua operação mesmo com falhas não-críticas

## Variáveis de Ambiente

| Variável | Descrição | Obrigatório | Default |
|----------|-----------|-------------|---------|
| `TRACKING_TABLE` | Nome da tabela DynamoDB de tracking | Sim | - |
| `NOTIFICATION_TOPIC_ARN` | ARN do tópico SNS para notificações | Sim | - |
| `OUTPUT_BUCKET` | Bucket S3 para documentos gerados | Sim | - |
| `ENVIRONMENT` | Ambiente (dev/staging/prod) | Sim | - |
| `LOG_LEVEL` | Nível de log (INFO/DEBUG/WARNING) | Não | `INFO` |
| `MAX_RETRY_ATTEMPTS` | Máximo de tentativas de retry DynamoDB | Não | `3` |
| `RETRY_DELAY_BASE` | Delay base para backoff (segundos) | Não | `1` |

## Evento de Entrada

A função aceita 3 tipos de eventos do Step Functions:

### 1. Success Event (COMPLETED)
```json
{
  "execution_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "COMPLETED",
  "video_key": "videos/meeting.mp4",
  "bucket": "input-bucket",
  "processing_results": {
    "transcription": {
      "status": "COMPLETED",
      "duration_seconds": 7200,
      "speakers_detected": 3,
      "transcript_uri": "s3://transcripts/550e8400/transcript.json"
    },
    "llm_processing": {
      "status": "COMPLETED",
      "documents_generated": ["training", "troubleshooting"],
      "output_uri": "s3://output/550e8400/documents.zip",
      "document_size_bytes": 2457600,
      "tokens_used": 45000,
      "processing_time_seconds": 180
    }
  },
  "timestamps": {
    "started_at": "2024-12-11T10:00:00Z",
    "completed_at": "2024-12-11T12:03:00Z"
  },
  "metadata": {
    "filename": "meeting.mp4",
    "size_mb": 1500.0
  }
}
```

### 2. Failure Event (FAILED)
```json
{
  "execution_id": "550e8400-e29b-41d4-a716-446655440001",
  "status": "FAILED",
  "video_key": "videos/meeting2.mp4",
  "error": {
    "stage": "llm_processing",
    "error_code": "BedrockQuotaExceeded",
    "error_message": "Rate limit exceeded",
    "timestamp": "2024-12-11T11:30:00Z"
  },
  "processing_results": {
    "transcription": {
      "status": "COMPLETED",
      "transcript_uri": "s3://transcripts/transcript.json"
    },
    "llm_processing": {
      "status": "FAILED"
    }
  },
  "timestamps": {
    "started_at": "2024-12-11T10:00:00Z",
    "failed_at": "2024-12-11T11:30:00Z"
  }
}
```

### 3. Partial Success Event (PARTIAL_SUCCESS)
```json
{
  "execution_id": "550e8400-e29b-41d4-a716-446655440002",
  "status": "PARTIAL_SUCCESS",
  "processing_results": {
    "transcription": {
      "status": "COMPLETED",
      "speakers_detected": 2
    },
    "llm_processing": {
      "status": "PARTIAL",
      "documents_generated": ["training"],
      "failed_documents": ["troubleshooting"]
    }
  }
}
```

## Resposta

### Sucesso (200)
```json
{
  "statusCode": 200,
  "body": {
    "status": "success",
    "execution_id": "550e8400-...",
    "final_status": "COMPLETED",
    "notification_sent": true,
    "metrics_recorded": true,
    "tracking_updated": true,
    "summary": {
      "total_duration_seconds": 7380,
      "processing_cost_usd": 1.45,
      "documents_generated": 2,
      "output_location": "s3://output/550e8400/"
    },
    "message": "Execution finalized successfully"
  }
}
```

### Erro (500)
```json
{
  "statusCode": 500,
  "body": {
    "status": "error",
    "error": "FinalizationError",
    "message": "Failed to update tracking after retries"
  }
}
```

## Status Finais

### COMPLETED
Todos os estágios foram concluídos com sucesso:
- ✅ Transcrição completa
- ✅ Processamento LLM completo
- ✅ Todos os documentos gerados

### FAILED
Falha crítica no processamento:
- ❌ Transcrição falhou, OU
- ❌ Erro crítico em qualquer estágio

### PARTIAL_SUCCESS
Sucesso parcial no processamento:
- ✅ Transcrição completa
- ⚠️ LLM parcialmente bem-sucedido ou falhou
- ℹ️ Alguns documentos gerados, outros falharam

## Lógica de Retry

### Exponential Backoff com Jitter
```
Tentativa 1: Imediata
Tentativa 2: ~1s + jitter (0-0.3s)
Tentativa 3: ~2s + jitter (0-0.6s)
```

### Erros que NÃO fazem retry
- `ValidationException`
- `AccessDeniedException`
- `ResourceNotFoundException`

### Erros que fazem retry
- `ProvisionedThroughputExceededException`
- `ServiceUnavailable`
- `InternalServerError`

## Notificações SNS

### Estrutura da Notificação de Sucesso
```json
{
  "Subject": "✅ Video Processing Completed - meeting.mp4",
  "Message": {
    "status": "COMPLETED",
    "execution_id": "550e8400-...",
    "video": {
      "filename": "meeting.mp4",
      "duration": "2h 0m",
      "size_mb": 1500.0
    },
    "processing": {
      "started_at": "2024-12-11 10:00 UTC",
      "completed_at": "2024-12-11 12:03 UTC",
      "total_duration": "2h 3m",
      "cost_estimate_usd": 1.45
    },
    "results": {
      "transcription": {
        "status": "Completed",
        "speakers_detected": 3,
        "transcript_download": "https://s3.console.aws.amazon.com/..."
      },
      "documents": {
        "status": "Generated",
        "types": ["Training Manual", "Troubleshooting Guide"],
        "total_size_mb": 2.34,
        "download_link": "https://s3.console.aws.amazon.com/..."
      }
    }
  }
}
```

### Message Attributes
```json
{
  "execution_id": {"DataType": "String", "StringValue": "550e8400-..."},
  "status": {"DataType": "String", "StringValue": "COMPLETED"},
  "cost_usd": {"DataType": "Number", "StringValue": "1.45"},
  "environment": {"DataType": "String", "StringValue": "dev"}
}
```

## Métricas CloudWatch

### Namespace
`AITechneAcademy`

### Métricas Registradas
1. **ProcessingDuration** (Seconds)
   - Duração total do processamento
   - Dimensões: Environment, Status

2. **ProcessingSuccess** (Count)
   - Contagem de execuções bem-sucedidas
   - Dimensões: Environment

3. **ProcessingFailure** (Count)
   - Contagem de execuções falhadas
   - Dimensões: Environment

4. **PartialSuccess** (Count)
   - Contagem de sucessos parciais
   - Dimensões: Environment

5. **TokensProcessed** (Count)
   - Total de tokens processados pelo LLM
   - Dimensões: Environment

6. **DocumentSize** (Bytes)
   - Tamanho dos documentos gerados
   - Dimensões: Environment, Status

7. **ProcessingCost** (None/USD)
   - Custo estimado do processamento
   - Dimensões: Environment

8. **SpeakersDetected** (Count)
   - Número de speakers identificados
   - Dimensões: Environment

## Cálculo de Custo

### Componentes de Custo
```python
# Transcribe: $0.024 por minuto
transcribe_cost = (video_duration_seconds / 60) * 0.024

# Bedrock Claude Sonnet 4:
# - Input: $0.003 por 1K tokens (~67% do total)
# - Output: $0.015 por 1K tokens (~33% do total)
input_tokens = total_tokens * 0.67
output_tokens = total_tokens * 0.33
bedrock_cost = (input_tokens / 1000 * 0.003) + (output_tokens / 1000 * 0.015)

# S3: Negligível para armazenamento de curto prazo
s3_cost = (document_size_gb * 0.023) * (30 / 365)

# Total
total_cost = transcribe_cost + bedrock_cost + s3_cost
```

### Exemplo para Vídeo de 2h
```
Video: 2 horas (120 minutos)
Tokens: 45,000 tokens
Documento: 2.4 MB

Transcribe: 120 min × $0.024 = $2.88
Bedrock: (30,150 × $0.003 + 14,850 × $0.015) / 1000 = $0.31
S3: Negligível

Total: ~$3.19
```

## Registro DynamoDB

### Campos Atualizados
```json
{
  "execution_id": "550e8400-...",
  "status": "COMPLETED",
  "updated_at": "2024-12-11T12:03:00Z",
  "completion_time": "2024-12-11T12:03:00Z",
  "total_duration_seconds": 7380,
  "cost_estimate_usd": 1.45,
  "processing_stages": {
    "trigger": { /* ... */ },
    "transcribe_starter": { /* ... */ },
    "finalizer": {
      "status": "completed",
      "timestamp": "2024-12-11T12:03:00Z",
      "final_status": "COMPLETED",
      "retry_attempts": 1
    }
  },
  "processing_metrics": {
    "transcription_duration_seconds": 7200,
    "llm_processing_seconds": 180,
    "total_duration_seconds": 7380,
    "tokens_used": 45000,
    "document_size_bytes": 2457600,
    "speakers_detected": 3,
    "documents_generated": 2
  }
}
```

## Tratamento de Erros

### Graceful Degradation Strategy

A função prioriza operações por criticidade:

1. **CRÍTICO**: Atualização DynamoDB
   - 3 tentativas com exponential backoff
   - Logs CRITICAL se falhar após retries
   - Continua para próximas operações mesmo se falhar

2. **IMPORTANTE**: Notificação SNS
   - 1 tentativa
   - Logs ERROR se falhar
   - Não bloqueia operações seguintes

3. **OPCIONAL**: Métricas CloudWatch
   - 1 tentativa
   - Logs WARNING se falhar
   - Não bloqueia resposta final

### Exemplo de Degradação Graceful
```json
{
  "tracking_updated": false,    // Failed after retries
  "notification_sent": true,    // Succeeded
  "metrics_recorded": false     // Failed
}
```
A função ainda retorna `200 OK` mas com detalhes das falhas parciais.

## Desenvolvimento Local

### Instalar Dependências
```bash
cd src/functions/finalizer
pip install -r requirements.txt
```

### Executar Testes
```bash
cd tests/unit
pytest test_finalizer.py -v

# Com coverage
pytest test_finalizer.py --cov=../../src/functions/finalizer --cov-report=html
```

### Testar com SAM Local
```bash
# Criar evento de teste
cat > event.json << EOF
{
  "execution_id": "test-123",
  "status": "COMPLETED",
  "processing_results": {
    "transcription": {"status": "COMPLETED"},
    "llm_processing": {"status": "COMPLETED", "tokens_used": 45000}
  },
  "timestamps": {
    "started_at": "2024-12-11T10:00:00Z",
    "completed_at": "2024-12-11T12:00:00Z"
  },
  "metadata": {"filename": "test.mp4"}
}
EOF

# Invocar função localmente
sam local invoke FinalizerFunction -e event.json
```

## Monitoramento e Logs

### CloudWatch Logs
Logs são enviados para: `/aws/lambda/ai-techne-academy-{environment}`

### Estrutura de Log
```json
{
  "timestamp": "2024-12-11T12:03:00Z",
  "level": "INFO",
  "execution_id": "550e8400-...",
  "final_status": "COMPLETED",
  "action": "finalize_execution",
  "results": {
    "tracking_updated": true,
    "notification_sent": true,
    "metrics_recorded": true
  },
  "duration_ms": 1245,
  "cost_usd": 1.45
}
```

### Logs Críticos a Monitorar
- `CRITICAL: Failed to update tracking` - DynamoDB falhou após retries
- `ERROR: Failed to send SNS notification` - Notificação não enviada
- `WARNING: Failed to record CloudWatch metrics` - Métricas não gravadas

## Performance

### Métricas Esperadas
| Métrica | Target | Notas |
|---------|--------|-------|
| Cold Start | <3s | Primeira invocação |
| Warm Execution | <2s | Sem retries |
| Com Retries | <10s | Pior caso (3 retries) |
| Uso de Memória | <128MB | Típico |

### Otimizações Implementadas
1. **Connection Reuse**: Clientes boto3 reutilizados
2. **Batch Metrics**: Todas métricas enviadas em uma única chamada
3. **Structured Logging**: JSON format para parsing eficiente
4. **Minimal Dependencies**: Apenas boto3 e botocore

## Troubleshooting

### Problema: DynamoDB UpdateItem falha sempre
**Sintomas**: Logs mostram `CRITICAL: Failed to update tracking`

**Possíveis Causas**:
1. Execution ID não existe na tabela
2. IAM permissions insuficientes
3. Tabela não existe ou nome incorreto

**Solução**:
```bash
# Verificar se record existe
aws dynamodb get-item \
  --table-name ai-techne-academy-tracking-dev \
  --key '{"execution_id": {"S": "550e8400-..."}}'

# Verificar IAM permissions
aws iam get-role-policy \
  --role-name ai-techne-academy-lambda-execution-dev \
  --policy-name DynamoDBAccess
```

### Problema: SNS notificações não chegam
**Sintomas**: Logs mostram notificação enviada mas email não chega

**Possíveis Causas**:
1. Subscription não confirmada
2. Email filtrado como spam
3. Message Attributes inválidos

**Solução**:
```bash
# Verificar subscriptions
aws sns list-subscriptions-by-topic \
  --topic-arn arn:aws:sns:region:account:topic-name

# Confirmar subscription
# Checar email e clicar no link de confirmação

# Testar publicação manual
aws sns publish \
  --topic-arn arn:aws:sns:... \
  --subject "Test" \
  --message "Test message"
```

### Problema: Métricas não aparecem no CloudWatch
**Sintomas**: CloudWatch dashboard vazio

**Possíveis Causas**:
1. IAM permissions insuficientes
2. Namespace incorreto
3. Delay na propagação (até 5 minutos)

**Solução**:
```bash
# Verificar métricas recentes
aws cloudwatch list-metrics \
  --namespace AITechneAcademy

# Aguardar 5 minutos para propagação
# Verificar IAM permissions para cloudwatch:PutMetricData
```

## Limitações

- **Timeout**: 90 segundos (suficiente para retry logic)
- **Memory**: 256 MB (adequado para processamento de métricas)
- **Retry Attempts**: Máximo de 3 tentativas no DynamoDB
- **SNS Message Size**: Máximo de 256 KB

## Próximos Passos

1. ✅ Implementação básica completa
2. ✅ Testes unitários (35+ casos, >85% coverage)
3. ✅ Graceful degradation implementado
4. ⏳ Integração com Step Functions (Fase 3)
5. ⏳ Testes de integração end-to-end
6. ⏳ Alarmes CloudWatch configurados
7. ⏳ Dashboard CloudWatch personalizado

## Links Relacionados

- [Design Técnico](../../../docs/FINALIZER_DESIGN.md)
- [Especificação Técnica](../../../docs/SPECIFICATION.md)
- [Plano de Implementação](../../../docs/IMPLEMENTATION_PLAN.md)
- [Template SAM](../../../infrastructure/template.yaml)
- [Trigger Function](../trigger/README.md)
- [Transcribe Starter](../transcribe/README.md)