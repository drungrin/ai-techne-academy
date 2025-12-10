# AI Techne Academy - Infrastructure

This directory contains the AWS infrastructure as code (IaC) using AWS SAM (Serverless Application Model).

## 📁 Structure

```
infrastructure/
├── template.yaml           # Main SAM template
├── parameters/
│   ├── dev.json           # Development environment parameters
│   ├── staging.json       # Staging environment parameters (future)
│   └── prod.json          # Production environment parameters (future)
├── statemachine/          # Step Functions definitions (Phase 3)
│   └── .gitkeep
└── README.md              # This file
```

## 🚀 Quick Start

### Prerequisites

- AWS CLI configured (`aws configure`)
- AWS SAM CLI installed (`sam --version`)
- Appropriate IAM permissions to create resources

### Validate Template

```bash
sam validate --template infrastructure/template.yaml --lint
```

### Deploy to Development

```bash
# Option 1: Using samconfig.toml (recommended)
sam deploy

# Option 2: Using parameters file
sam deploy \
  --template-file infrastructure/template.yaml \
  --parameter-overrides $(cat infrastructure/parameters/dev.json | jq -r '.[] | "\(.ParameterKey)=\(.ParameterValue)"' | tr '\n' ' ') \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --stack-name ai-techne-academy-dev

# Option 3: Guided deployment (first time)
sam deploy --guided
```

### Deploy to Production

```bash
sam deploy \
  --template-file infrastructure/template.yaml \
  --parameter-overrides file://infrastructure/parameters/prod.json \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --stack-name ai-techne-academy-prod \
  --confirm-changeset
```

## 📦 Resources Created (Phase 1.2)

### S3 Buckets
- **Input Bucket**: `ai-techne-academy-input-{env}-{account-id}`
  - Video uploads
  - Lifecycle: Archive to Glacier after 30 days
  - EventBridge notifications enabled

- **Output Bucket**: `ai-techne-academy-output-{env}-{account-id}`
  - Generated documents
  - Versioning enabled
  - Encrypted at rest

- **Transcription Bucket**: `ai-techne-academy-transcripts-{env}-{account-id}`
  - Temporary transcription storage
  - Lifecycle: Delete after 7 days

### DynamoDB
- **Tracking Table**: `ai-techne-academy-tracking-{env}`
  - Primary Key: `execution_id`
  - GSI: `video-key-index` (video_key + created_at)
  - Streams enabled for audit
  - Pay-per-request billing

### SNS
- **Notification Topic**: `ai-techne-academy-notifications-{env}`
  - Email subscription (configurable via parameter)
  - Used for success/failure notifications

### CloudWatch Log Groups
- `/aws/vendedlogs/states/ai-techne-academy-{env}` - Step Functions logs
- `/ecs/ai-techne-academy-processor-{env}` - ECS processor logs
- `/aws/lambda/ai-techne-academy-{env}` - Lambda function logs
- Retention: 30 days (configurable)

### IAM Roles
- **LambdaExecutionRole**: For Lambda functions
  - S3 read/write
  - DynamoDB CRUD
  - SNS publish
  - Transcribe access

- **ECSTaskExecutionRole**: For ECS task execution
  - ECR pull permissions
  - CloudWatch Logs write

- **ECSTaskRole**: For ECS task application
  - S3 read/write
  - Bedrock invoke
  - DynamoDB CRUD

## 🔧 Configuration

### Parameters

Edit `infrastructure/parameters/dev.json`:

```json
{
  "Environment": "dev",
  "ProjectName": "ai-techne-academy",
  "NotificationEmail": "your-email@techne.com.br",
  "InputBucketRetentionDays": 30,
  "TranscriptionBucketRetentionDays": 7,
  "LogRetentionDays": 30
}
```

### Environment Variables

The template automatically sets these environment variables for Lambda/ECS:
- `LOG_LEVEL`: INFO
- `ENVIRONMENT`: {Environment parameter}
- `PROJECT_NAME`: {ProjectName parameter}

## 📊 Monitoring

### View Stack Resources

```bash
aws cloudformation describe-stack-resources \
  --stack-name ai-techne-academy-dev \
  --query 'StackResources[*].[LogicalResourceId,ResourceType,ResourceStatus]' \
  --output table
```

### Get Stack Outputs

```bash
aws cloudformation describe-stacks \
  --stack-name ai-techne-academy-dev \
  --query 'Stacks[0].Outputs' \
  --output table
```

### View Logs

```bash
# Step Functions logs
aws logs tail /aws/vendedlogs/states/ai-techne-academy-dev --follow

# ECS processor logs
aws logs tail /ecs/ai-techne-academy-processor-dev --follow

# Lambda logs
aws logs tail /aws/lambda/ai-techne-academy-dev --follow
```

## 🗑️ Cleanup

```bash
# Delete stack and all resources
sam delete --stack-name ai-techne-academy-dev

# Or using AWS CLI
aws cloudformation delete-stack --stack-name ai-techne-academy-dev
```

**⚠️ Warning**: S3 buckets with versioning enabled need to be emptied first:

```bash
# Empty buckets before deletion
aws s3 rm s3://ai-techne-academy-input-dev-{account-id} --recursive
aws s3 rm s3://ai-techne-academy-output-dev-{account-id} --recursive
aws s3 rm s3://ai-techne-academy-transcripts-dev-{account-id} --recursive

# Then delete versions
aws s3api delete-bucket --bucket ai-techne-academy-input-dev-{account-id}
```

## 💰 Cost Estimation

Approximate monthly costs for development environment:

| Resource | Usage | Cost (USD) |
|----------|-------|------------|
| S3 Storage | ~10 GB | $0.23 |
| DynamoDB | On-demand, low usage | $1-2 |
| CloudWatch Logs | 1 GB/month | $0.50 |
| SNS | 100 notifications | $0.00 |
| **Total** | | **~$2-3/month** |

Note: Actual processing costs (Transcribe, Bedrock, ECS) will be added in Phase 2.

## 🔐 Security

All resources follow security best practices:
- ✅ Encryption at rest enabled (S3, DynamoDB, SNS)
- ✅ Encryption in transit (TLS 1.2+)
- ✅ Least privilege IAM roles
- ✅ Public access blocked on S3 buckets
- ✅ Resource tagging for cost tracking

## 📝 Tags

All resources are tagged with:
- `Project`: ai-techne-academy
- `Environment`: {env}
- `ManagedBy`: SAM

## 🚧 Future Phases

### Phase 2: Lambda Functions & ECS
- Trigger function
- Transcribe starter function
- Finalizer function
- ECS task definition
- ECR repository

### Phase 3: Orchestration
- Step Functions state machine
- EventBridge rules
- VPC and networking (if needed)

## 📚 References

- [AWS SAM Documentation](https://docs.aws.amazon.com/serverless-application-model/)
- [CloudFormation Resource Reference](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-template-resource-type-ref.html)
- [Project Specification](../docs/SPECIFICATION.md)
- [Implementation Plan](../docs/IMPLEMENTATION_PLAN.md)

## 🤝 Contributing

When modifying infrastructure:
1. Update `template.yaml`
2. Validate: `sam validate --template infrastructure/template.yaml --lint`
3. Test in dev: `sam deploy`
4. Update this README if needed
5. Commit changes
6. Create PR for review

---

**Last Updated**: 2024-12-10  
**Template Version**: 1.0.0  
**Status**: Phase 1.2 Complete - Base Infrastructure