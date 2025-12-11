"""
Lambda Trigger Function
Responds to S3 upload events and initiates video processing workflow
"""
import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Union
from urllib.parse import unquote_plus
from decimal import Decimal
import uuid

import boto3
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))

# AWS clients
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
sfn_client = boto3.client('stepfunctions')

# Environment variables
TRACKING_TABLE = os.getenv('TRACKING_TABLE')
STATE_MACHINE_ARN = os.getenv('STATE_MACHINE_ARN')
ENVIRONMENT = os.getenv('ENVIRONMENT', 'dev')

# Supported video formats
SUPPORTED_FORMATS = {
    '.mp4': 'video/mp4',
    '.mov': 'video/quicktime',
    '.avi': 'video/x-msvideo',
    '.mkv': 'video/x-matroska',
    '.webm': 'video/webm',
    '.flv': 'video/x-flv',
    '.m4v': 'video/x-m4v'
}

# Maximum file size (5 GB in bytes)
MAX_FILE_SIZE = 5 * 1024 * 1024 * 1024


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for S3 upload events
    
    Args:
        event: S3 event notification
        context: Lambda context
        
    Returns:
        Response dict with execution details
    """
    logger.info(f"Received event: {json.dumps(event)}")
    
    try:
        # Parse S3 event
        s3_event = parse_s3_event(event)
        if not s3_event:
            return create_response(400, "Invalid S3 event format")
        
        bucket = s3_event['bucket']
        key = s3_event['key']
        
        logger.info(f"Processing upload: s3://{bucket}/{key}")
        
        # Get object metadata
        metadata = get_object_metadata(bucket, key)
        if not metadata:
            return create_response(500, "Failed to retrieve object metadata")
        
        # Validate file
        validation_result = validate_video_file(key, metadata['size'])
        if not validation_result['valid']:
            logger.warning(f"Validation failed: {validation_result['reason']}")
            return create_response(400, validation_result['reason'])
        
        # Generate execution ID
        execution_id = str(uuid.uuid4())
        
        # Extract video metadata
        video_metadata = extract_video_metadata(bucket, key, metadata)
        
        # Create initial tracking record
        tracking_record = create_tracking_record(
            execution_id=execution_id,
            video_key=f"s3://{bucket}/{key}",
            metadata=video_metadata
        )
        
        if not tracking_record:
            return create_response(500, "Failed to create tracking record")
        
        # Start Step Functions execution (if State Machine ARN is configured)
        if STATE_MACHINE_ARN:
            sfn_execution = start_step_function_execution(
                execution_id=execution_id,
                video_key=key,
                bucket=bucket,
                metadata=video_metadata
            )
            
            if not sfn_execution:
                logger.warning("Failed to start Step Functions execution")
                # Don't fail the Lambda - record is already created
        else:
            logger.info("STATE_MACHINE_ARN not configured, skipping Step Functions execution")
        
        # Success response
        response_body = {
            'status': 'success',
            'execution_id': execution_id,
            'video_key': key,
            'bucket': bucket,
            'metadata': video_metadata,
            'message': 'Video processing initiated successfully'
        }
        
        logger.info(f"Successfully initiated processing for execution {execution_id}")
        return create_response(200, response_body)
        
    except Exception as e:
        logger.error(f"Error processing event: {str(e)}", exc_info=True)
        return create_response(500, f"Internal error: {str(e)}")


def parse_s3_event(event: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """
    Parse S3 event notification
    
    Args:
        event: Lambda event dict
        
    Returns:
        Dict with bucket and key, or None if invalid
    """
    try:
        # Handle S3 event notification
        if 'Records' in event and len(event['Records']) > 0:
            record = event['Records'][0]
            
            # Direct S3 event
            if 's3' in record:
                bucket = record['s3']['bucket']['name']
                key = unquote_plus(record['s3']['object']['key'])
                return {'bucket': bucket, 'key': key}
            
            # EventBridge event
            if 'detail' in event:
                detail = event['detail']
                bucket = detail['bucket']['name']
                key = unquote_plus(detail['object']['key'])
                return {'bucket': bucket, 'key': key}
        
        # EventBridge format
        if 'detail' in event:
            detail = event['detail']
            bucket = detail['bucket']['name']
            key = unquote_plus(detail['object']['key'])
            return {'bucket': bucket, 'key': key}
        
        return None
        
    except (KeyError, IndexError) as e:
        logger.error(f"Failed to parse S3 event: {e}")
        return None


def get_object_metadata(bucket: str, key: str) -> Optional[Dict[str, Any]]:
    """
    Get S3 object metadata
    
    Args:
        bucket: S3 bucket name
        key: S3 object key
        
    Returns:
        Metadata dict or None
    """
    try:
        response = s3_client.head_object(Bucket=bucket, Key=key)
        
        return {
            'size': response['ContentLength'],
            'content_type': response.get('ContentType', 'unknown'),
            'last_modified': response['LastModified'].isoformat(),
            'etag': response['ETag'].strip('"'),
            'metadata': response.get('Metadata', {})
        }
        
    except ClientError as e:
        logger.error(f"Failed to get object metadata: {e}")
        return None


def validate_video_file(key: str, size: int) -> Dict[str, Any]:
    """
    Validate video file format and size
    
    Args:
        key: S3 object key (filename)
        size: File size in bytes
        
    Returns:
        Dict with 'valid' boolean and optional 'reason'
    """
    # Extract file extension
    extension = os.path.splitext(key.lower())[1]
    
    # Check format
    if extension not in SUPPORTED_FORMATS:
        return {
            'valid': False,
            'reason': f"Unsupported file format: {extension}. Supported formats: {', '.join(SUPPORTED_FORMATS.keys())}"
        }
    
    # Check size
    if size > MAX_FILE_SIZE:
        size_gb = size / (1024 * 1024 * 1024)
        max_gb = MAX_FILE_SIZE / (1024 * 1024 * 1024)
        return {
            'valid': False,
            'reason': f"File too large: {size_gb:.2f} GB. Maximum size: {max_gb} GB"
        }
    
    if size == 0:
        return {
            'valid': False,
            'reason': "File is empty"
        }
    
    return {'valid': True}


def extract_video_metadata(bucket: str, key: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract video metadata for processing
    
    Args:
        bucket: S3 bucket name
        key: S3 object key
        metadata: S3 object metadata
        
    Returns:
        Formatted metadata dict
    """
    filename = os.path.basename(key)
    extension = os.path.splitext(key.lower())[1]
    
    return {
        'filename': filename,
        'extension': extension,
        'mime_type': SUPPORTED_FORMATS.get(extension, 'unknown'),
        'size_bytes': metadata['size'],
        'size_mb': Decimal(str(round(metadata['size'] / (1024 * 1024), 2))),
        'bucket': bucket,
        'key': key,
        's3_uri': f"s3://{bucket}/{key}",
        'etag': metadata['etag'],
        'uploaded_at': metadata['last_modified']
    }


def create_tracking_record(
    execution_id: str,
    video_key: str,
    metadata: Dict[str, Any]
) -> bool:
    """
    Create initial tracking record in DynamoDB
    
    Args:
        execution_id: Unique execution ID
        video_key: S3 URI of video
        metadata: Video metadata
        
    Returns:
        True if successful, False otherwise
    """
    if not TRACKING_TABLE:
        logger.warning("TRACKING_TABLE not configured, skipping tracking record")
        return True
    
    try:
        table = dynamodb.Table(TRACKING_TABLE)
        
        item = {
            'execution_id': execution_id,
            'video_key': video_key,
            'status': 'STARTED',
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat(),
            'environment': ENVIRONMENT,
            'video_metadata': metadata,
            'processing_stages': {
                'trigger': {
                    'status': 'completed',
                    'timestamp': datetime.utcnow().isoformat()
                }
            }
        }
        
        table.put_item(Item=item)
        logger.info(f"Created tracking record for execution {execution_id}")
        return True
        
    except ClientError as e:
        logger.error(f"Failed to create tracking record: {e}")
        return False


def start_step_function_execution(
    execution_id: str,
    video_key: str,
    bucket: str,
    metadata: Dict[str, Any]
) -> Optional[str]:
    """
    Start Step Functions execution
    
    Args:
        execution_id: Execution ID
        video_key: S3 object key
        bucket: S3 bucket name
        metadata: Video metadata
        
    Returns:
        Execution ARN or None
    """
    try:
        # Convert Decimal to float for JSON serialization
        metadata_for_sfn = metadata.copy()
        if 'size_mb' in metadata_for_sfn and isinstance(metadata_for_sfn['size_mb'], Decimal):
            metadata_for_sfn['size_mb'] = float(metadata_for_sfn['size_mb'])
        
        input_data = {
            'execution_id': execution_id,
            'video_key': video_key,
            'bucket': bucket,
            'metadata': metadata_for_sfn,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        response = sfn_client.start_execution(
            stateMachineArn=STATE_MACHINE_ARN,
            name=execution_id,
            input=json.dumps(input_data)
        )
        
        execution_arn = response['executionArn']
        logger.info(f"Started Step Functions execution: {execution_arn}")
        return execution_arn
        
    except ClientError as e:
        logger.error(f"Failed to start Step Functions execution: {e}")
        return None


def convert_decimals(obj: Any) -> Any:
    """
    Recursively convert Decimal types to float/int for JSON serialization
    
    Args:
        obj: Object that may contain Decimals
        
    Returns:
        Object with Decimals converted to float/int
    """
    if isinstance(obj, Decimal):
        # Convert to int if it's a whole number, otherwise float
        return int(obj) if obj % 1 == 0 else float(obj)
    elif isinstance(obj, dict):
        return {key: convert_decimals(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals(item) for item in obj]
    else:
        return obj


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
        # Convert Decimals before JSON serialization
        body = convert_decimals(body)
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