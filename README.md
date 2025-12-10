# AI Techne Academy - Sistema de Geração de Documentos de Treinamento

Sistema automatizado para processar vídeos de até 3 horas e gerar documentos completos de Treinamento e Troubleshooting usando AWS e LLM.

## 🎯 Visão Geral

Este projeto utiliza AWS Transcribe para transcrever vídeos e AWS Bedrock (Claude 3.5 Sonnet) para gerar documentos estruturados de treinamento. O processamento é orquestrado via Step Functions e executado em containers ECS Fargate.

## 📋 Pré-requisitos

- **AWS Account** com permissões para:
  - S3, Lambda, ECS, Step Functions, Transcribe, Bedrock
  - IAM role creation
- **Docker** (versão 20.10+)
- **AWS SAM CLI** (versão 1.100+)
- **Python** 3.12+
- **AWS CLI** configurado

## 🚀 Quick Start

### 1. Clone o Repositório

```bash
git clone https://github.com/your-org/ai-techne-academy.git
cd ai-techne-academy
```

### 2. Configure o Ambiente Local

```bash
# Instalar dependências Python
pip install -r src/processor/requirements.txt

# Configurar LocalStack para desenvolvimento
./scripts/local-setup.sh
```

### 3. Build e Deploy

```bash
# Build SAM
sam build

# Deploy em desenvolvimento
sam deploy --guided
```

### 4. Upload de Vídeo para Teste

```bash
# Upload para S3
aws s3 cp seu-video.mp4 s3://video-processing-input-dev/

# Monitorar processamento
aws stepfunctions list-executions \
  --state-machine-arn <YOUR_STATE_MACHINE_ARN>
```

## 📁 Estrutura do Projeto

```
ai-techne-academy/
├── README.md                     # Este arquivo
├── SPECIFICATION.md              # Especificação técnica completa
├── docker/
│   ├── Dockerfile               # Container do processador
│   └── docker-compose.yml       # Ambiente local
├── src/
│   ├── functions/               # Lambda Functions
│   │   ├── trigger/
│   │   ├── transcribe/
│   │   └── finalizer/
│   └── processor/               # ECS Task
│       ├── main.py
│       ├── llm_client.py
│       ├── document_generator.py
│       └── transcription_parser.py
├── infrastructure/
│   ├── template.yaml            # SAM template
│   └── statemachine/
│       └── video_processor.asl.json
├── tests/
│   ├── unit/
│   └── integration/
└── scripts/
    ├── local-setup.sh
    ├── local-test.sh
    └── deploy.sh
```

## 🛠️ Desenvolvimento Local

### Usando LocalStack

```bash
# Iniciar ambiente local
cd docker
docker-compose up -d

# Verificar status
docker-compose ps

# Visualizar logs
docker-compose logs -f processor
```

### Teste Manual Local

```bash
# Executar teste com vídeo local
./scripts/local-test.sh samples/meeting.mp4

# Verificar saída
aws --endpoint-url=http://localhost:4566 s3 ls \
  s3://video-processing-output-dev/
```

### Debug com VS Code

1. Abra o projeto no VS Code
2. Selecione a configuração "Python: Processor Local"
3. Pressione F5 para iniciar debug
4. Defina breakpoints conforme necessário

## 📊 Monitoramento

### CloudWatch Dashboard

Acesse o dashboard principal:
```bash
aws cloudwatch get-dashboard \
  --dashboard-name ai-techne-academy-overview
```

### Logs

```bash
# Logs do ECS Task
aws logs tail /ecs/ai-techne-academy-dev --follow

# Logs da State Machine
aws logs tail /aws/vendedlogs/states/ai-techne-academy-dev --follow

# Logs de Lambda
aws logs tail /aws/lambda/ai-techne-academy-transcribe-starter-dev --follow
```

### Métricas

```bash
# Ver execuções da State Machine
aws cloudwatch get-metric-statistics \
  --namespace AWS/States \
  --metric-name ExecutionsSucceeded \
  --dimensions Name=StateMachineArn,Value=<YOUR_ARN> \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum
```

## 🧪 Testes

### Testes Unitários

```bash
# Executar todos os testes
pytest tests/unit/ -v

# Com coverage
pytest tests/unit/ --cov=src --cov-report=html
```

### Testes de Integração

```bash
# Executar testes de integração
pytest tests/integration/ -v

# Teste específico
pytest tests/integration/test_workflow.py::test_full_pipeline -v
```

## 🚢 Deploy em Produção

### Deploy Automatizado (CI/CD)

Push para a branch `main` dispara automaticamente o pipeline via GitHub Actions.

### Deploy Manual

```bash
# Build da imagem Docker
docker build -t ai-techne-academy:v1.0.0 -f docker/Dockerfile .

# Push para ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  123456789.dkr.ecr.us-east-1.amazonaws.com

docker tag ai-techne-academy:v1.0.0 \
  123456789.dkr.ecr.us-east-1.amazonaws.com/ai-techne-academy:v1.0.0

docker push 123456789.dkr.ecr.us-east-1.amazonaws.com/ai-techne-academy:v1.0.0

# Deploy com SAM
sam deploy \
  --stack-name ai-techne-academy-prod \
  --parameter-overrides \
    Environment=prod \
    ProcessorImage=123456789.dkr.ecr.us-east-1.amazonaws.com/ai-techne-academy:v1.0.0 \
  --capabilities CAPABILITY_IAM \
  --region us-east-1 \
  --confirm-changeset
```

## 💰 Custos Estimados

| Cenário | Vídeos/Mês | Custo Estimado |
|---------|------------|----------------|
| Baixo | 10 | ~$15/mês |
| Médio | 50 | ~$70/mês |
| Alto | 200 | ~$280/mês |

**Custo por execução (vídeo de 3h)**: ~$1.45

Veja [`SPECIFICATION.md`](./SPECIFICATION.md) para breakdown detalhado.

## 🔒 Segurança

### Melhores Práticas Implementadas

- ✅ Princípio do menor privilégio em IAM roles
- ✅ Criptografia em repouso (S3, DynamoDB)
- ✅ Criptografia em trânsito (TLS 1.2+)
- ✅ VPC privada para ECS tasks
- ✅ CloudTrail habilitado para auditoria
- ✅ Sem credenciais hardcoded

### Rotação de Segredos

```bash
# Atualizar secrets no AWS Secrets Manager
aws secretsmanager update-secret \
  --secret-id ai-techne-academy/api-keys \
  --secret-string '{"bedrock_key":"new_key"}'
```

## 🐛 Troubleshooting

### Problema: Transcription Job Failed

**Sintomas**: State Machine falha na etapa de transcrição

**Solução**:
1. Verificar formato do vídeo (deve ser MP4, MP3, WAV, FLAC)
2. Verificar tamanho do arquivo (<5 GB)
3. Verificar permissões do bucket S3

```bash
# Verificar job de transcrição
aws transcribe get-transcription-job \
  --transcription-job-name <JOB_NAME>
```

### Problema: ECS Task Out of Memory

**Sintomas**: Task termina com exit code 137

**Solução**:
1. Aumentar memória no Task Definition (atual: 8 GB)
2. Implementar chunking para transcrições muito grandes
3. Verificar memory leaks no código

### Problema: Bedrock Rate Limit

**Sintomas**: `ThrottlingException` nos logs

**Solução**:
1. Implementar backoff exponencial (já implementado)
2. Solicitar aumento de quota na AWS
3. Considerar Provisioned Throughput para alto volume

### Verificar Status do Sistema

```bash
# Health check completo
./scripts/health-check.sh

# Verificar componentes AWS
aws stepfunctions list-state-machines
aws ecs list-clusters
aws s3 ls | grep video-processing
```

## 📚 Documentação Adicional

- [Especificação Técnica Completa](./SPECIFICATION.md)
- [Guia de Contribuição](./CONTRIBUTING.md)
- [Changelog](./CHANGELOG.md)
- [AWS Transcribe Docs](https://docs.aws.amazon.com/transcribe/)
- [AWS Bedrock Docs](https://docs.aws.amazon.com/bedrock/)

## 🤝 Contribuindo

1. Fork o projeto
2. Crie uma branch para sua feature (`git checkout -b feature/AmazingFeature`)
3. Commit suas mudanças (`git commit -m 'Add some AmazingFeature'`)
4. Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request

## 📝 Licença

Este projeto está licenciado sob a MIT License - veja o arquivo [LICENSE](LICENSE) para detalhes.

## 👥 Autores

- **Seu Nome** - *Trabalho Inicial* - [@seu-username](https://github.com/seu-username)

## 🙏 Agradecimentos

- AWS pela infraestrutura e serviços
- Anthropic pelo Claude
- Comunidade open source

## 📞 Suporte

- **Email**: devops@techne.com.br
- **Slack**: #ai-techne-academy
- **Issues**: [GitHub Issues](https://github.com/your-org/ai-techne-academy/issues)

## 🗓️ Roadmap

### Q1 2025
- [ ] Interface web para upload/gerenciamento
- [ ] Suporte para múltiplos idiomas
- [ ] API REST para integração

### Q2 2025
- [ ] Processamento em tempo real (streaming)
- [ ] Templates customizáveis de documentos
- [ ] Análise de sentimento

### Q3 2025
- [ ] Integração com ferramentas de ticketing (Jira, ServiceNow)
- [ ] Suporte para múltiplos modelos LLM
- [ ] Dashboard analytics

---

**Última Atualização**: 2024-12-10  
**Versão**: 1.0.0  
**Status**: 🟢 Ativo