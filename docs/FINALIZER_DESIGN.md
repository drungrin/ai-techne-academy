# Lambda Finalizer Function - Technical Design

**Version**: 1.0  
**Date**: 2024-12-11  
**Status**: Design Complete - Ready for Implementation  
**Author**: Kilo Code (Architect Mode)

---

## 1. Overview

### Purpose
The Finalizer Function is the last stage in the AI Techne Academy video processing pipeline. It updates final execution status, publishes comprehensive notifications, records metrics, and ensures proper workflow closure with robust retry logic.

### Position in Architecture
```
Processing Complete → [Finalizer Function] → DynamoDB Update (with retry)
                                ↓
                         SNS Notification
                                ↓
                       CloudWatch Metrics
```

### Key Responsibilities
1. Receive execution results from Step Functions (success/failure/partial)
2. Validate and determine final status (COMPLETED, FAILED, PARTIAL_SUCCESS)
3. Update DynamoDB tracking record with retry logic (3 attempts, exponential backoff)
4. Publish detailed SNS notification with download links and summary
5. Record comprehensive CloudWatch metrics (duration, cost, success rate)
6. Calculate processing costs and generate execution summary
7. Implement graceful degradation for non-critical failures

---

## 2. Function Specifications

### Runtime Configuration
```yaml
Runtime: Python 3.12
Timeout: 90 seconds
Memory: 256 MB
Handler: app.lambda_handler
IAM Role: LambdaExecutionRole
```

### Environment Variables
| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `TRACKING_TABLE` | DynamoDB table name | Yes | - |
| `NOTIFICATION_TOPIC_ARN` | SNS topic ARN | Yes | - |
| `OUTPUT_BUCKET` | S3 bucket for documents | Yes | - |
| `ENVIRONMENT` | Environment name | Yes | - |
| `LOG_LEVEL` | Logging level | No | `INFO` |
| `MAX_RETRY_ATTEMPTS` | Max DynamoDB retries | No | `3` |
| `RETRY_DELAY_BASE` | Base delay for backoff (sec) | No | `1` |

### AWS Permissions Required
- **DynamoDB**: `UpdateItem`, `GetItem`
- **SNS**: `Publish`
- **S3**: `GetObject` (for document metadata)
- **CloudWatch**: `PutMetricData`
- **CloudWatch Logs**: `CreateLogStream`, `PutLogEvents`

---

## 3. Input/Output Specifications

### Input Event Formats

#### Success Event
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
  }
}
```

#### Failure Event
```json
{
  "execution_id": "550e8400-...",
  "status": "FAILED",
  "error": {
    "stage": "llm_processing",
    "error_code": "BedrockQuotaExceeded",
    "error_message": "Rate limit exceeded",
    "timestamp": "2024-12-11T11:30:00Z"
  },
  "processing_results": {
    "transcription": {"status": "COMPLETED"},
    "llm_processing": {"status": "FAILED"}
  }
}
```

### Output Response
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
      "documents_generated": 2
    }
  }
}
```

---

## 4. Core Logic

### 4.1 Status Determination
```python
def determine_final_status(processing_results: Dict) -> str:
    """
    COMPLETED: All stages successful
    PARTIAL_SUCCESS: Transcription OK, LLM partial/failed
    FAILED: Critical stage failed
    """
    transcription = processing_results.get('transcription', {}).get('status')
    llm = processing_results.get('llm_processing', {}).get('status')
    
    if transcription == 'FAILED':
        return 'FAILED'
    if transcription == 'COMPLETED' and llm == 'COMPLETED':
        return 'COMPLETED'
    if transcription == 'COMPLETED' and llm in ['PARTIAL', 'FAILED']:
        return 'PARTIAL_SUCCESS'
    return 'FAILED'
```

### 4.2 DynamoDB Update with Retry
```python
def update_tracking_with_retry(
    execution_id: str,
    final_status: str,
    summary: Dict,
    max_attempts: int = 3
) -> bool:
    """Exponential backoff: 1s, 2s, 4s + jitter"""
    for attempt in range(1, max_attempts + 1):
        try:
            table.update_item(
                Key={'execution_id': execution_id},
                UpdateExpression="""
                    SET #status = :status,
                        #stages.#finalizer = :data,
                        updated_at = :ts,
                        completion_time = :ct,
                        total_duration_seconds = :dur,
                        processing_metrics = :metrics,
                        cost_estimate_usd = :cost
                """,
                ExpressionAttributeValues={
                    ':status': final_status,
                    ':data': {
                        'status': 'completed',
                        'timestamp': datetime.utcnow().isoformat(),
                        'retry_attempts': attempt
                    },
                    ':ts': datetime.utcnow().isoformat(),
                    ':ct': summary['completion_time'],
                    ':dur': summary['duration_seconds'],
                    ':metrics': summary['metrics'],
                    ':cost': summary['cost_usd']
                }
            )
            return True
        except ClientError as e:
            if attempt == max_attempts:
                raise
            delay = (2 ** (attempt - 1)) + random.uniform(0, 0.3)
            time.sleep(delay)
    return False
```

### 4.3 Cost Calculation
```python
def calculate_cost(metrics: Dict) -> float:
    """
    Transcribe: $0.024/min
    Bedrock: $0.003/1K input + $0.015/1K output tokens
    S3: $0.023/GB/month (negligible)
    """
    video_min = metrics.get('transcription_duration_seconds', 0) / 60
    transcribe = video_min * 0.024
    
    tokens = metrics.get('tokens_used', 45000)
    bedrock = (tokens * 0.67 / 1000 * 0.003) + (tokens * 0.33 / 1000 * 0.015)
    
    return round(transcribe + bedrock, 2)
```

---

## 5. SNS Notification Structure

### Success Notification
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
      "started": "2024-12-11 10:00 UTC",
      "completed": "2024-12-11 12:03 UTC",
      "duration": "2h 3m",
      "cost_usd": 1.45
    },
    "results": {
      "transcription": {
        "speakers": 3,
        "download": "https://s3.console.aws.amazon.com/..."
      },
      "documents": {
        "types": ["Training", "Troubleshooting"],
        "size_mb": 2.34,
        "download": "https://s3.console.aws.amazon.com/..."
      }
    }
  },
  "MessageAttributes": {
    "execution_id": {"DataType": "String", "StringValue": "550e8400-..."},
    "status": {"DataType": "String", "StringValue": "COMPLETED"},
    "cost_usd": {"DataType": "Number", "StringValue": "1.45"}
  }
}
```

### Failure Notification
```json
{
  "Subject": "❌ Video Processing Failed - meeting.mp4",
  "Message": {
    "status": "FAILED",
    "error": {
      "stage": "llm_processing",
      "code": "BedrockQuotaExceeded",
      "message": "Rate limit exceeded"
    },
    "partial_results": {
      "transcription": "Available",
      "download": "https://..."
    },
    "actions": [
      "Check AWS Bedrock quotas",
      "Review CloudWatch logs",
      "Contact support"
    ]
  }
}
```

---

## 6. CloudWatch Metrics

### Metrics to Record
```python
METRICS = [
    {
        "MetricName": "ProcessingDuration",
        "Unit": "Seconds",
        "Value": duration,
        "Dimensions": [
            {"Name": "Environment", "Value": env},
            {"Name": "Status", "Value": status}
        ]
    },
    {
        "MetricName": "ProcessingSuccess",
        "Unit": "Count",
        "Value": 1 if status == "COMPLETED" else 0
    },
    {
        "MetricName": "ProcessingFailure",
        "Unit": "Count",
        "Value": 1 if status == "FAILED" else 0
    },
    {
        "MetricName": "TokensProcessed",
        "Unit": "Count",
        "Value": tokens
    },
    {
        "MetricName": "ProcessingCost",
        "Unit": "None",  # USD
        "Value": cost_usd
    }
]
```

---

## 7. Error Handling

### Error Categories
| Category | Severity | Action | Notify? |
|----------|----------|--------|---------|
| Input Validation | Low | Return 400 | No |
| DynamoDB Failure | **Critical** | Retry 3x | Yes |
| SNS Failure | Medium | Log warning | Yes |
| Metrics Failure | Low | Log warning | No |

### Graceful Degradation
```python
def finalize_execution(event: Dict) -> Dict:
    results = {
        "tracking_updated": False,
        "notification_sent": False,
        "metrics_recorded": False
    }
    
    # Critical: Update DynamoDB (with retry)
    try:
        results["tracking_updated"] = update_tracking_with_retry(...)
    except Exception as e:
        logger.critical(f"Failed to update tracking: {e}")
    
    # Important: Send SNS
    try:
        results["notification_sent"] = publish_notification(...)
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")
    
    # Nice-to-have: Metrics
    try:
        results["metrics_recorded"] = record_metrics(...)
    except Exception as e:
        logger.warning(f"Failed to record metrics: {e}")
    
    return results
```

---

## 8. Testing Strategy

### Unit Test Suites (7 suites, 25+ cases)

1. **TestInputParsing**: Parse success/failure/partial events
2. **TestStatusDetermination**: Verify status logic
3. **TestMetricsCalculation**: Cost and duration calculations
4. **TestDynamoDBRetry**: Exponential backoff, retry limits
5. **TestSNSNotifications**: Build and publish notifications
6. **TestCloudWatchMetrics**: Record all metrics correctly
7. **TestLambdaHandler**: End-to-end flows, graceful degradation

**Coverage Goal**: >85% (100% on critical paths)

---

## 9. Implementation Checklist

### Phase 1: Core Implementation (2h)
- [ ] Create [`app.py`](../src/functions/finalizer/app.py) with handler
- [ ] Implement status determination logic
- [ ] Implement DynamoDB update with exponential backoff
- [ ] Implement cost calculation
- [ ] Implement SNS notification builder
- [ ] Implement CloudWatch metrics recording
- [ ] Implement graceful degradation

### Phase 2: Testing (1.5h)
- [ ] Create [`test_finalizer.py`](../tests/unit/test_finalizer.py)
- [ ] Write 25+ unit tests covering all scenarios
- [ ] Mock AWS services (DynamoDB, SNS, CloudWatch)
- [ ] Achieve >85% coverage

### Phase 3: Documentation (0.5h)
- [ ] Create [`README.md`](../src/functions/finalizer/README.md)
- [ ] Document all functions and parameters
- [ ] Add usage examples
- [ ] Create troubleshooting guide

### Phase 4: Infrastructure (0.5h)
- [ ] Update [`template.yaml`](../infrastructure/template.yaml)
- [ ] Add FinalizerFunction resource
- [ ] Configure IAM permissions
- [ ] Add CloudWatch log group and alarms
- [ ] Validate SAM template

### Phase 5: Integration (0.5h)
- [ ] Test locally with SAM CLI
- [ ] Deploy to dev environment
- [ ] Run integration tests
- [ ] Verify notifications and metrics

**Total Estimated Time**: 5 hours

---

## 10. Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| Cold Start | <3s | First invocation |
| Warm Execution | <2s | Without retries |
| With Retries | <10s | Worst case (3 retries) |
| Memory Usage | <128MB | Typical usage |

---

## 11. Monitoring

### CloudWatch Alarms
- **HighFailureRate**: >10% failures in 5 min
- **LongExecutionTime**: Execution >30s
- **DynamoDBRetryFailures**: Any critical failures after retries
- **SNSPublishFailures**: >3 failures in 5 min

### Key Logs to Monitor
```json
{
  "level": "INFO",
  "execution_id": "550e8400-...",
  "final_status": "COMPLETED",
  "action": "finalize_execution",
  "results": {
    "tracking_updated": true,
    "notification_sent": true,
    "metrics_recorded": true
  },
  "duration_ms": 1245
}
```

---

## 12. Security Considerations

### IAM Least Privilege
```json
{
  "Effect": "Allow",
  "Action": [
    "dynamodb:UpdateItem",
    "dynamodb:GetItem",
    "sns:Publish",
    "cloudwatch:PutMetricData"
  ],
  "Resource": [
    "arn:aws:dynamodb:*:*:table/ai-techne-academy-tracking-*",
    "arn:aws:sns:*:*:ai-techne-academy-notifications-*"
  ]
}
```

### Input Sanitization
- Validate all execution IDs (UUID format)
- Sanitize S3 URIs before inclusion in notifications
- Limit string lengths to prevent overflow
- Validate status values against allowed set

---

## 13. References

### AWS Documentation
- [DynamoDB UpdateItem](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/WorkingWithItems.html)
- [SNS Publish](https://docs.aws.amazon.com/sns/latest/api/API_Publish.html)
- [CloudWatch PutMetricData](https://docs.aws.amazon.com/AmazonCloudWatch/latest/APIReference/API_PutMetricData.html)
- [Exponential Backoff](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/)

### Project Documentation
- [Project Specification](./SPECIFICATION.md)
- [Implementation Plan](./IMPLEMENTATION_PLAN.md)
- [Trigger Function](../src/functions/trigger/README.md)
- [Transcribe Starter](./TRANSCRIBE_STARTER_DESIGN.md)

---

**Design Status**: ✅ Complete and Ready for Implementation  
**Next Step**: Switch to Code mode to implement the function  
**Estimated Implementation Time**: 5 hours total  
**Priority**: High (completes Phase 2.1 Lambda Functions)