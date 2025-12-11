# Lambda Transcribe Starter Function

## Descrição

Função Lambda que inicia jobs de transcrição no AWS Transcribe com identificação de speakers para processar áudio de vídeos.

## Responsabilidades

1. **Receber Dados de Execução**: Processa eventos do Step Functions ou invocação direta
2. **Validar Parâmetros**: 
   - Verifica formato de S3 URI
   - Valida execution_id
   - Confirma formato de mídia suportado
3. **Iniciar Job Transcribe**: 
   - Configura speaker identification (até 10 speakers)
   - Define idioma (padrão: pt-BR)
   - Especifica bucket de saída
4. **Atualizar Tracking**: Registra início do job no DynamoDB
5. **Retornar Detalhes**: Fornece informações do job para próximas etapas

## Variáveis de Ambiente

| Variável | Descrição | Obrigatório | Default |
|----------|-----------|-------------|---------|
| `TRACKING_TABLE` | Nome da tabela DynamoDB de tracking | Sim | - |
| `OUTPUT_BUCKET` | Bucket S3 para transcrições | Sim | - |
| `LANGUAGE_CODE` | Código do idioma para transcrição | Não | `pt-BR` |
| `MAX_SPEAKERS` | Número máximo de speakers | Não | `10` |
| `ENVIRONMENT` | Ambiente (dev/staging/prod) | Sim | - |
| `LOG_LEVEL` | Nível de log (INFO/DEBUG/WARNING) | Não | `INFO` |

## Evento de Entrada

A função aceita múltiplos formatos de entrada:

### Formato 1: Invocação Direta
```json
{
  "execution_id": "550e8400-e29b-41d4-a716-446655440000",
  "s3_uri": "s3://ai-techne-academy-input-dev-123456789/videos/meeting.mp4",
  "language_code": "pt-BR",
  "max_speakers": 10
}
```

### Formato 2: Step Functions (com bucket/key)
```json
{
  "execution_id": "550e8400-e29b-41d4-a716-446655440000",
  "bucket": "ai-techne-academy-input-dev-123456789",
  "video_key": "videos/meeting.mp4",
  "metadata": {
    "filename": "meeting.mp4",
    "size_mb": 1500.0
  },
  "timestamp": "2024-12-11T10:00:00.000Z"
}
```

### Formato 3: Step Functions (com metadata)
```json
{
  "execution_id": "550e8400-e29b-41d4-a716-446655440000",
  "metadata": {
    "s3_uri": "s3://bucket/videos/meeting.mp4",
    "filename": "meeting.mp4"
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
    "execution_id": "550e8400-e29b-41d4-a716-446655440000",
    "transcription_job": {
      "job_name": "transcribe-550e8400-e29b-41d4-a716-446655440000",
      "job_status": "IN_PROGRESS",
      "language_code": "pt-BR",
      "media_uri": "s3://bucket/videos/meeting.mp4",
      "output_location": "s3://transcripts-bucket/550e8400/transcript.json",
      "created_at": "2024-12-11T10:00:01.000Z"
    },
    "message": "Transcription job started successfully"
  }
}
```

### Erro (400/500)
```json
{
  "statusCode": 400,
  "body": "Invalid S3 URI: invalid-uri"
}
```

## Formatos de Mídia Suportados

| Extensão | MediaFormat | Tipo MIME |
|----------|-------------|-----------|
| `.mp4` | `mp4` | video/mp4 |
| `.mp3` | `mp3` | audio/mpeg |
| `.wav` | `wav` | audio/wav |
| `.flac` | `flac` | audio/flac |
| `.ogg` | `ogg` | audio/ogg |
| `.webm` | `webm` | video/webm |
| `.amr` | `amr` | audio/amr |
| `.m4a` | `mp4` | audio/mp4 |
| `.m4v` | `mp4` | video/x-m4v |

## Configuração AWS Transcribe

### Parâmetros do Job
```python
{
    "TranscriptionJobName": "transcribe-{execution_id}",
    "Media": {
        "MediaFileUri": "s3://bucket/video.mp4"
    },
    "MediaFormat": "mp4",
    "LanguageCode": "pt-BR",
    "OutputBucketName": "transcripts-bucket",
    "OutputKey": "{execution_id}/",
    "Settings": {
        "ShowSpeakerLabels": True,
        "MaxSpeakerLabels": 10,
        "ChannelIdentification": False
    }
}
```

### Speaker Identification
- **Habilitado**: Identifica automaticamente diferentes speakers
- **Máximo**: 10 speakers (configurável)
- **Formato**: Labels como "spk_0", "spk_1", etc.
- **Uso**: Ideal para reuniões e treinamentos com múltiplos participantes

## Registro DynamoDB

A função atualiza o registro de tracking com informações do job:

```json
{
  "execution_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "TRANSCRIBING",
  "updated_at": "2024-12-11T10:00:01.000Z",
  "processing_stages": {
    "trigger": {
      "status": "completed",
      "timestamp": "2024-12-11T10:00:00.000Z"
    },
    "transcribe_starter": {
      "status": "in_progress",
      "job_name": "transcribe-550e8400-...",
      "job_status": "IN_PROGRESS",
      "timestamp": "2024-12-11T10:00:01.000Z",
      "language_code": "pt-BR",
      "media_format": "mp4",
      "created_at": "2024-12-11T10:00:01.000Z"
    }
  }
}
```

## Tratamento de Erros

### Erros Comuns

#### 1. ConflictException
**Causa**: Job com mesmo nome já existe  
**Ação**: Recupera status do job existente  
**Retry**: Não necessário

#### 2. LimitExceededException
**Causa**: Quota do AWS Transcribe excedida  
**Ação**: Propaga erro para Step Functions  
**Retry**: Sim, com backoff exponencial

#### 3. BadRequestException
**Causa**: Parâmetros inválidos  
**Ação**: Retorna erro 400  
**Retry**: Não (erro de input)

#### 4. InvalidS3URI
**Causa**: Formato de S3 URI inválido  
**Ação**: Retorna erro 400  
**Retry**: Não (erro de input)

### Estratégia de Retry

A função é **idempotente** - pode ser executada múltiplas vezes com segurança:
- Jobs duplicados são detectados via `ConflictException`
- Status do job existente é recuperado
- DynamoDB updates são condicionais

## Desenvolvimento Local

### Instalar Dependências
```bash
cd src/functions/transcribe
pip install -r requirements.txt
```

### Executar Testes
```bash
cd tests/unit
pytest test_transcribe_starter.py -v

# Com coverage
pytest test_transcribe_starter.py -v --cov=../../src/functions/transcribe --cov-report=html
```

### Testar com SAM Local
```bash
# Criar evento de teste
cat > event.json << EOF
{
  "execution_id": "test-123",
  "s3_uri": "s3://test-bucket/video.mp4"
}
EOF

# Configurar variáveis de ambiente
export TRACKING_TABLE=test-tracking-table
export OUTPUT_BUCKET=test-output-bucket
export LANGUAGE_CODE=pt-BR
export MAX_SPEAKERS=10
export ENVIRONMENT=dev

# Invocar função localmente
sam local invoke TranscribeStarterFunction \
  -e event.json \
  --env-vars env.json
```

### Mock AWS Services
```python
# Exemplo de mock para testes
from unittest.mock import patch, Mock

@patch('app.transcribe_client')
def test_function(mock_client):
    mock_client.start_transcription_job.return_value = {
        'TranscriptionJob': {
            'TranscriptionJobName': 'test-job',
            'TranscriptionJobStatus': 'IN_PROGRESS',
            # ...
        }
    }
    # Seu teste aqui
```

## Monitoramento

### CloudWatch Logs

Logs são enviados para: `/aws/lambda/ai-techne-academy-transcribe-{environment}`

### Formato de Log Estruturado
```json
{
  "timestamp": "2024-12-11T10:00:01.000Z",
  "level": "INFO",
  "execution_id": "550e8400-...",
  "job_name": "transcribe-550e8400-...",
  "action": "start_transcription_job",
  "status": "success",
  "language_code": "pt-BR",
  "max_speakers": 10
}
```

### Métricas Customizadas

A função registra as seguintes métricas no CloudWatch:
- Número de jobs iniciados
- Número de falhas
- Duração da execução
- Erros de validação

### Alarmes Recomendados

1. **Taxa de Erro Alta**: >5% de erros em 5 minutos
2. **Quota Excedida**: Qualquer `LimitExceededException`
3. **Duração Longa**: Execução >10 segundos
4. **Falhas DynamoDB**: >3 falhas de atualização em 5 minutos

## Performance

### Métricas Esperadas
- **Cold Start**: <3 segundos
- **Warm Execution**: <500ms
- **Uso de Memória**: <128MB
- **Timeout**: 60 segundos

### Otimizações
- Reutilização de conexões boto3
- Inicialização lazy de recursos
- Logging estruturado para melhor parsing
- Validação rápida de inputs antes de chamadas AWS

## Limitações

### AWS Transcribe
- **Tamanho máximo**: 2GB por arquivo
- **Duração máxima**: 4 horas
- **Concurrent jobs**: 100 por conta (default)
- **Formatos**: Apenas formatos listados acima

### Speaker Identification
- **Máximo speakers**: 10
- **Precisão**: Varia com qualidade do áudio
- **Idiomas**: Suporte varia por idioma

## Integração com Step Functions

### Input para Próximo Step
```json
{
  "execution_id": "550e8400-...",
  "job_name": "transcribe-550e8400-...",
  "output_location": "s3://bucket/550e8400/transcript.json"
}
```

### Wait for Completion
O Step Functions deve aguardar conclusão do job:
```json
{
  "Type": "Wait",
  "Seconds": 60,
  "Next": "CheckTranscriptionStatus"
}
```

## Próximos Passos

1. ✅ Implementação básica completa
2. ✅ Testes unitários (>85% cobertura)
3. ✅ Documentação completa
4. 🔄 Integração com Step Functions (Fase 3)
5. ⏳ Adicionar custom vocabularies
6. ⏳ Implementar content redaction
7. ⏳ Suporte a múltiplos idiomas

## Troubleshooting

### Job não inicia
**Sintomas**: Função retorna erro 500  
**Possíveis Causas**:
- IAM role sem permissões corretas
- Bucket de output não existe
- Formato de mídia não suportado

**Solução**:
1. Verificar IAM role tem permissões: `transcribe:StartTranscriptionJob`
2. Confirmar bucket existe e função tem acesso `s3:PutObject`
3. Validar extensão do arquivo é suportada

### DynamoDB update falha
**Sintomas**: Warning logs sobre falha de atualização  
**Possíveis Causas**:
- Registro não existe (Trigger não executou)
- IAM role sem permissões DynamoDB

**Solução**:
1. Verificar Trigger function executou primeiro
2. Confirmar IAM role tem `dynamodb:UpdateItem`
3. Job continua mesmo com falha de tracking

### Quota exceeded
**Sintomas**: `LimitExceededException`  
**Possíveis Causas**:
- Muitos jobs concorrentes
- Limite de conta AWS atingido

**Solução**:
1. Solicitar aumento de quota via AWS Support
2. Implementar rate limiting
3. Usar filas para controlar concorrência

## Links Relacionados

- [Design Técnico](../../../docs/TRANSCRIBE_STARTER_DESIGN.md)
- [Especificação do Projeto](../../../docs/SPECIFICATION.md)
- [Plano de Implementação](../../../docs/IMPLEMENTATION_PLAN.md)
- [Template SAM](../../../infrastructure/template.yaml)
- [AWS Transcribe Documentation](https://docs.aws.amazon.com/transcribe/)

## Contribuindo

Para modificar esta função:
1. Atualizar código em [`app.py`](./app.py)
2. Adicionar/atualizar testes em [`test_transcribe_starter.py`](../../tests/unit/test_transcribe_starter.py)
3. Executar testes: `pytest -v --cov`
4. Atualizar documentação se necessário
5. Validar template SAM: `sam validate --lint`

---

**Status**: ✅ Implementado e Testado  
**Versão**: 1.0.0  
**Última Atualização**: 2024-12-11