# Guia de Deployment - AI Techne Academy

**Versão**: 1.0.0  
**Data**: 2024-12-11  
**Status**: Pronto para resolver bloqueios críticos

---

## 🎯 OBJETIVO

Este guia resolve os 2 bloqueios críticos identificados na revisão arquitetural e prepara o sistema para deploy em desenvolvimento.

---

## 🔴 BLOQUEIO 1: VPC/Subnet para ECS Task

### Problema
Step Functions workflow referencia `${SubnetId}` no [`workflow.asl.json:160`](infrastructure/statemachine/workflow.asl.json:160), mas template não define VPC/Subnet.

### Soluções Disponíveis

#### ✅ OPÇÃO A - Usar VPC Default da Conta AWS (RECOMENDADO para Dev)

**Vantagens**: Rápido, sem custos adicionais, suficiente para dev  
**Desvantagens**: Não é isolado

**Passos**:

1. **Identificar VPC e Subnet Default**:
```bash
# Listar VPC default
aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query "Vpcs[0].VpcId" --output text

# Listar subnets públicas
aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=<VPC_ID>" "Name=map-public-ip-on-launch,Values=true" \
  --query "Subnets[0].SubnetId" --output text
```

2. **Atualizar `infrastructure/parameters/dev.json`**:
```json
{
  "Parameters": {
    "Environment": "dev",
    "NotificationEmail": "devops@techne.com.br",
    "SubnetId": "subnet-xxxxx",  // ← Adicionar subnet ID aqui
    "ProcessorImage": "<account>.dkr.ecr.us-east-1.amazonaws.com/ai-techne-academy/processor:latest"
  }
}
```

3. **Atualizar `infrastructure/template.yaml` - Adicionar Parâmetro**:
```yaml
Parameters:
  # ... existentes ...
  
  SubnetId:
    Type: String
    Description: Subnet ID for ECS tasks (must be public with internet access)
```

**Status**: ✅ Solução mais rápida - 5 minutos

---

#### 🏗️ OPÇÃO B - Criar VPC Dedicada (RECOMENDADO para Prod)

**Vantagens**: Isolamento, controle total, segurança  
**Desvantagens**: Mais complexo, custos de NAT Gateway (~$32/mês)

**Implementação**: Adicionar ao `template.yaml`:

```yaml
# VPC e Networking Resources
ProcessingVPC:
  Type: AWS::EC2::VPC
  Properties:
    CidrBlock: 10.0.0.0/16
    EnableDnsHostnames: true
    EnableDnsSupport: true
    Tags:
      - Key: Name
        Value: !Sub ${AWS::StackName}-vpc
      - Key: Project
        Value: ai-techne-academy

InternetGateway:
  Type: AWS::EC2::InternetGateway
  Properties:
    Tags:
      - Key: Name
        Value: !Sub ${AWS::StackName}-igw

AttachGateway:
  Type: AWS::EC2::VPCGatewayAttachment
  Properties:
    VpcId: !Ref ProcessingVPC
    InternetGatewayId: !Ref InternetGateway

PublicSubnet1:
  Type: AWS::EC2::Subnet
  Properties:
    VpcId: !Ref ProcessingVPC
    CidrBlock: 10.0.1.0/24
    AvailabilityZone: !Select [0, !GetAZs '']
    MapPublicIpOnLaunch: true
    Tags:
      - Key: Name
        Value: !Sub ${AWS::StackName}-public-1

PublicSubnet2:
  Type: AWS::EC2::Subnet
  Properties:
    VpcId: !Ref ProcessingVPC
    CidrBlock: 10.0.2.0/24
    AvailabilityZone: !Select [1, !GetAZs '']
    MapPublicIpOnLaunch: true
    Tags:
      - Key: Name
        Value: !Sub ${AWS::StackName}-public-2

PublicRouteTable:
  Type: AWS::EC2::RouteTable
  Properties:
    VpcId: !Ref ProcessingVPC
    Tags:
      - Key: Name
        Value: !Sub ${AWS::StackName}-public-rt

PublicRoute:
  Type: AWS::EC2::Route
  DependsOn: AttachGateway
  Properties:
    RouteTableId: !Ref PublicRouteTable
    DestinationCidrBlock: 0.0.0.0/0
    GatewayId: !Ref InternetGateway

SubnetRouteTableAssociation1:
  Type: AWS::EC2::SubnetRouteTableAssociation
  Properties:
    SubnetId: !Ref PublicSubnet1
    RouteTableId: !Ref PublicRouteTable

SubnetRouteTableAssociation2:
  Type: AWS::EC2::SubnetRouteTableAssociation
  Properties:
    SubnetId: !Ref PublicSubnet2
    RouteTableId: !Ref PublicRouteTable

# Security Group for ECS Tasks
ECSSecurityGroup:
  Type: AWS::EC2::SecurityGroup
  Properties:
    GroupName: !Sub ${AWS::StackName}-ecs-sg
    GroupDescription: Security group for ECS processor tasks
    VpcId: !Ref ProcessingVPC
    SecurityGroupEgress:
      - IpProtocol: tcp
        FromPort: 443
        ToPort: 443
        CidrIp: 0.0.0.0/0
        Description: HTTPS to AWS services
    Tags:
      - Key: Name
        Value: !Sub ${AWS::StackName}-ecs-sg

# Outputs
VPCId:
  Description: VPC ID
  Value: !Ref ProcessingVPC
  Export:
    Name: !Sub ${AWS::StackName}-VpcId

PublicSubnetIds:
  Description: Public Subnet IDs
  Value: !Join [',', [!Ref PublicSubnet1, !Ref PublicSubnet2]]
  Export:
    Name: !Sub ${AWS::StackName}-PublicSubnets
```

**Depois, atualizar workflow.asl.json**:
```json
"NetworkConfiguration": {
  "AwsvpcConfiguration": {
    "Subnets": ["${PublicSubnet1}", "${PublicSubnet2}"],
    "SecurityGroups": ["${ECSSecurityGroup}"],
    "AssignPublicIp": "ENABLED"
  }
}
```

**Status**: ⏳ Solução completa - 30 minutos

---

### 🎯 DECISÃO RECOMENDADA

**Para Dev**: OPÇÃO A (usar VPC default)  
**Para Prod**: OPÇÃO B (VPC dedicada)

---

## 🔴 BLOQUEIO 2: Bedrock Quota Limits

### Problema Atual
- **Default Quota**: 10 requests/min, 200K tokens/min
- **Necessidade Real**: ~5-6 chamadas LLM por vídeo
- **Risco**: Com 2-3 vídeos paralelos, pode exceder quota

### Solução: Solicitar Aumento de Quota

#### Passo 1: Acessar Service Quotas Console

```bash
# Via AWS CLI (preparar request)
aws service-quotas request-service-quota-increase \
  --service-code bedrock \
  --quota-code L-3051920E \
  --desired-value 50

aws service-quotas request-service-quota-increase \
  --service-code bedrock \
  --quota-code L-4A5F3F7E \
  --desired-value 500000
```

#### Passo 2: Ou Via Console (Recomendado)

1. Acessar: https://console.aws.amazon.com/servicequotas/
2. Buscar: "Bedrock"
3. Selecionar:
   - **"On-Demand requests per minute"** → Solicitar: **50**
   - **"On-Demand tokens per minute"** → Solicitar: **500,000**
4. Justificativa:
   ```
   Request for AI Techne Academy video processing system.
   
   Use Case: Batch processing of 3-hour video transcriptions to generate 
   technical training documents using Claude Sonnet 4.
   
   Expected Load:
   - 5-6 LLM calls per video (multi-stage pipeline)
   - Average 20K tokens input, 8K tokens output per call
   - Concurrent processing: 3-5 videos
   
   Current quota (10 req/min, 200K tokens/min) insufficient for production load.
   
   Requested quota will support 10 concurrent videos with headroom for spikes.
   ```

#### Passo 3: Aguardar Aprovação (geralmente 1-2 dias úteis)

**Enquanto isso**: Implementar proteções no código

---

### Proteção: Implementar Circuit Breaker

**Criar arquivo**: `src/processor/circuit_breaker.py`

```python
"""
Circuit Breaker para proteção contra quota exhaustion
"""
import time
import logging
from enum import Enum
from typing import Callable, Any

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "CLOSED"    # Normal operation
    OPEN = "OPEN"        # Quota exceeded, blocking calls
    HALF_OPEN = "HALF_OPEN"  # Testing if quota recovered


class CircuitBreakerOpen(Exception):
    """Exception raised when circuit breaker is open."""
    pass


class BedrockCircuitBreaker:
    """
    Circuit breaker for Bedrock API calls.
    
    Prevents cascading failures when quota is exceeded.
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: int = 300,  # 5 minutes
        expected_error_codes: list = None
    ):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.expected_errors = expected_error_codes or [
            'ThrottlingException',
            'TooManyRequestsException',
            'ServiceQuotaExceededException'
        ]
        
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED
        
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.
        
        Args:
            func: Function to call
            *args, **kwargs: Arguments for function
            
        Returns:
            Function result
            
        Raises:
            CircuitBreakerOpen: If circuit is open
        """
        # Check if circuit should transition
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                logger.info("Circuit breaker transitioning to HALF_OPEN")
                self.state = CircuitState.HALF_OPEN
            else:
                time_remaining = self.timeout - (time.time() - self.last_failure_time)
                raise CircuitBreakerOpen(
                    f"Circuit breaker OPEN. Quota likely exceeded. "
                    f"Retry in {time_remaining:.0f}s"
                )
        
        try:
            result = func(*args, **kwargs)
            
            # Success - reset if in HALF_OPEN
            if self.state == CircuitState.HALF_OPEN:
                logger.info("Circuit breaker reset to CLOSED")
                self._reset()
            
            return result
            
        except Exception as e:
            error_name = type(e).__name__
            
            # Check if this is a quota-related error
            if any(err in str(e) or err == error_name for err in self.expected_errors):
                self._record_failure()
                logger.warning(
                    f"Circuit breaker failure {self.failure_count}/{self.failure_threshold}: {e}"
                )
            
            raise
    
    def _record_failure(self):
        """Record a failure and potentially open circuit."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            logger.error(
                f"Circuit breaker OPENED after {self.failure_count} failures"
            )
            self.state = CircuitState.OPEN
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self.last_failure_time is None:
            return True
        
        return (time.time() - self.last_failure_time) >= self.timeout
    
    def _reset(self):
        """Reset circuit breaker to CLOSED state."""
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED
    
    def get_state(self) -> dict:
        """Get current circuit breaker state."""
        return {
            'state': self.state.value,
            'failure_count': self.failure_count,
            'last_failure': self.last_failure_time,
            'threshold': self.failure_threshold,
            'timeout': self.timeout
        }
```

**Integrar no llm_client.py**:

```python
# Adicionar no __init__
from circuit_breaker import BedrockCircuitBreaker, CircuitBreakerOpen

self.circuit_breaker = BedrockCircuitBreaker(
    failure_threshold=5,
    timeout=300  # 5 minutes
)

# Modificar invoke()
def invoke(self, prompt: str, ...):
    try:
        return self.circuit_breaker.call(
            self._invoke_internal,
            prompt,
            system_prompt,
            temperature
        )
    except CircuitBreakerOpen as e:
        logger.error(f"Circuit breaker open: {e}")
        raise ProcessingError(f"Bedrock quota exceeded: {e}")
```

---

## ✅ CHECKLIST DE PRÉ-DEPLOYMENT

### 1. Configuração AWS

- [ ] **VPC/Subnet configurado** (Opção A ou B escolhida)
- [ ] **Subnet ID adicionado** em `parameters/dev.json`
- [ ] **Bedrock quota solicitada** (ou proteção implementada)
- [ ] **Confirmação SNS** (email verificado)
- [ ] **ECR repository** existe e tem imagem

### 2. Validações de Código

- [ ] **Template SAM válido**:
```bash
sam validate --template infrastructure/template.yaml --lint
```

- [ ] **Testes unitários passando**:
```bash
pytest tests/unit/ -v
```

- [ ] **Linting OK**:
```bash
flake8 src/ --max-line-length=100
```

### 3. Verificações de Infraestrutura

- [ ] **ECR image atualizada**:
```bash
# Build e push
./scripts/build-processor.sh
./scripts/push-processor.sh
```

- [ ] **Parameters file atualizado**:
```bash
cat infrastructure/parameters/dev.json
# Verificar: SubnetId, ProcessorImage, NotificationEmail
```

### 4. Backup e Segurança

- [ ] **Backup do DynamoDB** (se existente):
```bash
aws dynamodb create-backup \
  --table-name ai-techne-academy-tracking-dev \
  --backup-name pre-deploy-$(date +%Y%m%d)
```

- [ ] **Tags corretos** no template
- [ ] **IAM roles revisados**

---

## 🚀 COMANDOS DE DEPLOY

### Deploy Step-by-Step

#### 1. Build Local
```bash
cd /home/michel/projects/ai-techne-academy-batch

# Validar template
sam validate --template infrastructure/template.yaml --lint

# Build SAM
sam build --template infrastructure/template.yaml
```

#### 2. Deploy Guided (Primeira Vez)
```bash
sam deploy \
  --guided \
  --template-file infrastructure/template.yaml \
  --stack-name ai-techne-academy-dev \
  --parameter-overrides $(cat infrastructure/parameters/dev.json | jq -r '.Parameters | to_entries | map("\(.key)=\(.value)") | join(" ")') \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

#### 3. Deploy Subsequente (Rápido)
```bash
sam deploy \
  --stack-name ai-techne-academy-dev \
  --parameter-overrides file://infrastructure/parameters/dev.json \
  --no-confirm-changeset \
  --capabilities CAPABILITY_NAMED_IAM
```

#### 4. Validar Deploy
```bash
# Verificar status da stack
aws cloudformation describe-stacks \
  --stack-name ai-techne-academy-dev \
  --query 'Stacks[0].StackStatus'

# Listar outputs
aws cloudformation describe-stacks \
  --stack-name ai-techne-academy-dev \
  --query 'Stacks[0].Outputs'
```

---

## 🧪 TESTE END-TO-END

### Teste 1: Upload de Vídeo de Teste

```bash
# 1. Criar arquivo de teste pequeno (ou usar um existente)
# Para teste, podemos usar um arquivo de áudio de 1 minuto

# 2. Upload para S3
aws s3 cp test-video.mp4 \
  s3://ai-techne-academy-input-dev-<account-id>/test-video-$(date +%Y%m%d).mp4

# 3. Monitorar execução Step Functions
aws stepfunctions list-executions \
  --state-machine-arn <arn-from-outputs> \
  --max-results 1

# 4. Aguardar conclusão e verificar logs
EXECUTION_ARN=$(aws stepfunctions list-executions \
  --state-machine-arn <arn> \
  --max-results 1 \
  --query 'executions[0].executionArn' --output text)

aws stepfunctions describe-execution --execution-arn $EXECUTION_ARN
```

### Teste 2: Verificar Outputs

```bash
# 1. Listar objetos gerados
aws s3 ls s3://ai-techne-academy-output-dev-<account-id>/ --recursive

# 2. Download do documento gerado
aws s3 cp \
  s3://ai-techne-academy-output-dev-<account-id>/<execution-id>/document.md \
  ./test-output.md

# 3. Verificar DynamoDB
aws dynamodb get-item \
  --table-name ai-techne-academy-tracking-dev \
  --key '{"execution_id": {"S": "<execution-id>"}}'
```

---

## 🔍 TROUBLESHOOTING

### Problema: ECS Task não inicia

**Sintoma**: Step Functions falha em "ProcessWithLLM"

**Checklist**:
1. Subnet tem acesso à internet? (IGW configurado)
2. Security Group permite egress HTTPS (443)?
3. IAM role tem permissões ecs:RunTask?
4. ECR image existe e é acessível?

**Debug**:
```bash
# Verificar task definition
aws ecs describe-task-definition \
  --task-definition ai-techne-academy-processor-dev

# Verificar últimas tasks
aws ecs list-tasks --cluster ai-techne-academy-dev
```

### Problema: Bedrock Throttling

**Sintoma**: Logs mostram "ThrottlingException"

**Solução Imediata**:
1. Verificar circuit breaker está funcionando
2. Reduzir concurrent executions
3. Aguardar aprovação de quota

**Workaround**:
```python
# Aumentar delay entre chamadas em llm_client.py
time.sleep(10)  # 10s entre chamadas (6 req/min)
```

### Problema: Lambda Timeout

**Sintoma**: Lambda termina antes de completar

**Solução**:
```yaml
# Aumentar timeout em template.yaml
Timeout: 300  # 5 minutos
```

---

## 📊 MONITORAMENTO PÓS-DEPLOY

### CloudWatch Logs Insights Queries

**Query 1: Erros nas últimas 24h**
```
fields @timestamp, @message
| filter @message like /ERROR/
| sort @timestamp desc
| limit 50
```

**Query 2: Custos por execução**
```
fields execution_id, cost_usd
| filter @message like /Processing result/
| stats avg(cost_usd), max(cost_usd), min(cost_usd)
```

**Query 3: Duração de processamento**
```
fields execution_id, duration_seconds
| filter @message like /Document generation complete/
| stats avg(duration_seconds) as avg_duration
```

### Alarmes Críticos

```bash
# Criar alarme para alta taxa de falhas
aws cloudwatch put-metric-alarm \
  --alarm-name ai-techne-academy-high-failure-rate \
  --alarm-description "Alert when >3 executions fail in 5 minutes" \
  --metric-name ExecutionsFailed \
  --namespace AWS/States \
  --statistic Sum \
  --period 300 \
  --threshold 3 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1
```

---

## 🎯 PRÓXIMOS PASSOS

### Imediato (Hoje)
1. ✅ Escolher solução VPC (A ou B)
2. ✅ Atualizar parameters/dev.json
3. ✅ Solicitar quota Bedrock
4. ✅ Deploy em dev
5. ✅ Teste end-to-end

### Curto Prazo (Semana 1)
1. Implementar circuit breaker
2. Adicionar DLQ para Lambdas
3. Setup CloudWatch Dashboard
4. Documentar runbooks

### Médio Prazo (Mês 1)
1. Testes de carga
2. Otimizações de custo
3. VPC dedicada para prod
4. Disaster recovery plan

---

**Documento mantido por**: Kilo (Architect Mode)  
**Última atualização**: 2024-12-11  
**Próxima revisão**: Após primeiro deploy