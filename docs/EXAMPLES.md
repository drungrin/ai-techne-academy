# Exemplos Práticos - Video Processor

Este documento contém exemplos práticos de uso do sistema de processamento de vídeos.

## 📋 Índice

1. [Upload e Processamento Básico](#upload-e-processamento-básico)
2. [Integração via API](#integração-via-api)
3. [Monitoramento e Troubleshooting](#monitoramento-e-troubleshooting)
4. [Customização de Templates](#customização-de-templates)
5. [Casos de Uso Reais](#casos-de-uso-reais)

---

## Upload e Processamento Básico

### Exemplo 1: Upload Manual via AWS CLI

```bash
# Upload de vídeo
aws s3 cp meeting-recording.mp4 \
  s3://video-processing-input-prod/meetings/2024-12-10/

# Verificar status do processamento
EXECUTION_ARN=$(aws stepfunctions list-executions \
  --state-machine-arn arn:aws:states:us-east-1:123456789:stateMachine:ai-techne-academy-prod \
  --status-filter RUNNING \
  --max-results 1 \
  --query 'executions[0].executionArn' \
  --output text)

# Acompanhar progresso
aws stepfunctions describe-execution \
  --execution-arn $EXECUTION_ARN
```

### Exemplo 2: Upload via SDK Python

```python
import boto3
from datetime import datetime

s3_client = boto3.client('s3')

def upload_video(video_path: str, bucket: str = 'video-processing-input-prod'):
    """Upload de vídeo para processamento"""
    
    # Gerar key único
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    video_name = video_path.split('/')[-1]
    s3_key = f"uploads/{timestamp}/{video_name}"
    
    # Upload
    s3_client.upload_file(
        Filename=video_path,
        Bucket=bucket,
        Key=s3_key,
        ExtraArgs={
            'Metadata': {
                'uploaded_by': 'user@techne.com.br',
                'source': 'api',
                'processing_priority': 'normal'
            }
        }
    )
    
    print(f"✅ Vídeo enviado: s3://{bucket}/{s3_key}")
    return s3_key

# Uso
video_key = upload_video('path/to/meeting.mp4')
```

### Exemplo 3: Verificar Resultado

```python
import boto3
import json

s3_client = boto3.client('s3')

def download_document(video_key: str, output_bucket: str = 'video-processing-output-prod'):
    """Download do documento gerado"""
    
    # Listar documentos relacionados ao vídeo
    response = s3_client.list_objects_v2(
        Bucket=output_bucket,
        Prefix=f"documents/{video_key.split('/')[-1]}"
    )
    
    if 'Contents' not in response:
        print("❌ Documento ainda não foi gerado")
        return None
    
    # Pegar o documento mais recente
    latest_doc = sorted(response['Contents'], key=lambda x: x['LastModified'])[-1]
    doc_key = latest_doc['Key']
    
    # Download
    local_path = f"output/{doc_key.split('/')[-1]}"
    s3_client.download_file(output_bucket, doc_key, local_path)
    
    print(f"✅ Documento baixado: {local_path}")
    return local_path

# Uso
doc_path = download_document('uploads/20241210_143000/meeting.mp4')
```

---

## Integração via API

### Exemplo 4: Webhook de Notificação

```python
from flask import Flask, request, jsonify
import boto3

app = Flask(__name__)
s3_client = boto3.client('s3')

@app.route('/webhook/video-processed', methods=['POST'])
def video_processed_webhook():
    """Recebe notificação quando vídeo é processado"""
    
    data = request.json
    
    print(f"📨 Notificação recebida:")
    print(f"  - Execution ID: {data.get('execution_id')}")
    print(f"  - Status: {data.get('status')}")
    print(f"  - Output Key: {data.get('output_key')}")
    
    # Processar documento gerado
    if data.get('status') == 'COMPLETED':
        output_key = data.get('output_key')
        
        # Download do documento
        response = s3_client.get_object(
            Bucket=data.get('output_bucket'),
            Key=output_key
        )
        
        document_content = response['Body'].read().decode('utf-8')
        
        # Enviar para sistema interno, banco de dados, etc.
        send_to_internal_system(document_content)
        
        return jsonify({'status': 'processed'}), 200
    
    return jsonify({'status': 'acknowledged'}), 200

def send_to_internal_system(document: str):
    """Integração com sistema interno"""
    # Implementar integração
    pass

if __name__ == '__main__':
    app.run(port=5000)
```

### Exemplo 5: Configurar SNS para Webhook

```python
import boto3

sns_client = boto3.client('sns')

def setup_webhook_notification(webhook_url: str, topic_arn: str):
    """Configurar webhook para receber notificações"""
    
    # Subscribe webhook ao tópico SNS
    response = sns_client.subscribe(
        TopicArn=topic_arn,
        Protocol='https',
        Endpoint=webhook_url
    )
    
    subscription_arn = response['SubscriptionArn']
    print(f"✅ Webhook configurado: {subscription_arn}")
    
    return subscription_arn

# Uso
topic_arn = 'arn:aws:sns:us-east-1:123456789:video-processing-notifications-prod'
webhook_url = 'https://api.example.com/webhook/video-processed'

setup_webhook_notification(webhook_url, topic_arn)
```

---

## Monitoramento e Troubleshooting

### Exemplo 6: Script de Monitoramento

```python
import boto3
from datetime import datetime, timedelta

cloudwatch = boto3.client('cloudwatch')
stepfunctions = boto3.client('stepfunctions')

def get_processing_metrics(hours: int = 24):
    """Obter métricas de processamento das últimas N horas"""
    
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours)
    
    # Buscar métricas do CloudWatch
    response = cloudwatch.get_metric_statistics(
        Namespace='AWS/States',
        MetricName='ExecutionsFailed',
        StartTime=start_time,
        EndTime=end_time,
        Period=3600,
        Statistics=['Sum']
    )
    
    total_failures = sum(point['Sum'] for point in response['Datapoints'])
    
    # Buscar execuções recentes
    executions = stepfunctions.list_executions(
        stateMachineArn='arn:aws:states:us-east-1:123456789:stateMachine:ai-techne-academy-prod',
        maxResults=100
    )
    
    total_executions = len(executions['executions'])
    failed_executions = [e for e in executions['executions'] if e['status'] == 'FAILED']
    
    print(f"📊 Métricas das últimas {hours} horas:")
    print(f"  - Total de execuções: {total_executions}")
    print(f"  - Execuções com falha: {len(failed_executions)}")
    print(f"  - Taxa de sucesso: {((total_executions - len(failed_executions)) / total_executions * 100):.1f}%")
    
    # Listar falhas recentes
    if failed_executions:
        print(f"\n❌ Falhas recentes:")
        for exec in failed_executions[:5]:
            print(f"  - {exec['name']}: {exec['stopDate']}")

# Uso
get_processing_metrics(hours=24)
```

### Exemplo 7: Debug de Execução Falha

```python
import boto3
import json

stepfunctions = boto3.client('stepfunctions')
logs_client = boto3.client('logs')

def debug_failed_execution(execution_arn: str):
    """Debug detalhado de execução falha"""
    
    # Obter detalhes da execução
    execution = stepfunctions.describe_execution(executionArn=execution_arn)
    
    print(f"🔍 Debug da execução: {execution['name']}")
    print(f"  - Status: {execution['status']}")
    print(f"  - Início: {execution['startDate']}")
    print(f"  - Fim: {execution.get('stopDate', 'N/A')}")
    
    # Obter histórico de eventos
    history = stepfunctions.get_execution_history(
        executionArn=execution_arn,
        maxResults=100,
        reverseOrder=True
    )
    
    # Encontrar o erro
    for event in history['events']:
        if event['type'].endswith('Failed'):
            print(f"\n❌ Erro encontrado:")
            print(f"  - Tipo: {event['type']}")
            print(f"  - Detalhes: {json.dumps(event, indent=2, default=str)}")
            
            # Se for erro de Lambda/ECS, buscar logs
            if 'taskFailedEventDetails' in event:
                error = event['taskFailedEventDetails'].get('error', 'Unknown')
                cause = event['taskFailedEventDetails'].get('cause', 'Unknown')
                print(f"  - Error: {error}")
                print(f"  - Causa: {cause}")

# Uso
execution_arn = 'arn:aws:states:us-east-1:123456789:execution:ai-techne-academy-prod:exec-123'
debug_failed_execution(execution_arn)
```

---

## Customização de Templates

### Exemplo 8: Template Customizado

```python
from jinja2 import Template

# Template customizado para relatórios executivos
EXECUTIVE_TEMPLATE = """
# {{ title }}

**Cliente**: {{ client_name }}
**Data da Reunião**: {{ meeting_date }}
**Participantes**: {{ participants | join(', ') }}

---

## 📊 Sumário Executivo

{{ executive_summary }}

## 🎯 Objetivos Alcançados

{% for objective in objectives %}
- {{ objective }}
{% endfor %}

## 📋 Próximos Passos

{% for step in next_steps %}
- [ ] {{ step }}
{% endfor %}

## 📎 Anexos

- [Transcrição Completa]({{ transcript_link }})
- [Gravação do Vídeo]({{ video_link }})

---
*Documento gerado automaticamente em {{ generated_at }}*
"""

def generate_custom_document(data: dict) -> str:
    """Gerar documento com template customizado"""
    
    template = Template(EXECUTIVE_TEMPLATE)
    
    return template.render(
        title=data.get('title', 'Relatório de Reunião'),
        client_name=data.get('client_name'),
        meeting_date=data.get('meeting_date'),
        participants=data.get('participants', []),
        executive_summary=data.get('summary'),
        objectives=data.get('objectives', []),
        next_steps=data.get('next_steps', []),
        transcript_link=data.get('transcript_link'),
        video_link=data.get('video_link'),
        generated_at=data.get('generated_at')
    )

# Uso
data = {
    'title': 'Reunião de Kickoff - Projeto X',
    'client_name': 'Empresa ABC',
    'meeting_date': '2024-12-10',
    'participants': ['João Silva', 'Maria Santos', 'Pedro Costa'],
    'summary': 'Reunião inicial para definir escopo e cronograma...',
    'objectives': [
        'Definir requisitos do projeto',
        'Estabelecer cronograma',
        'Alocar recursos'
    ],
    'next_steps': [
        'Enviar proposta comercial até 15/12',
        'Agendar reunião técnica',
        'Preparar ambiente de desenvolvimento'
    ],
    'transcript_link': 's3://bucket/transcripts/meeting-123.json',
    'video_link': 's3://bucket/videos/meeting-123.mp4',
    'generated_at': '2024-12-10 15:30:00'
}

document = generate_custom_document(data)
print(document)
```

---

## Casos de Uso Reais

### Exemplo 9: Processamento em Lote

```python
import boto3
from concurrent.futures import ThreadPoolExecutor
import glob

s3_client = boto3.client('s3')

def process_video_batch(video_folder: str, bucket: str = 'video-processing-input-prod'):
    """Processar lote de vídeos"""
    
    video_files = glob.glob(f"{video_folder}/*.mp4")
    
    print(f"📦 Processando {len(video_files)} vídeos...")
    
    def upload_single(video_path):
        key = f"batch/{video_path.split('/')[-1]}"
        s3_client.upload_file(video_path, bucket, key)
        return key
    
    # Upload paralelo
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(upload_single, video_files))
    
    print(f"✅ {len(results)} vídeos enviados para processamento")
    return results

# Uso
uploaded_keys = process_video_batch('./videos/december-meetings/')
```

### Exemplo 10: Integração com Sistema de Tickets

```python
import boto3
import requests

def create_ticket_from_document(document_key: str):
    """Criar ticket no Jira com informações do documento"""
    
    s3_client = boto3.client('s3')
    
    # Download do documento
    response = s3_client.get_object(
        Bucket='video-processing-output-prod',
        Key=document_key
    )
    
    document = response['Body'].read().decode('utf-8')
    
    # Extrair action items (parsing básico)
    action_items = []
    in_action_section = False
    
    for line in document.split('\n'):
        if '## 6. Action Items' in line:
            in_action_section = True
        elif in_action_section and line.startswith('- [ ]'):
            action_items.append(line.replace('- [ ]', '').strip())
        elif in_action_section and line.startswith('##'):
            break
    
    # Criar tickets no Jira
    jira_api = 'https://your-domain.atlassian.net/rest/api/3'
    headers = {
        'Authorization': 'Bearer YOUR_API_TOKEN',
        'Content-Type': 'application/json'
    }
    
    for item in action_items:
        ticket_data = {
            'fields': {
                'project': {'key': 'PROJ'},
                'summary': item,
                'description': {
                    'type': 'doc',
                    'version': 1,
                    'content': [{
                        'type': 'paragraph',
                        'content': [{
                            'type': 'text',
                            'text': f'Action item extraído do documento: {document_key}'
                        }]
                    }]
                },
                'issuetype': {'name': 'Task'}
            }
        }
        
        response = requests.post(
            f'{jira_api}/issue',
            headers=headers,
            json=ticket_data
        )
        
        if response.status_code == 201:
            ticket_key = response.json()['key']
            print(f"✅ Ticket criado: {ticket_key} - {item}")
        else:
            print(f"❌ Erro ao criar ticket: {response.text}")

# Uso
create_ticket_from_document('documents/meeting-123_20241210.md')
```

### Exemplo 11: Relatório Consolidado Mensal

```python
import boto3
from datetime import datetime, timedelta
import pandas as pd

def generate_monthly_report(year: int, month: int):
    """Gerar relatório consolidado mensal"""
    
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('video-processing-tracking-prod')
    
    # Buscar todas as execuções do mês
    start_date = datetime(year, month, 1)
    end_date = (start_date + timedelta(days=32)).replace(day=1)
    
    # Scan da tabela (em produção, usar query com GSI)
    response = table.scan()
    executions = response['Items']
    
    # Filtrar por mês
    monthly_executions = [
        e for e in executions
        if start_date <= datetime.fromisoformat(e['updated_at']) < end_date
    ]
    
    # Análise
    total = len(monthly_executions)
    completed = len([e for e in monthly_executions if e['status'] == 'COMPLETED'])
    failed = len([e for e in monthly_executions if e['status'] == 'FAILED'])
    
    # Criar DataFrame
    df = pd.DataFrame([{
        'execution_id': e['execution_id'],
        'status': e['status'],
        'video_key': e.get('video_key', 'N/A'),
        'updated_at': e['updated_at']
    } for e in monthly_executions])
    
    # Gerar relatório
    report = f"""
# Relatório Mensal - {year}/{month:02d}

## Estatísticas Gerais

- **Total de Processamentos**: {total}
- **Concluídos com Sucesso**: {completed} ({completed/total*100:.1f}%)
- **Falhas**: {failed} ({failed/total*100:.1f}%)

## Processamentos por Dia

{df.groupby(df['updated_at'].str[:10]).size().to_string()}

## Top 5 Vídeos Processados

{df.head(5).to_string(index=False)}
"""
    
    # Salvar relatório
    filename = f"reports/monthly_{year}_{month:02d}.md"
    with open(filename, 'w') as f:
        f.write(report)
    
    print(f"✅ Relatório gerado: {filename}")
    return report

# Uso
report = generate_monthly_report(2024, 12)
```

---

## 🎓 Dicas e Best Practices

### 1. Otimização de Custos

```python
# Implementar cleanup automático de arquivos temporários
def cleanup_old_files(bucket: str, days: int = 7):
    """Limpar arquivos antigos para reduzir custos de storage"""
    
    s3_client = boto3.client('s3')
    cutoff_date = datetime.now() - timedelta(days=days)
    
    # Listar e deletar objetos antigos
    paginator = s3_client.get_paginator('list_objects_v2')
    
    for page in paginator.paginate(Bucket=bucket, Prefix='transcripts/'):
        if 'Contents' in page:
            for obj in page['Contents']:
                if obj['LastModified'].replace(tzinfo=None) < cutoff_date:
                    s3_client.delete_object(Bucket=bucket, Key=obj['Key'])
                    print(f"🗑️  Deletado: {obj['Key']}")
```

### 2. Rate Limiting para Bedrock

```python
from ratelimit import limits, sleep_and_retry

# Limitar chamadas ao Bedrock (exemplo: 10 req/minuto)
@sleep_and_retry
@limits(calls=10, period=60)
def call_bedrock_with_rate_limit(client, prompt):
    """Chamar Bedrock com rate limiting"""
    return client.generate(prompt)
```

### 3. Retry com Circuit Breaker

```python
from circuitbreaker import circuit

@circuit(failure_threshold=5, recovery_timeout=60)
def reliable_transcribe_call(transcribe_client, job_name):
    """Chamada robusta ao Transcribe com circuit breaker"""
    return transcribe_client.get_transcription_job(
        TranscriptionJobName=job_name
    )
```

---

**Nota**: Todos os exemplos acima são ilustrativos. Adapte conforme suas necessidades específicas e sempre teste em ambiente de desenvolvimento antes de usar em produção.