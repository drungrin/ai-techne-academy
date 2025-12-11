# 🧪 Guia de Teste End-to-End - AI Techne Academy

**Data**: 2024-12-11  
**Stack**: ai-techne-academy-dev  
**Status**: Pronto para teste

---

## 📋 Informações da Infraestrutura

### S3 Buckets
- **Input**: `ai-techne-academy-input-dev-435376089474`
- **Output**: `ai-techne-academy-output-dev-435376089474`
- **Transcriptions**: `ai-techne-academy-transcripts-dev-435376089474`

### Step Functions
- **State Machine**: `ai-techne-academy-workflow-dev`
- **ARN**: `arn:aws:states:us-east-1:435376089474:stateMachine:ai-techne-academy-workflow-dev`

### CloudWatch
- **Dashboard**: `ai-techne-academy-dev`
- **Log Group**: `/aws/vendedlogs/states/ai-techne-academy-dev`

---

## 🎬 PASSO 1: Preparar Vídeo de Teste

### Opção A: Usar Vídeo Existente
Se você tem um vídeo de treinamento/reunião (MP4, MOV, etc.):
```bash
# Verificar formato e tamanho
ls -lh seu-video.mp4
file seu-video.mp4
```

### Opção B: Baixar Vídeo de Teste Público
```bash
# Exemplo: Vídeo curto do YouTube (use youtube-dl ou yt-dlp)
yt-dlp -f "best[ext=mp4]" -o "test-video.mp4" "URL_DO_VIDEO"
```

### Opção C: Criar Vídeo de Teste Simples
Se não tiver vídeo, podemos fazer um teste com arquivo de áudio convertido para vídeo:
```bash
# Criar vídeo simples com ffmpeg (se disponível)
ffmpeg -f lavfi -i sine=frequency=1000:duration=60 -f lavfi -i color=c=blue:s=1280x720:d=60 test-video.mp4
```

### Requisitos do Vídeo
- ✅ Formato: MP4, MOV, AVI, MKV, WEBM, FLV, M4V
- ✅ Tamanho: < 5 GB
- ✅ Duração recomendada para primeiro teste: 1-5 minutos
- ⚠️ Para vídeos longos (>30min), considere solicitar quota Bedrock primeiro

---

## 🚀 PASSO 2: Upload no S3

```bash
# Upload do vídeo
aws s3 cp seu-video.mp4 s3://ai-techne-academy-input-dev-435376089474/test-videos/

# Verificar upload bem-sucedido
aws s3 ls s3://ai-techne-academy-input-dev-435376089474/test-videos/
```

**Nota**: O upload automaticamente dispara o EventBridge rule que inicia a State Machine!

---

## 📊 PASSO 3: Monitorar Execução

### 3.1 Listar Execuções da State Machine
```bash
# Listar últimas execuções
aws stepfunctions list-executions \
  --state-machine-arn arn:aws:states:us-east-1:435376089474:stateMachine:ai-techne-academy-workflow-dev \
  --max-results 5 \
  --query 'executions[*].{Name:name,Status:status,StartDate:startDate}' \
  --output table
```

### 3.2 Obter Detalhes de Execução Específica
```bash
# Substitua EXECUTION_ARN pela ARN da execução
aws stepfunctions describe-execution \
  --execution-arn EXECUTION_ARN \
  --query '{Status:status,StartDate:startDate,StopDate:stopDate,Output:output}' \
  --output json
```

### 3.3 Monitorar via Console Web
Abra no navegador:
```
https://console.aws.amazon.com/states/home?region=us-east-1#/statemachines/view/arn:aws:states:us-east-1:435376089474:stateMachine:ai-techne-academy-workflow-dev
```

---

## 📈 PASSO 4: Verificar CloudWatch Dashboard

### Via Console Web
```
https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=ai-techne-academy-dev
```

### Via CLI - Verificar Métricas
```bash
# Execuções da State Machine (últimos 5 minutos)
aws cloudwatch get-metric-statistics \
  --namespace AWS/States \
  --metric-name ExecutionsFailed \
  --dimensions Name=StateMachineArn,Value=arn:aws:states:us-east-1:435376089474:stateMachine:ai-techne-academy-workflow-dev \
  --start-time $(date -u -d '5 minutes ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum
```

---

## ✅ PASSO 5: Validar Documento Gerado

### 5.1 Listar Arquivos no Output Bucket
```bash
aws s3 ls s3://ai-techne-academy-output-dev-435376089474/ --recursive
```

### 5.2 Baixar Documentos Gerados
```bash
# Markdown
aws s3 cp s3://ai-techne-academy-output-dev-435376089474/EXECUTION_ID/document.md ./output/

# DOCX
aws s3 cp s3://ai-techne-academy-output-dev-435376089474/EXECUTION_ID/document.docx ./output/
```

### 5.3 Validar Conteúdo
```bash
# Ver primeiras linhas do Markdown
head -n 50 ./output/document.md

# Verificar tamanho dos arquivos
ls -lh ./output/
```

---

## 📧 PASSO 6: Conferir Notificação SNS

As notificações são enviadas para: **devops@techne.com.br**

### Verificar se Subscrição Está Confirmada
```bash
aws sns list-subscriptions-by-topic \
  --topic-arn $(aws cloudformation describe-stacks \
    --stack-name ai-techne-academy-dev \
    --query 'Stacks[0].Outputs[?OutputKey==`NotificationTopicArn`].OutputValue' \
    --output text) \
  --query 'Subscriptions[*].{Protocol:Protocol,Endpoint:Endpoint,Status:SubscriptionArn}' \
  --output table
```

**Nota**: Se status for "PendingConfirmation", confirme via email antes do teste.

---

## 📝 PASSO 7: Verificar Logs CloudWatch

### 7.1 Logs da State Machine
```bash
aws logs tail /aws/vendedlogs/states/ai-techne-academy-dev --follow
```

### 7.2 Logs das Lambda Functions
```bash
# Trigger Function
aws logs tail /aws/lambda/ai-techne-academy-dev --follow --filter-pattern "TriggerFunction"

# Transcribe Starter
aws logs tail /aws/lambda/ai-techne-academy-dev --follow --filter-pattern "TranscribeStarterFunction"

# Finalizer
aws logs tail /aws/lambda/ai-techne-academy-dev --follow --filter-pattern "FinalizerFunction"
```

### 7.3 Logs do ECS Processor
```bash
aws logs tail /ecs/ai-techne-academy-processor-dev --follow
```

---

## 📊 PASSO 8: Documentar Resultado

Após o teste, documente os seguintes dados:

### Métricas de Execução
- [ ] **Duração Total**: _____ minutos
- [ ] **Status Final**: SUCCESS / FAILED / PARTIAL_SUCCESS
- [ ] **Duração da Transcrição**: _____ minutos
- [ ] **Duração do Processamento LLM**: _____ minutos

### Qualidade
- [ ] **Transcrição**: Precisa? Speakers identificados?
- [ ] **Documento Markdown**: Bem estruturado? Tom profissional?
- [ ] **Documento DOCX**: Formatação correta?

### Custos Estimados
```bash
# Calcular com base nos logs do Finalizer
# Procurar por: "ProcessingCost" no CloudWatch
```

### Issues Encontradas
- [ ] Listar quaisquer erros ou problemas
- [ ] Verificar alarmes disparados

---

## 🚨 Troubleshooting

### Execução não Iniciou
```bash
# Verificar EventBridge Rule
aws events describe-rule --name ai-techne-academy-video-upload-dev

# Verificar se Rule está habilitada
aws events list-rule-names-by-target \
  --target-arn arn:aws:states:us-east-1:435376089474:stateMachine:ai-techne-academy-workflow-dev
```

### Transcrição Falhou
```bash
# Listar jobs Transcribe
aws transcribe list-transcription-jobs --max-results 5

# Ver detalhes de job específico
aws transcribe get-transcription-job --transcription-job-name JOB_NAME
```

### ECS Task Falhou
```bash
# Listar tasks do cluster
aws ecs list-tasks --cluster ai-techne-academy-dev

# Descrever task específica
aws ecs describe-tasks --cluster ai-techne-academy-dev --tasks TASK_ARN
```

### Circuit Breaker Abriu (Quota Bedrock)
Se ver erro "Circuit breaker is OPEN":
1. Aguardar 5 minutos (auto-recovery)
2. Ou solicitar aumento de quota
3. Verificar estado:
```bash
# Procurar em logs do processor
aws logs filter-log-events \
  --log-group-name /ecs/ai-techne-academy-processor-dev \
  --filter-pattern "circuit_breaker"
```

---

## 📚 Links Úteis

- **CloudWatch Dashboard**: https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=ai-techne-academy-dev
- **Step Functions Console**: https://console.aws.amazon.com/states/home?region=us-east-1
- **S3 Buckets**: https://s3.console.aws.amazon.com/s3/buckets?region=us-east-1
- **CloudWatch Logs**: https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups

---

## ✅ Checklist de Sucesso

- [ ] Vídeo enviado para S3
- [ ] State Machine iniciou automaticamente
- [ ] Transcrição completada com sucesso
- [ ] ECS task executou sem erros
- [ ] Documentos gerados (MD + DOCX)
- [ ] Notificação SNS recebida
- [ ] Métricas visíveis no Dashboard
- [ ] Alarmes permanecem OK (não dispararam)
- [ ] Custo está dentro do esperado (~$1.45 por 3h de vídeo)

---

**Pronto para começar? Execute o PASSO 1!** 🚀