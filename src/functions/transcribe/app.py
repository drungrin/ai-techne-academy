"""
Lambda Transcribe Starter Function
Starts AWS Transcribe jobs for video processing with speaker identification
"""
import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from urllib.parse import urlparse
import re

import boto3
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))

# AWS clients
transcribe_client = boto3.client('transcribe')
dynamodb = boto3.resource('dynamodb')

# Environment variables
TRACKING_TABLE = os.getenv('TRACKING_TABLE')
OUTPUT_BUCKET = os.getenv('OUTPUT_BUCKET')
LANGUAGE_CODE = os.getenv('LANGUAGE_CODE', 'pt-BR')
MAX_SPEAKERS = int(os.getenv('MAX_SPEAKERS', '10'))
ENVIRONMENT = os.getenv('ENVIRONMENT', 'dev')

# Media format mapping
MEDIA_FORMAT_MAP = {
    '.mp4': 'mp4',
    '.mp3': 'mp3',
    '.wav': 'wav',
    '.flac': 'flac',
    '.ogg': 'ogg',
    '.webm': 'webm',
    '.amr': 'amr',
    '.m4a': 'mp4',
    '.m4v': 'mp4'
}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for starting AWS Transcribe jobs
    
    Args:
        event: Input event with execution details
        context: Lambda context
        
    Returns:
        Response dict with job details
    """
    logger.info(f"Received event: {json.dumps(event)}")
    
    try:
        # Parse input event
        input_data = parse_input_event(event)
        if not input_data:
            return create_response(400, "Invalid input format")
        
        execution_id = input_data['execution_id']
        s3_uri = input_data['s3_uri']
        language_code = input_data.get('language_code', LANGUAGE_CODE)
        max_speakers = input_data.get('max_speakers', MAX_SPEAKERS)
        
        logger.info(f"Processing execution {execution_id} for {s3_uri}")
        
        # Validate S3 URI
        if not validate_s3_uri(s3_uri):
            return create_response(400, f"Invalid S3 URI: {s3_uri}")
        
        # Extract bucket and key from S3 URI
        bucket, key = parse_s3_uri(s3_uri)
        
        # Determine media format
        media_format = get_media_format(key)
        if not media_format:
            return create_response(400, f"Unsupported media format for: {key}")
        
        # Generate job name
        job_name = generate_job_name(execution_id)
        
        # Build output location
        output_key = f"{execution_id}/"
        
        # Start transcription job
        job_details = start_transcription_job(
            job_name=job_name,
            media_uri=s3_uri,
            media_format=media_format,
            language_code=language_code,
            max_speakers=max_speakers,
            output_bucket=OUTPUT_BUCKET,
            output_key=output_key
        )
        
        if not job_details:
            return create_response(500, "Failed to start transcription job")
        
        # Update DynamoDB tracking
        update_success = update_tracking_record(
            execution_id=execution_id,
            job_name=job_name,
            job_details=job_details
        )
        
        if not update_success:
            logger.warning(f"Failed to update tracking record for {execution_id}")
            # Don't fail the Lambda - job was started successfully
        
        # Success response
        response_body = {
            'status': 'success',
            'execution_id': execution_id,
            'transcription_job': {
                'job_name': job_name,
                'job_status': job_details['job_status'],
                'language_code': language_code,
                'media_uri': s3_uri,
                'output_location': f"s3://{OUTPUT_BUCKET}/{output_key}transcript.json",
                'created_at': job_details['created_at']
            },
            'message': 'Transcription job started successfully'
        }
        
        logger.info(f"Successfully started transcription job {job_name}")
        return create_response(200, response_body)
        
    except Exception as e:
        logger.error(f"Error processing event: {str(e)}", exc_info=True)
        return create_response(500, f"Internal error: {str(e)}")


def parse_input_event(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Parse input event from Step Functions or direct invocation
    
    Args:
        event: Lambda event dict
        
    Returns:
        Dict with parsed data or None if invalid
    """
    try:
        # Direct invocation with s3_uri
        if 'execution_id' in event and 's3_uri' in event:
            return {
                'execution_id': event['execution_id'],
                's3_uri': event['s3_uri'],
                'language_code': event.get('language_code'),
                'max_speakers': event.get('max_speakers')
            }
        
        # Step Functions format
        if 'execution_id' in event and 'bucket' in event and 'video_key' in event:
            bucket = event['bucket']
            key = event['video_key']
            s3_uri = f"s3://{bucket}/{key}"
            
            return {
                'execution_id': event['execution_id'],
                's3_uri': s3_uri,
                'language_code': event.get('language_code'),
                'max_speakers': event.get('max_speakers')
            }
        
        # Alternative Step Functions format with metadata
        if 'execution_id' in event and 'metadata' in event:
            metadata = event['metadata']
            if 's3_uri' in metadata:
                return {
                    'execution_id': event['execution_id'],
                    's3_uri': metadata['s3_uri'],
                    'language_code': event.get('language_code'),
                    'max_speakers': event.get('max_speakers')
                }
        
        logger.error(f"Unable to parse event format: {event}")
        return None
        
    except (KeyError, TypeError) as e:
        logger.error(f"Failed to parse input event: {e}")
        return None


def validate_s3_uri(s3_uri: str) -> bool:
    """
    Validate S3 URI format
    
    Args:
        s3_uri: S3 URI string
        
    Returns:
        True if valid, False otherwise
    """
    pattern = r'^s3://[a-z0-9\-\.]+/.+$'
    return bool(re.match(pattern, s3_uri))


def parse_s3_uri(s3_uri: str) -> tuple:
    """
    Parse S3 URI into bucket and key
    
    Args:
        s3_uri: S3 URI string (s3://bucket/key)
        
    Returns:
        Tuple of (bucket, key)
    """
    parsed = urlparse(s3_uri)
    bucket = parsed.netloc
    key = parsed.path.lstrip('/')
    return bucket, key


def get_media_format(key: str) -> Optional[str]:
    """
    Determine media format from file extension
    
    Args:
        key: S3 object key (filename)
        
    Returns:
        Media format string or None
    """
    extension = os.path.splitext(key.lower())[1]
    return MEDIA_FORMAT_MAP.get(extension)


def generate_job_name(execution_id: str) -> str:
    """
    Generate unique job name for Transcribe job
    
    Args:
        execution_id: Execution ID
        
    Returns:
        Job name string
    """
    # Transcribe job names must be alphanumeric, hyphens, and underscores only
    # Remove any invalid characters from execution_id
    clean_id = re.sub(r'[^a-zA-Z0-9\-_]', '-', execution_id)
    return f"transcribe-{clean_id}"


def start_transcription_job(
    job_name: str,
    media_uri: str,
    media_format: str,
    language_code: str,
    max_speakers: int,
    output_bucket: str,
    output_key: str
) -> Optional[Dict[str, Any]]:
    """
    Start AWS Transcribe job
    
    Args:
        job_name: Unique job name
        media_uri: S3 URI of media file
        media_format: Media format (mp4, mp3, etc.)
        language_code: Language code (pt-BR, en-US, etc.)
        max_speakers: Maximum number of speakers
        output_bucket: S3 bucket for output
        output_key: S3 key prefix for output
        
    Returns:
        Dict with job details or None
    """
    try:
        response = transcribe_client.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={
                'MediaFileUri': media_uri
            },
            MediaFormat=media_format,
            LanguageCode=language_code,
            OutputBucketName=output_bucket,
            OutputKey=output_key,
            Settings={
                'ShowSpeakerLabels': True,
                'MaxSpeakerLabels': max_speakers,
                'ChannelIdentification': False
            },
            Tags=[
                {'Key': 'Environment', 'Value': ENVIRONMENT},
                {'Key': 'Project', 'Value': 'ai-techne-academy'},
                {'Key': 'JobName', 'Value': job_name}
            ]
        )
        
        job = response['TranscriptionJob']
        
        return {
            'job_name': job['TranscriptionJobName'],
            'job_status': job['TranscriptionJobStatus'],
            'language_code': job['LanguageCode'],
            'media_format': job['MediaFormat'],
            'created_at': job['CreationTime'].isoformat()
        }
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        
        if error_code == 'ConflictException':
            logger.warning(f"Job already exists: {job_name}")
            # Try to get existing job details
            try:
                existing_job = transcribe_client.get_transcription_job(
                    TranscriptionJobName=job_name
                )
                job = existing_job['TranscriptionJob']
                return {
                    'job_name': job['TranscriptionJobName'],
                    'job_status': job['TranscriptionJobStatus'],
                    'language_code': job['LanguageCode'],
                    'media_format': job['MediaFormat'],
                    'created_at': job['CreationTime'].isoformat()
                }
            except ClientError as get_error:
                logger.error(f"Failed to get existing job: {get_error}")
                return None
                
        elif error_code == 'LimitExceededException':
            logger.error(f"Transcribe quota exceeded: {error_message}")
            raise
            
        elif error_code == 'BadRequestException':
            logger.error(f"Invalid transcribe request: {error_message}")
            return None
            
        else:
            logger.error(f"Transcribe error ({error_code}): {error_message}")
            return None


def update_tracking_record(
    execution_id: str,
    job_name: str,
    job_details: Dict[str, Any]
) -> bool:
    """
    Update DynamoDB tracking record with transcription job details
    
    Args:
        execution_id: Execution ID
        job_name: Transcribe job name
        job_details: Job details from start_transcription_job
        
    Returns:
        True if successful, False otherwise
    """
    if not TRACKING_TABLE:
        logger.warning("TRACKING_TABLE not configured, skipping tracking update")
        return True
    
    try:
        table = dynamodb.Table(TRACKING_TABLE)
        
        timestamp = datetime.utcnow().isoformat()
        
        response = table.update_item(
            Key={'execution_id': execution_id},
            UpdateExpression="""
                SET 
                    processing_stages.transcribe_starter = :stage_data,
                    updated_at = :timestamp,
                    #status = :status
            """,
            ExpressionAttributeNames={
                '#status': 'status'
            },
            ExpressionAttributeValues={
                ':stage_data': {
                    'status': 'in_progress',
                    'job_name': job_name,
                    'job_status': job_details['job_status'],
                    'timestamp': timestamp,
                    'language_code': job_details['language_code'],
                    'media_format': job_details['media_format'],
                    'created_at': job_details['created_at']
                },
                ':timestamp': timestamp,
                ':status': 'TRANSCRIBING'
            },
            ConditionExpression='attribute_exists(execution_id)',
            ReturnValues='UPDATED_NEW'
        )
        
        logger.info(f"Updated tracking record for execution {execution_id}")
        return True
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        
        if error_code == 'ConditionalCheckFailedException':
            logger.error(f"Tracking record not found for execution {execution_id}")
        else:
            logger.error(f"Failed to update tracking record: {e}")
        
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
        body_str = json.dumps(body)
    else:
        body_str = str(body)
    
    return {
        'statusCode': status_code,
        'body': body_str,
        'headers': {
            'Content-Type': 'application/json'
        }
    }