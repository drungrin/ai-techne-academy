"""
Lambda Finalizer Function
Final stage of video processing pipeline - updates status, sends notifications, records metrics
"""
import os
import json
import logging
import time
import random
from datetime import datetime
from typing import Dict, Any, Optional, List
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))

# AWS clients
dynamodb = boto3.resource('dynamodb')
sns_client = boto3.client('sns')
cloudwatch = boto3.client('cloudwatch')
s3_client = boto3.client('s3')

# Environment variables
TRACKING_TABLE = os.getenv('TRACKING_TABLE')
NOTIFICATION_TOPIC_ARN = os.getenv('NOTIFICATION_TOPIC_ARN')
OUTPUT_BUCKET = os.getenv('OUTPUT_BUCKET')
ENVIRONMENT = os.getenv('ENVIRONMENT', 'dev')
MAX_RETRY_ATTEMPTS = int(os.getenv('MAX_RETRY_ATTEMPTS', '3'))
RETRY_DELAY_BASE = float(os.getenv('RETRY_DELAY_BASE', '1.0'))

# Valid final statuses
VALID_STATUSES = {'COMPLETED', 'FAILED', 'PARTIAL_SUCCESS'}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for finalizing video processing execution
    
    Args:
        event: Step Functions execution result
        context: Lambda context
        
    Returns:
        Response dict with finalization results
    """
    logger.info(f"Finalizer invoked: {json.dumps(event)}")
    
    try:
        # Parse and validate input
        execution_data = parse_input_event(event)
        if not execution_data:
            return create_response(400, "Invalid input event format")
        
        execution_id = execution_data['execution_id']
        logger.info(f"Finalizing execution {execution_id}")
        
        # Determine final status
        final_status = determine_final_status(execution_data)
        logger.info(f"Final status determined: {final_status}")
        
        # Calculate metrics and summary
        summary = build_execution_summary(execution_data, final_status)
        
        # Initialize results tracking
        results = {
            'tracking_updated': False,
            'notification_sent': False,
            'metrics_recorded': False
        }
        
        # Critical: Update DynamoDB with retry
        try:
            results['tracking_updated'] = update_tracking_with_retry(
                execution_id=execution_id,
                final_status=final_status,
                summary=summary,
                max_attempts=MAX_RETRY_ATTEMPTS
            )
            logger.info(f"Tracking record updated for {execution_id}")
        except Exception as e:
            logger.critical(f"CRITICAL: Failed to update tracking after retries: {e}")
            # Continue to try notification
        
        # Important: Send SNS notification
        try:
            results['notification_sent'] = publish_sns_notification(
                execution_data=execution_data,
                final_status=final_status,
                summary=summary
            )
            logger.info(f"Notification sent for {execution_id}")
        except Exception as e:
            logger.error(f"Failed to send SNS notification: {e}")
            # Continue to record metrics
        
        # Nice-to-have: Record CloudWatch metrics
        try:
            results['metrics_recorded'] = record_cloudwatch_metrics(
                execution_id=execution_id,
                final_status=final_status,
                summary=summary
            )
            logger.info(f"Metrics recorded for {execution_id}")
        except Exception as e:
            logger.warning(f"Failed to record CloudWatch metrics: {e}")
            # Non-blocking
        
        # Build success response
        response_body = {
            'status': 'success',
            'execution_id': execution_id,
            'final_status': final_status,
            'notification_sent': results['notification_sent'],
            'metrics_recorded': results['metrics_recorded'],
            'tracking_updated': results['tracking_updated'],
            'summary': {
                'total_duration_seconds': summary['duration_seconds'],
                'processing_cost_usd': summary['cost_usd'],
                'documents_generated': summary.get('documents_generated', 0),
                'output_location': summary.get('output_location', '')
            },
            'message': 'Execution finalized successfully'
        }
        
        logger.info(f"Finalization completed for {execution_id}: {json.dumps(results)}")
        return create_response(200, response_body)
        
    except Exception as e:
        logger.error(f"Error finalizing execution: {str(e)}", exc_info=True)
        return create_response(500, {
            'status': 'error',
            'error': 'FinalizationError',
            'message': str(e)
        })


def parse_input_event(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Parse and validate input event from Step Functions
    
    Args:
        event: Lambda event dict
        
    Returns:
        Parsed execution data or None if invalid
    """
    try:
        # Extract required fields
        execution_id = event.get('execution_id')
        if not execution_id:
            logger.error("Missing execution_id in event")
            return None
        
        # Extract status (may be in event or results)
        status = event.get('status', 'UNKNOWN')
        
        # Extract processing results
        processing_results = event.get('processing_results', {})
        
        # Extract timestamps
        timestamps = event.get('timestamps', {})
        
        # Extract metadata
        metadata = event.get('metadata', {})
        video_key = event.get('video_key', '')
        bucket = event.get('bucket', '')
        
        # Extract error info if present
        error = event.get('error', {})
        
        return {
            'execution_id': execution_id,
            'status': status,
            'processing_results': processing_results,
            'timestamps': timestamps,
            'metadata': metadata,
            'video_key': video_key,
            'bucket': bucket,
            'error': error
        }
        
    except (KeyError, TypeError) as e:
        logger.error(f"Failed to parse input event: {e}")
        return None


def determine_final_status(execution_data: Dict[str, Any]) -> str:
    """
    Determine final execution status based on processing results
    
    Priority:
    1. COMPLETED: All stages successful
    2. PARTIAL_SUCCESS: Transcription OK, LLM partial/failed
    3. FAILED: Critical stage failed
    
    Args:
        execution_data: Parsed execution data
        
    Returns:
        Final status string
    """
    processing_results = execution_data.get('processing_results', {})
    
    # Get stage statuses
    transcription_status = processing_results.get('transcription', {}).get('status', 'UNKNOWN')
    llm_status = processing_results.get('llm_processing', {}).get('status', 'UNKNOWN')
    
    # Check for explicit status in event
    event_status = execution_data.get('status', '').upper()
    if event_status in VALID_STATUSES:
        return event_status
    
    # Critical failure: transcription failed
    if transcription_status == 'FAILED':
        logger.warning("Transcription failed - marking as FAILED")
        return 'FAILED'
    
    # Complete success
    if transcription_status == 'COMPLETED' and llm_status == 'COMPLETED':
        return 'COMPLETED'
    
    # Partial success: transcription OK but LLM issues
    if transcription_status == 'COMPLETED' and llm_status in ['PARTIAL', 'FAILED']:
        logger.warning(f"LLM processing {llm_status} - marking as PARTIAL_SUCCESS")
        return 'PARTIAL_SUCCESS'
    
    # Default to FAILED for unknown states
    logger.warning(f"Unknown status combination - defaulting to FAILED")
    return 'FAILED'


def build_execution_summary(execution_data: Dict[str, Any], final_status: str) -> Dict[str, Any]:
    """
    Build comprehensive execution summary with metrics and costs
    
    Args:
        execution_data: Parsed execution data
        final_status: Determined final status
        
    Returns:
        Summary dict with all metrics
    """
    processing_results = execution_data.get('processing_results', {})
    timestamps = execution_data.get('timestamps', {})
    metadata = execution_data.get('metadata', {})
    
    # Calculate duration
    started_at = timestamps.get('started_at', '')
    completed_at = timestamps.get('completed_at', timestamps.get('failed_at', ''))
    
    duration_seconds = 0
    if started_at and completed_at:
        try:
            start = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
            end = datetime.fromisoformat(completed_at.replace('Z', '+00:00'))
            duration_seconds = int((end - start).total_seconds())
        except Exception as e:
            logger.warning(f"Failed to calculate duration: {e}")
    
    # Extract processing metrics
    transcription = processing_results.get('transcription', {})
    llm_processing = processing_results.get('llm_processing', {})
    
    metrics = {
        'transcription_duration_seconds': transcription.get('duration_seconds', 0),
        'llm_processing_seconds': llm_processing.get('processing_time_seconds', 0),
        'total_duration_seconds': duration_seconds,
        'tokens_used': llm_processing.get('tokens_used', 0),
        'document_size_bytes': llm_processing.get('document_size_bytes', 0),
        'speakers_detected': transcription.get('speakers_detected', 0),
        'documents_generated': len(llm_processing.get('documents_generated', []))
    }
    
    # Calculate cost
    cost_usd = calculate_processing_cost(metrics)
    
    # Build summary
    summary = {
        'execution_id': execution_data['execution_id'],
        'final_status': final_status,
        'duration_seconds': duration_seconds,
        'cost_usd': cost_usd,
        'metrics': metrics,
        'completion_time': completed_at or datetime.utcnow().isoformat(),
        'documents_generated': metrics['documents_generated'],
        'output_location': llm_processing.get('output_uri', ''),
        'video_filename': metadata.get('filename', execution_data.get('video_key', '').split('/')[-1])
    }
    
    return summary


def calculate_processing_cost(metrics: Dict[str, Any]) -> float:
    """
    Calculate estimated processing cost
    
    Cost Components:
    - Transcribe: $0.024 per minute
    - Bedrock (Claude Sonnet 4): $0.003/1K input + $0.015/1K output tokens
    - S3: Negligible for short-term storage
    
    Args:
        metrics: Processing metrics dict
        
    Returns:
        Estimated cost in USD
    """
    # Transcribe cost
    video_minutes = metrics.get('transcription_duration_seconds', 0) / 60
    transcribe_cost = video_minutes * 0.024
    
    # Bedrock cost (estimated 67% input, 33% output)
    total_tokens = metrics.get('tokens_used', 0)
    input_tokens = total_tokens * 0.67
    output_tokens = total_tokens * 0.33
    bedrock_cost = (input_tokens / 1000 * 0.003) + (output_tokens / 1000 * 0.015)
    
    # S3 storage cost (negligible)
    document_gb = metrics.get('document_size_bytes', 0) / (1024 ** 3)
    s3_cost = document_gb * 0.023 * (30 / 365)  # 30 days retention
    
    total_cost = transcribe_cost + bedrock_cost + s3_cost
    return round(total_cost, 2)


def update_tracking_with_retry(
    execution_id: str,
    final_status: str,
    summary: Dict[str, Any],
    max_attempts: int = 3
) -> bool:
    """
    Update DynamoDB tracking record with exponential backoff retry
    
    Retry Policy:
    - Attempt 1: Immediate
    - Attempt 2: ~1s delay + jitter
    - Attempt 3: ~2s delay + jitter
    
    Args:
        execution_id: Execution ID
        final_status: Final status
        summary: Execution summary
        max_attempts: Maximum retry attempts
        
    Returns:
        True if successful, False otherwise
    """
    if not TRACKING_TABLE:
        logger.warning("TRACKING_TABLE not configured")
        return False
    
    table = dynamodb.Table(TRACKING_TABLE)
    
    for attempt in range(1, max_attempts + 1):
        try:
            # Convert float to Decimal for DynamoDB
            metrics = {k: Decimal(str(v)) if isinstance(v, float) else v 
                      for k, v in summary['metrics'].items()}
            
            table.update_item(
                Key={'execution_id': execution_id},
                UpdateExpression="""
                    SET #status = :status,
                        #stages.#finalizer = :finalizer_data,
                        updated_at = :timestamp,
                        completion_time = :completion_time,
                        total_duration_seconds = :duration,
                        processing_metrics = :metrics,
                        cost_estimate_usd = :cost
                """,
                ExpressionAttributeNames={
                    '#status': 'status',
                    '#stages': 'processing_stages',
                    '#finalizer': 'finalizer'
                },
                ExpressionAttributeValues={
                    ':status': final_status,
                    ':finalizer_data': {
                        'status': 'completed',
                        'timestamp': datetime.utcnow().isoformat(),
                        'final_status': final_status,
                        'retry_attempts': attempt
                    },
                    ':timestamp': datetime.utcnow().isoformat(),
                    ':completion_time': summary['completion_time'],
                    ':duration': summary['duration_seconds'],
                    ':metrics': metrics,
                    ':cost': Decimal(str(summary['cost_usd']))
                }
            )
            
            logger.info(f"DynamoDB updated successfully on attempt {attempt}")
            return True
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            
            # Don't retry on certain errors
            if error_code in ['ValidationException', 'AccessDeniedException', 'ResourceNotFoundException']:
                logger.error(f"Non-retryable error: {error_code}")
                raise
            
            if attempt == max_attempts:
                logger.error(f"Failed after {max_attempts} attempts: {error_code}")
                raise
            
            # Calculate delay with jitter
            base_delay = RETRY_DELAY_BASE * (2 ** (attempt - 1))
            jitter = random.uniform(0, base_delay * 0.3)
            delay = base_delay + jitter
            
            logger.warning(
                f"Attempt {attempt}/{max_attempts} failed: {error_code}. "
                f"Retrying in {delay:.2f}s"
            )
            time.sleep(delay)
    
    return False


def publish_sns_notification(
    execution_data: Dict[str, Any],
    final_status: str,
    summary: Dict[str, Any]
) -> bool:
    """
    Publish comprehensive SNS notification
    
    Args:
        execution_data: Execution data
        final_status: Final status
        summary: Execution summary
        
    Returns:
        True if successful, False otherwise
    """
    if not NOTIFICATION_TOPIC_ARN:
        logger.warning("NOTIFICATION_TOPIC_ARN not configured")
        return False
    
    try:
        # Build notification based on status
        if final_status == 'COMPLETED':
            subject, message = build_success_notification(execution_data, summary)
        elif final_status == 'PARTIAL_SUCCESS':
            subject, message = build_partial_success_notification(execution_data, summary)
        else:  # FAILED
            subject, message = build_failure_notification(execution_data, summary)
        
        # Publish to SNS
        response = sns_client.publish(
            TopicArn=NOTIFICATION_TOPIC_ARN,
            Subject=subject,
            Message=json.dumps(message, indent=2),
            MessageAttributes={
                'execution_id': {
                    'DataType': 'String',
                    'StringValue': execution_data['execution_id']
                },
                'status': {
                    'DataType': 'String',
                    'StringValue': final_status
                },
                'cost_usd': {
                    'DataType': 'Number',
                    'StringValue': str(summary['cost_usd'])
                },
                'environment': {
                    'DataType': 'String',
                    'StringValue': ENVIRONMENT
                }
            }
        )
        
        logger.info(f"SNS notification published: {response['MessageId']}")
        return True
        
    except ClientError as e:
        logger.error(f"Failed to publish SNS notification: {e}")
        return False


def build_success_notification(
    execution_data: Dict[str, Any],
    summary: Dict[str, Any]
) -> tuple:
    """Build success notification"""
    filename = summary['video_filename']
    processing_results = execution_data.get('processing_results', {})
    transcription = processing_results.get('transcription', {})
    llm_processing = processing_results.get('llm_processing', {})
    
    # Format duration
    duration_minutes = summary['duration_seconds'] // 60
    duration_hours = duration_minutes // 60
    duration_mins = duration_minutes % 60
    duration_str = f"{duration_hours}h {duration_mins}m" if duration_hours > 0 else f"{duration_minutes}m"
    
    subject = f"✅ Video Processing Completed - {filename}"
    
    message = {
        'status': 'COMPLETED',
        'execution_id': execution_data['execution_id'],
        'video': {
            'filename': filename,
            'duration': duration_str,
            'size_mb': execution_data.get('metadata', {}).get('size_mb', 0)
        },
        'processing': {
            'started_at': execution_data.get('timestamps', {}).get('started_at', ''),
            'completed_at': summary['completion_time'],
            'total_duration': duration_str,
            'cost_estimate_usd': summary['cost_usd']
        },
        'results': {
            'transcription': {
                'status': 'Completed',
                'speakers_detected': transcription.get('speakers_detected', 0),
                'transcript_download': transcription.get('transcript_uri', '')
            },
            'documents': {
                'status': 'Generated',
                'types': llm_processing.get('documents_generated', []),
                'total_size_mb': round(llm_processing.get('document_size_bytes', 0) / (1024 * 1024), 2),
                'download_link': llm_processing.get('output_uri', '')
            }
        },
        'metrics': {
            'tokens_processed': llm_processing.get('tokens_used', 0),
            'processing_efficiency': 'High'
        },
        'next_steps': [
            'Review generated documents',
            'Validate content accuracy',
            'Share with stakeholders'
        ]
    }
    
    return subject, message


def build_failure_notification(
    execution_data: Dict[str, Any],
    summary: Dict[str, Any]
) -> tuple:
    """Build failure notification"""
    filename = summary['video_filename']
    error_info = execution_data.get('error', {})
    processing_results = execution_data.get('processing_results', {})
    transcription = processing_results.get('transcription', {})
    
    subject = f"❌ Video Processing Failed - {filename}"
    
    message = {
        'status': 'FAILED',
        'execution_id': execution_data['execution_id'],
        'video': {
            'filename': filename
        },
        'error': {
            'stage': error_info.get('stage', 'unknown'),
            'error_code': error_info.get('error_code', 'UnknownError'),
            'error_message': error_info.get('error_message', 'No details available'),
            'timestamp': error_info.get('timestamp', '')
        },
        'partial_results': {
            'transcription': 'Available' if transcription.get('status') == 'COMPLETED' else 'Failed',
            'transcript_download': transcription.get('transcript_uri', '') if transcription.get('status') == 'COMPLETED' else ''
        },
        'recommended_actions': [
            'Check AWS service quotas and limits',
            'Review CloudWatch logs for detailed error information',
            'Verify IAM permissions are correctly configured',
            'Retry processing after resolving the issue'
        ],
        'support_info': {
            'execution_id': execution_data['execution_id'],
            'cloudwatch_log_group': f'/aws/lambda/ai-techne-academy-{ENVIRONMENT}',
            'environment': ENVIRONMENT
        }
    }
    
    return subject, message


def build_partial_success_notification(
    execution_data: Dict[str, Any],
    summary: Dict[str, Any]
) -> tuple:
    """Build partial success notification"""
    filename = summary['video_filename']
    processing_results = execution_data.get('processing_results', {})
    llm_processing = processing_results.get('llm_processing', {})
    
    subject = f"⚠️ Video Processing Partial Success - {filename}"
    
    message = {
        'status': 'PARTIAL_SUCCESS',
        'execution_id': execution_data['execution_id'],
        'summary': 'Transcription completed successfully, but some documents failed to generate',
        'completed': {
            'transcription': '✅ Success',
            'documents': llm_processing.get('documents_generated', [])
        },
        'failed': {
            'documents': llm_processing.get('failed_documents', [])
        },
        'available_downloads': {
            'transcript': processing_results.get('transcription', {}).get('transcript_uri', ''),
            'documents': llm_processing.get('output_uri', '')
        },
        'next_steps': [
            'Review available documents',
            'Check error logs for failed components',
            'Consider re-running failed stages'
        ]
    }
    
    return subject, message


def record_cloudwatch_metrics(
    execution_id: str,
    final_status: str,
    summary: Dict[str, Any]
) -> bool:
    """
    Record custom CloudWatch metrics
    
    Args:
        execution_id: Execution ID
        final_status: Final status
        summary: Execution summary
        
    Returns:
        True if successful, False otherwise
    """
    try:
        metrics = summary['metrics']
        
        metric_data = [
            {
                'MetricName': 'ProcessingDuration',
                'Unit': 'Seconds',
                'Value': summary['duration_seconds'],
                'Dimensions': [
                    {'Name': 'Environment', 'Value': ENVIRONMENT},
                    {'Name': 'Status', 'Value': final_status}
                ]
            },
            {
                'MetricName': 'ProcessingSuccess',
                'Unit': 'Count',
                'Value': 1 if final_status == 'COMPLETED' else 0,
                'Dimensions': [{'Name': 'Environment', 'Value': ENVIRONMENT}]
            },
            {
                'MetricName': 'ProcessingFailure',
                'Unit': 'Count',
                'Value': 1 if final_status == 'FAILED' else 0,
                'Dimensions': [{'Name': 'Environment', 'Value': ENVIRONMENT}]
            },
            {
                'MetricName': 'PartialSuccess',
                'Unit': 'Count',
                'Value': 1 if final_status == 'PARTIAL_SUCCESS' else 0,
                'Dimensions': [{'Name': 'Environment', 'Value': ENVIRONMENT}]
            },
            {
                'MetricName': 'TokensProcessed',
                'Unit': 'Count',
                'Value': metrics.get('tokens_used', 0),
                'Dimensions': [{'Name': 'Environment', 'Value': ENVIRONMENT}]
            },
            {
                'MetricName': 'DocumentSize',
                'Unit': 'Bytes',
                'Value': metrics.get('document_size_bytes', 0),
                'Dimensions': [
                    {'Name': 'Environment', 'Value': ENVIRONMENT},
                    {'Name': 'Status', 'Value': final_status}
                ]
            },
            {
                'MetricName': 'ProcessingCost',
                'Unit': 'None',  # USD
                'Value': summary['cost_usd'],
                'Dimensions': [{'Name': 'Environment', 'Value': ENVIRONMENT}]
            },
            {
                'MetricName': 'SpeakersDetected',
                'Unit': 'Count',
                'Value': metrics.get('speakers_detected', 0),
                'Dimensions': [{'Name': 'Environment', 'Value': ENVIRONMENT}]
            }
        ]
        
        # Send metrics in batch
        cloudwatch.put_metric_data(
            Namespace='AITechneAcademy',
            MetricData=metric_data
        )
        
        logger.info(f"Recorded {len(metric_data)} CloudWatch metrics")
        return True
        
    except ClientError as e:
        logger.warning(f"Failed to record CloudWatch metrics: {e}")
        return False


def create_response(status_code: int, body: Any) -> Dict[str, Any]:
    """
    Create Lambda response
    
    Args:
        status_code: HTTP status code
        body: Response body (dict or string)
        
    Returns:
        Formatted response dict
    """
    if isinstance(body, dict):
        body_str = json.dumps(body, default=str)
    else:
        body_str = str(body)
    
    return {
        'statusCode': status_code,
        'body': body_str,
        'headers': {
            'Content-Type': 'application/json'
        }
    }