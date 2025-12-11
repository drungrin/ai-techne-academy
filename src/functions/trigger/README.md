# Lambda Trigger Function

## Descrição

Função Lambda que responde a eventos de upload de vídeos no S3 e inicia o workflow de processamento.

## Responsabilidades

1. **Receber Eventos S3**: Escuta eventos de criação de objetos no bucket de input
2. **Validar Arquivos**: 
   - Verifica formato do arquivo (mp4, mov, avi, mkv, webm, flv, m4v)
   - Valida tamanho (máximo 5 GB)
   - Verifica se arquivo não está vazio
3. **Extrair Metadados**: Coleta informações do vídeo (nome, tamanho, tipo, etc.)
4. **Criar Tracking Record**: Registra execução inicial no DynamoDB
5. **Iniciar Workflow**: Dispara Step Functions execution (quando configurado)

## Variáveis de Ambiente

| Variável | Descrição | Obrigatório |
|----------|-----------|-------------|
| `TRACKING_TABLE` | Nome da tabela DynamoDB de tracking | Sim |
| `STATE_MACHINE_ARN` | ARN da Step Functions state machine | Não* |
| `ENVIRONMENT` | Ambiente (dev/staging/prod) | Sim |
| `LOG_LEVEL` | Nível de log (INFO/DEBUG/WARNING) | Não |

*Nota: STATE_MACHINE_ARN será obrigatório na Fase 3 quando o workflow completo for implementado.

## Evento de Entrada

A função aceita eventos do EventBridge originados de notificações S3:

```json
{
  "detail": {
    "bucket": {
      "name": "ai-techne-academy-input-dev-123456789"
    },
    "object": {
      "key": "videos/meeting-2024-12-11.mp4"
    }
  }
}
```

## Resposta

### Sucesso (200)
```json
{
  "status": "success",
  "execution_id": "550e8400-e29b-41d4-a716-446655440000",
  "video_key": "videos/meeting-2024-12-11.mp4",
  "bucket": "ai-techne-academy-input-dev-123456789",
  "metadata": {
    "filename": "meeting-2024-12-11.mp4",
    "extension": ".mp4",
    "mime_type": "video/mp4",
    "size_bytes": 104857600,
    "size_mb": 100.0,
    "s3_uri": "s3://ai-techne-academy-input-dev-123456789/videos/meeting-2024-12-11.mp4"
  },
  "message": "Video processing initiated successfully"
}
```

### Erro (400/500)
```json
{
  "statusCode": 400,
  "body": "Unsupported file format: .txt. Supported formats: .mp4, .mov, .avi, .mkv, .webm, .flv, .m4v"
}
```

## Formatos Suportados

- `.mp4` - video/mp4
- `.mov` - video/quicktime
- `.avi` - video/x-msvideo
- `.mkv` - video/x-matroska
- `.webm` - video/webm
- `.flv` - video/x-flv
- `.m4v` - video/x-m4v

## Limitações

- Tamanho máximo de arquivo: 5 GB
- Timeout: 60 segundos
- Memória: 256 MB

## Registro DynamoDB

A função cria o seguinte registro inicial:

```json
{
  "execution_id": "uuid",
  "video_key": "s3://bucket/key",
  "status": "STARTED",
  "created_at": "2024-12-11T10:00:00.000Z",
  "updated_at": "2024-12-11T10:00:00.000Z",
  "environment": "dev",
  "video_metadata": {
    "filename": "video.mp4",
    "size_bytes": 104857600,
    ...
  },
  "processing_stages": {
    "trigger": {
      "status": "completed",
      "timestamp": "2024-12-11T10:00:00.000Z"
    }
  }
}
```

## Desenvolvimento Local

### Instalar Dependências
```bash
cd src/functions/trigger
pip install -r requirements.txt
```

### Executar Testes
```bash
cd tests/unit
pytest test_trigger.py -v
```

### Testar com SAM Local
```bash
# Criar evento de teste
cat > event.json << EOF
{
  "Records": [{
    "s3": {
      "bucket": {"name": "test-bucket"},
      "object": {"key": "test-video.mp4"}
    }
  }]
}
EOF

# Invocar função localmente
sam local invoke TriggerFunction -e event.json
```

## Métricas e Logs

A função registra as seguintes informações:

- **INFO**: Upload recebido, validação bem-sucedida, tracking record criado
- **WARNING**: Validação falhou, configuração faltando
- **ERROR**: Falha ao acessar S3, DynamoDB, ou Step Functions

### CloudWatch Logs

Logs são enviados para: `/aws/lambda/ai-techne-academy-trigger-{environment}`

### Exemplo de Log Estruturado
```
2024-12-11 10:00:00 INFO Processing upload: s3://bucket/video.mp4
2024-12-11 10:00:01 INFO Created tracking record for execution 550e8400-...
2024-12-11 10:00:02 INFO Successfully initiated processing for execution 550e8400-...
```

## Próximos Passos

1. ✅ Implementação básica completa
2. 🔄 Integração com Step Functions (Fase 3)
3. ⏳ Adicionar validação avançada de vídeo (duração, codec)
4. ⏳ Implementar retry automático para falhas transientes
5. ⏳ Adicionar métricas customizadas no CloudWatch

## Links Relacionados

- [Especificação Técnica](../../../docs/SPECIFICATION.md)
- [Plano de Implementação](../../../docs/IMPLEMENTATION_PLAN.md)
- [Template SAM](../../../infrastructure/template.yaml)