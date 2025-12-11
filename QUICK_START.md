# AI Techne Academy - Quick Start Guide

Este guia fornece instruções rápidas para configurar e fazer o deploy do sistema.

---

## 📋 Pré-requisitos

- AWS CLI configurado com credenciais válidas
- AWS SAM CLI instalado
- Docker Desktop rodando
- Conta AWS com permissões adequadas

---

## 🚀 Deploy Rápido

### 1. Configurar SubnetId

Execute o script helper para detectar automaticamente uma subnet pública:

```bash
./scripts/setup-subnet.sh
```

Ou configure manualmente editando `infrastructure/parameters/dev.json`:
```json
{
  "ParameterKey": "SubnetId",
  "ParameterValue": "subnet-xxxxxxxx"
}
```

### 2. Build com Containers

⚠️ **IMPORTANTE**: Sempre use `--use-container` para evitar problemas com Python/pip local:

```bash
sam build --template infrastructure/template.yaml --use-container
```

### 3. Deploy

```bash
sam deploy \
  --template-file .aws-sam/build/template.yaml \
  --stack-name ai-techne-academy-dev \
  --parameter-overrides file://infrastructure/parameters/dev.json \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --region us-east-1
```

Ou use o modo guiado na primeira vez:

```bash
sam deploy --guided
```

### 4. Verificar Deploy

Após o deploy, verifique os recursos criados:

```bash
# Stack status
aws cloudformation describe-stacks --stack-name ai-techne-academy-dev

# Buckets S3
aws s3 ls | grep ai-techne-academy

# Dashboard CloudWatch
# https://console.aws.amazon.com/cloudwatch/dashboards
```

---

## 🧪 Teste End-to-End

### 1. Upload de Vídeo

```bash
# Obter nome do bucket de input
INPUT_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name ai-techne-academy-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`InputBucketName`].OutputValue' \
  --output text)

# Upload de vídeo de teste
aws s3 cp seu-video.mp4 s3://$INPUT_BUCKET/
```

### 2. Monitorar Execução

```bash
# Obter ARN da State Machine
STATE_MACHINE_ARN=$(aws cloudformation describe-stacks \
  --stack-name ai-techne-academy-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`ProcessingStateMachineArn`].OutputValue' \
  --output text)

# Listar execuções
aws stepfunctions list-executions \
  --state-machine-arn $STATE_MACHINE_ARN \
  --max-results 5
```

Ou acesse o console:
- Step Functions: https://console.aws.amazon.com/states/home
- CloudWatch Dashboard: https://console.aws.amazon.com/cloudwatch/dashboards

### 3. Verificar Resultado

```bash
# Obter nome do bucket de output
OUTPUT_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name ai-techne-academy-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`OutputBucketName`].OutputValue' \
  --output text)

# Listar documentos gerados
aws s3 ls s3://$OUTPUT_BUCKET/ --recursive
```

---

## 🔧 Comandos Úteis

### Logs

```bash
# Logs do Step Functions
aws logs tail /aws/vendedlogs/states/ai-techne-academy-dev --follow

# Logs das Lambdas
aws logs tail /aws/lambda/ai-techne-academy-dev --follow

# Logs do ECS Processor
aws logs tail /ecs/ai-techne-academy-processor-dev --follow
```

### Métricas

```bash
# Ver métricas customizadas
aws cloudwatch list-metrics --namespace AITechneAcademy

# Ver alarmes
aws cloudwatch describe-alarms --state-value ALARM
```

### Limpeza

Para remover todos os recursos:

```bash
# Esvaziar buckets S3 primeiro
aws s3 rm s3://$INPUT_BUCKET --recursive
aws s3 rm s3://$OUTPUT_BUCKET --recursive
aws s3 rm s3://$TRANSCRIPTS_BUCKET --recursive

# Deletar stack
aws cloudformation delete-stack --stack-name ai-techne-academy-dev
```

---

## ⚠️ Troubleshooting

### Erro: Subnet inválida

**Problema**: ECS Task não consegue iniciar por falta de subnet.

**Solução**:
```bash
./scripts/setup-subnet.sh
sam build --use-container
sam deploy
```

### Erro: Bedrock quota exceeded

**Problema**: Quota do Bedrock foi atingida.

**Solução**:
1. Acesse: https://console.aws.amazon.com/servicequotas/
2. Service: Amazon Bedrock
3. Solicite aumento de quota:
   - Requests: 50/min → 100/min
   - Tokens: 500K/min → 1M/min

O circuit breaker irá proteger o sistema enquanto isso.

### Erro: Build failed - Python/pip

**Problema**: SAM não encontra Python/pip local.

**Solução**: SEMPRE use `--use-container`:
```bash
sam build --template infrastructure/template.yaml --use-container
```

---

## 📚 Documentação Adicional

- [Especificação Técnica](docs/SPECIFICATION.md)
- [Guia de Deploy Detalhado](docs/DEPLOYMENT_GUIDE.md)
- [Estratégia de Observabilidade](docs/OBSERVABILITY_STRATEGY.md)
- [Revisão Arquitetural](docs/ARCHITECTURE_REVIEW.md)

---

## 💰 Custos Estimados

- **Desenvolvimento**: ~$2-3/mês (infraestrutura base)
- **Por Vídeo (3h)**: ~$1.45
  - Transcribe: ~$0.83
  - Bedrock: ~$0.62
  - ECS + outros: ~$0.00 (custo marginal)

---

**Última Atualização**: 2024-12-11  
**Versão**: 1.0.0