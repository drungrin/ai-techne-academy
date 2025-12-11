# Estratégia de Observabilidade - AI Techne Academy

**Data**: 2024-12-11  
**Status**: ✅ Implementado  
**Versão**: 1.0.0

---

## 📊 VISÃO GERAL

Este documento descreve a estratégia completa de observabilidade implementada no AI Techne Academy, incluindo dashboards, alarmes, logs e tracing.

---

## 🎯 OBJETIVOS

1. **Visibilidade Completa**: Monitorar todos os componentes do sistema
2. **Detecção Proativa**: Identificar problemas antes que impactem usuários
3. **Análise de Custos**: Rastrear custos de processamento em tempo real
4. **Troubleshooting Rápido**: Facilitar diagnóstico de problemas
5. **Compliance**: Manter logs para auditoria e conformidade

---

## 📈 CLOUDWATCH DASHBOARD

### Dashboard: `ai-techne-academy-{env}`

**Localização**: CloudWatch Console → Dashboards

#### Widgets Implementados

##### 1. Step Functions Executions
**Métricas**:
- ExecutionsStarted (Sum)
- ExecutionsSucceeded (Sum)
- ExecutionsFailed (Sum)
- ExecutionsTimedOut (Sum)

**Período**: 5 minutos  
**Objetivo**: Monitorar saúde geral do workflow

##### 2. Lambda Functions
**Métricas**:
- Invocations (Sum)
- Errors (Sum)
- Throttles (Sum)

**Período**: 5 minutos  
**Objetivo**: Detectar problemas nas funções Lambda

##### 3. ECS Task Utilization
**Métricas**:
- CPUUtilization (Average)
- MemoryUtilization (Average)

**Período**: 5 minutos  
**Range**: 0-100%  
**Objetivo**: Identificar necessidade de ajuste de recursos

##### 4. Dead Letter Queue
**Métricas**:
- ApproximateNumberOfMessagesVisible (Average)

**Período**: 5 minutos  
**Alerta Visual**: Linha vermelha em 1 mensagem  
**Objetivo**: Detectar falhas permanentes

##### 5. Processing Results (Custom)
**Métricas**:
- ProcessingSuccess (Sum)
- ProcessingFailure (Sum)
- PartialSuccess (Sum)

**Período**: 5 minutos  
**Visualização**: Stacked (empilhado)  
**Objetivo**: Taxa de sucesso do processamento

---

## 🚨 CLOUDWATCH ALARMS

### 1. High Failure Rate Alarm
**Nome**: `ai-techne-academy-high-failure-rate-{env}`

- **Métrica**: ExecutionsFailed (AWS/States)
- **Threshold**: > 3 falhas em 5 minutos
- **Ação**: SNS notification
- **Severidade**: 🔴 CRÍTICA

**Quando Dispara**: Múltiplas execuções falhando rapidamente

**Ação Recomendada**:
1. Verificar logs do Step Functions
2. Identificar estado falhando
3. Analisar logs do componente específico

---

### 2. Lambda Error Alarm
**Nome**: `ai-techne-academy-lambda-errors-{env}`

- **Métrica**: Errors (AWS/Lambda)
- **Threshold**: > 5 erros em 5 minutos
- **Ação**: SNS notification
- **Severidade**: 🟠 ALTA

**Quando Dispara**: Lambdas com muitos erros

**Ação Recomendada**:
1. Verificar CloudWatch Logs Insights
2. Identificar Lambda específico
3. Analisar stack trace

---

### 3. Lambda Throttle Alarm
**Nome**: `ai-techne-academy-lambda-throttles-{env}`

- **Métrica**: Throttles (AWS/Lambda)
- **Threshold**: >= 1 throttle em 5 minutos
- **Ação**: SNS notification
- **Severidade**: 🟡 MÉDIA

**Quando Dispara**: Lambda atingindo limite de concorrência

**Ação Recomendada**:
1. Verificar concurrent executions
2. Solicitar aumento de quota se necessário
3. Otimizar código para reduzir duração

---

### 4. DLQ Messages Alarm
**Nome**: `ai-techne-academy-dlq-messages-{env}`

- **Métrica**: ApproximateNumberOfMessagesVisible (AWS/SQS)
- **Threshold**: >= 1 mensagem
- **Ação**: SNS notification
- **Severidade**: 🔴 CRÍTICA

**Quando Dispara**: Eventos falhando após todos os retries

**Ação Recomendada**:
1. Ler mensagem do DLQ
2. Identificar causa raiz
3. Corrigir problema
4. Replay manual se necessário

---

### 5. ECS Task Failure Alarm
**Nome**: `ai-techne-academy-ecs-task-failure-{env}`

- **Métrica**: ExecutionsFailed (AWS/States)
- **Threshold**: >= 1 falha
- **Ação**: SNS notification
- **Severidade**: 🔴 CRÍTICA

**Quando Dispara**: ECS task falhando

**Ação Recomendada**:
1. Verificar logs do ECS
2. Checar se é erro Bedrock (quota/throttle)
3. Validar circuit breaker está funcionando

---

### 6. High Cost Alarm
**Nome**: `ai-techne-academy-high-cost-{env}`

- **Métrica**: ProcessingCost (Custom)
- **Threshold**: > $10/hora
- **Ação**: SNS notification
- **Severidade**: 🟡 MÉDIA

**Quando Dispara**: Custos acima do esperado

**Ação Recomendada**:
1. Verificar número de execuções
2. Analisar custos por vídeo
3. Identificar anomalias (vídeos muito longos, muitos retries)

---

## 📝 CLOUDWATCH LOGS

### Log Groups Criados

#### 1. Step Functions
**Nome**: `/aws/vendedlogs/states/ai-techne-academy-{env}`

- **Retention**: 30 dias
- **Level**: ALL
- **Include Execution Data**: true

**Contém**:
- Início/fim de execuções
- Transições entre estados
- Inputs/outputs de cada estado
- Erros e exceções

**Queries Úteis**:
```
# Execuções falhadas nas últimas 24h
fields @timestamp, execution_name, error
| filter @message like /ExecutionFailed/
| sort @timestamp desc
| limit 20
```

---

#### 2. ECS Processor
**Nome**: `/ecs/ai-techne-academy-processor-{env}`

- **Retention**: 30 dias
- **Stream Prefix**: processor

**Contém**:
- Logs do processador Python
- Progresso do pipeline (6 stages)
- Chamadas LLM e respostas
- Erros e stack traces
- Circuit breaker state changes

**Queries Úteis**:
```
# Erros no processador
fields @timestamp, @message
| filter @message like /ERROR/
| sort @timestamp desc
| limit 50
```

```
# Custos por execução
fields execution_id, cost_usd
| filter @message like /Processing result/
| stats avg(cost_usd), max(cost_usd), min(cost_usd)
```

```
# Duração por stage
fields stage, duration_seconds
| filter @message like /Stage completed/
| stats avg(duration_seconds) by stage
```

---

#### 3. Lambda Functions
**Nome**: `/aws/lambda/ai-techne-academy-{env}`

- **Retention**: 30 dias

**Contém**:
- Logs de todas as 3 Lambdas
- Invocações e erros
- DynamoDB updates
- SNS publications

**Queries Úteis**:
```
# Errors por função
fields @timestamp, function_name, @message
| filter @message like /ERROR/
| stats count() by function_name
```

---

## 🔍 X-RAY TRACING

### Status
✅ **HABILITADO** em todos os componentes

### Componentes Rastreados

1. **Step Functions**: Tracing enabled
2. **Lambda Functions**: AWSXRayDaemonWriteAccess policy
3. **Service Map**: Visualização completa do fluxo

### Benefícios

- **Latência End-to-End**: Tempo total de processamento
- **Bottleneck Identification**: Identificar componente mais lento
- **Error Traces**: Stack trace completo com contexto
- **Dependency Map**: Visualizar chamadas entre serviços

### Como Acessar

1. AWS Console → X-Ray → Service Map
2. Filtrar por: `ai-techne-academy-{env}`
3. Selecionar período
4. Analisar traces

---

## 📊 MÉTRICAS CUSTOMIZADAS

### Namespace: `AITechneAcademy`

#### Métricas Publicadas (via Finalizer)

##### 1. ProcessingDuration
- **Unidade**: Seconds
- **Dimensões**: Environment, ExecutionId
- **Objetivo**: Rastrear tempo de processamento

##### 2. ProcessingSuccess
- **Unidade**: Count
- **Dimensões**: Environment
- **Objetivo**: Taxa de sucesso

##### 3. ProcessingFailure
- **Unidade**: Count
- **Dimensões**: Environment, ErrorType
- **Objetivo**: Taxa de falha por tipo

##### 4. PartialSuccess
- **Unidade**: Count
- **Dimensões**: Environment
- **Objetivo**: Processamentos parciais

##### 5. TokensProcessed
- **Unidade**: Count
- **Dimensões**: Environment
- **Objetivo**: Volume de tokens LLM

##### 6. DocumentSize
- **Unidade**: Bytes
- **Dimensões**: Environment
- **Objetivo**: Tamanho dos documentos gerados

##### 7. ProcessingCost
- **Unidade**: None (USD)
- **Dimensões**: Environment
- **Objetivo**: Custo por processamento

##### 8. SpeakersDetected
- **Unidade**: Count
- **Dimensões**: Environment
- **Objetivo**: Número de speakers identificados

---

## 🔔 NOTIFICAÇÕES SNS

### Topic: `ai-techne-academy-notifications-{env}`

#### Subscribers
- Email: `devops@techne.com.br` (configurável)

#### Tipos de Notificações

1. **Sucesso de Processamento**
   - Enviado por: Finalizer Lambda
   - Contém: Links de download, sumário, custos

2. **Falha de Processamento**
   - Enviado por: Finalizer Lambda
   - Contém: Erro detalhado, ações recomendadas

3. **Processamento Parcial**
   - Enviado por: Finalizer Lambda
   - Contém: O que funcionou, o que falhou

4. **Alarmes CloudWatch**
   - Enviado por: CloudWatch Alarms
   - Contém: Nome do alarme, threshold, valor atual

---

## 📋 RUNBOOK OPERACIONAL

### Cenário 1: Alta Taxa de Falhas

**Alarme**: HighFailureRateAlarm dispara

**Passos**:
1. Acessar CloudWatch Dashboard
2. Verificar qual componente está falhando (Lambda/ECS)
3. Consultar logs correspondentes
4. Se for Bedrock: verificar circuit breaker e quotas
5. Se for outro componente: analisar erro específico

---

### Cenário 2: Mensagens no DLQ

**Alarme**: DLQMessagesAlarm dispara

**Passos**:
1. Acessar SQS Console → DLQ
2. Ler mensagem (Receive Message)
3. Analisar erro (body da mensagem)
4. Corrigir causa raiz
5. Opcional: Replay manual via Step Functions

**Replay Manual**:
```bash
aws stepfunctions start-execution \
  --state-machine-arn <arn> \
  --input '<json-from-dlq>'
```

---

### Cenário 3: Custos Elevados

**Alarme**: HighCostAlarm dispara

**Passos**:
1. Verificar número de execuções (Dashboard)
2. Calcular custo médio por vídeo
3. Identificar outliers (vídeos muito caros)
4. Analisar:
   - Vídeos muito longos (>3h)
   - Muitos retries/reprocessamentos
   - Tokens por chamada LLM acima do esperado

---

## 🎯 KPIS E SLOs

### Service Level Objectives (SLOs)

#### Disponibilidade
- **Target**: 99.0%
- **Medição**: (Successes / Total Executions) * 100
- **Período**: Mensal

#### Latência
- **Target**: P95 < 60 minutos para vídeo de 3h
- **Medição**: ProcessingDuration metric
- **Período**: Semanal

#### Taxa de Erro
- **Target**: < 5% de falhas
- **Medição**: (Failures / Total Executions) * 100
- **Período**: Diário

#### Custo
- **Target**: $1.45 ± 20% por vídeo de 3h
- **Medição**: ProcessingCost metric
- **Período**: Por execução

---

## 🔧 TROUBLESHOOTING COM LOGS INSIGHTS

### Query 1: Top 10 Erros

```
fields @timestamp, @message
| filter @message like /ERROR/
| stats count() as error_count by @message
| sort error_count desc
| limit 10
```

### Query 2: Latência por Componente

```
fields component, duration_ms
| filter @message like /completed/
| stats avg(duration_ms), max(duration_ms), p99(duration_ms) by component
```

### Query 3: Custos por Dia

```
fields @timestamp, cost_usd
| filter @message like /Processing result/
| stats sum(cost_usd) as total_cost by datefloor(@timestamp, 1d)
| sort @timestamp desc
```

### Query 4: Taxa de Sucesso por Hora

```
fields @timestamp, status
| filter @message like /Processing result/
| stats count() as total,
        sum(case status = 'COMPLETED' then 1 else 0 end) as successes
        by bin(@timestamp, 1h)
| fields @timestamp, successes * 100 / total as success_rate
```

---

## 📊 DASHBOARD ADICIONAL (FUTURO)

### Métricas Sugeridas para v2.0

1. **Bedrock Latency**: P50, P95, P99 por chamada
2. **Transcribe Duration**: Tempo de transcrição vs duração do vídeo
3. **Chunk Size Distribution**: Distribuição de tamanhos de chunks
4. **Retry Rate**: Percentual de execuções que precisaram de retry
5. **Cost per Minute**: Custo normalizado por minuto de vídeo

---

## 🔗 LINKS RÁPIDOS

### AWS Console
- [CloudWatch Dashboard](https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=ai-techne-academy-dev)
- [CloudWatch Alarms](https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#alarmsV2:)
- [CloudWatch Logs Insights](https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:logs-insights)
- [X-Ray Service Map](https://console.aws.amazon.com/xray/home?region=us-east-1#/service-map)
- [Step Functions Executions](https://console.aws.amazon.com/states/home?region=us-east-1#/statemachines)
- [SQS DLQ](https://console.aws.amazon.com/sqs/v2/home?region=us-east-1#/queues)

### Documentação Relacionada
- [`DEPLOYMENT_GUIDE.md`](./DEPLOYMENT_GUIDE.md) - Guia de deployment
- [`ARCHITECTURE_REVIEW.md`](./ARCHITECTURE_REVIEW.md) - Revisão arquitetural
- [`CRITICAL_FIXES_IMPLEMENTED.md`](./CRITICAL_FIXES_IMPLEMENTED.md) - Fixes implementados
- [`infrastructure/statemachine/README.md`](../infrastructure/statemachine/README.md) - Step Functions docs

---

## 📝 MANUTENÇÃO

### Revisão Mensal
- [ ] Validar que alarmes estão configurados corretamente
- [ ] Revisar logs de falso positivo
- [ ] Ajustar thresholds se necessário
- [ ] Verificar se dashboards estão úteis

### Revisão Trimestral
- [ ] Analisar tendências de custo
- [ ] Revisar SLOs (ajustar se necessário)
- [ ] Atualizar runbooks baseado em incidentes
- [ ] Considerar novas métricas/alarmes

---

**Implementado por**: Kilo Code  
**Última Revisão**: 2024-12-11  
**Próxima Revisão**: 2025-01-11