"""
ECS Processor Main Entry Point

This is the main entry point for the ECS Fargate task that processes
video transcriptions and generates technical training documents.

Author: AI Techne Academy
Version: 1.0.0
"""

import os
import json
import logging
import sys
from typing import Dict, Any, Optional
from datetime import datetime
import boto3
from botocore.exceptions import ClientError

from transcription_parser import TranscriptionParser
from llm_client import BedrockLLMClient
from document_generator import DocumentGenerator

# Configure logging
logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)


class ProcessorError(Exception):
    """Base exception for processor errors."""
    pass


class ConfigurationError(ProcessorError):
    """Configuration or environment error."""
    pass


class ProcessingError(ProcessorError):
    """Error during document processing."""
    pass


def load_config() -> Dict[str, str]:
    """
    Load configuration from environment variables.
    
    Required environment variables:
    - TRACKING_TABLE: DynamoDB table name
    - OUTPUT_BUCKET: S3 bucket for outputs
    - AWS_REGION: AWS region (default: us-east-1)
    - BEDROCK_MODEL_ID: Bedrock model identifier
    
    Optional:
    - LOG_LEVEL: Logging level (default: INFO)
    - MAX_TOKENS_PER_CHUNK: Maximum tokens per chunk (default: 100000)
    
    Returns:
        Configuration dictionary
        
    Raises:
        ConfigurationError: If required variables are missing
    """
    required_vars = ['TRACKING_TABLE', 'OUTPUT_BUCKET']
    config = {}
    
    for var in required_vars:
        value = os.environ.get(var)
        if not value:
            raise ConfigurationError(f"Missing required environment variable: {var}")
        config[var] = value
    
    # Optional with defaults
    config['AWS_REGION'] = os.environ.get('AWS_REGION', 'us-east-1')
    config['BEDROCK_MODEL_ID'] = os.environ.get(
        'BEDROCK_MODEL_ID',
        'anthropic.claude-sonnet-4-5-20250929-v1:0'
    )
    config['LOG_LEVEL'] = os.environ.get('LOG_LEVEL', 'INFO')
    config['MAX_TOKENS_PER_CHUNK'] = int(
        os.environ.get('MAX_TOKENS_PER_CHUNK', '100000')
    )
    
    logger.info(f"Configuration loaded: {list(config.keys())}")
    return config


def validate_event(event: Dict[str, Any]) -> None:
    """
    Validate input event structure.
    
    Required fields:
    - execution_id
    - transcription_s3_uri
    - video_s3_uri (for tracking)
    
    Args:
        event: Input event dictionary
        
    Raises:
        ConfigurationError: If event is invalid
    """
    required_fields = ['execution_id', 'transcription_s3_uri', 'video_s3_uri']
    
    for field in required_fields:
        if field not in event:
            raise ConfigurationError(f"Missing required event field: {field}")
    
    logger.info(f"Event validated: execution_id={event['execution_id']}")


def update_dynamodb_status(
    dynamodb: Any,
    table_name: str,
    execution_id: str,
    status: str,
    data: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None
) -> None:
    """
    Update processing status in DynamoDB.
    
    Args:
        dynamodb: boto3 DynamoDB resource
        table_name: Table name
        execution_id: Execution identifier
        status: Status (PROCESSING, COMPLETED, FAILED)
        data: Additional data to store
        error: Error message if failed
    """
    table = dynamodb.Table(table_name)
    
    update_expression = "SET #status = :status, updated_at = :updated_at"
    expression_values = {
        ':status': status,
        ':updated_at': datetime.now(timezone.utc).isoformat()
    }
    expression_names = {'#status': 'status'}
    
    # Add processing stage info
    if data:
        update_expression += ", processing_stages.processor = :processor_data"
        expression_values[':processor_data'] = {
            'status': status,
            'updated_at': datetime.now(timezone.utc).isoformat(),
        }
    
    # Add error if present
    if error:
        update_expression += ", error = :error"
        expression_values[':error'] = error
    
    try:
        table.update_item(
            Key={'execution_id': execution_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values,
            ExpressionAttributeNames=expression_names
        )
        logger.info(f"DynamoDB updated: {execution_id} -> {status}")
    except ClientError as e:
        logger.error(f"Failed to update DynamoDB: {str(e)}")
        # Don't raise - this is non-critical


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main handler for ECS task.
    
    Event format (from Step Functions):
    {
        "execution_id": "uuid",
        "video_s3_uri": "s3://bucket/video.mp4",
        "transcription_s3_uri": "s3://bucket/transcription.json",
        "video_metadata": {...}
    }
    
    Returns:
        {
            "statusCode": 200,
            "body": {
                "execution_id": "uuid",
                "markdown_s3_uri": "s3://...",
                "docx_s3_uri": "s3://...",
                "tokens_used": {...},
                "cost_usd": 0.57,
                "duration_seconds": 185,
                "chunks_processed": 1
            }
        }
    
    Raises:
        ProcessorError: If processing fails
    """
    logger.info("=" * 80)
    logger.info("ECS Processor Started")
    logger.info("=" * 80)
    
    start_time = datetime.now()
    
    try:
        # 1. Load configuration
        logger.info("Step 1: Loading configuration")
        config = load_config()
        
        # 2. Validate event
        logger.info("Step 2: Validating event")
        validate_event(event)
        
        execution_id = event['execution_id']
        transcription_uri = event['transcription_s3_uri']
        output_bucket = config['OUTPUT_BUCKET']
        
        logger.info(f"Processing execution: {execution_id}")
        logger.info(f"Transcription URI: {transcription_uri}")
        logger.info(f"Output bucket: {output_bucket}")
        
        # 3. Initialize AWS clients
        logger.info("Step 3: Initializing AWS clients")
        region = config['AWS_REGION']
        s3_client = boto3.client('s3', region_name=region)
        dynamodb = boto3.resource('dynamodb', region_name=region)
        
        # 4. Update DynamoDB: PROCESSING
        logger.info("Step 4: Updating DynamoDB status -> PROCESSING")
        update_dynamodb_status(
            dynamodb=dynamodb,
            table_name=config['TRACKING_TABLE'],
            execution_id=execution_id,
            status='PROCESSING',
            data={
                'started_at': datetime.now(timezone.utc).isoformat(),
                'processor_version': '1.0.0'
            }
        )
        
        # 5. Initialize processing components
        logger.info("Step 5: Initializing processing components")
        
        parser = TranscriptionParser(
            max_tokens_per_chunk=config['MAX_TOKENS_PER_CHUNK']
        )
        
        llm_client = BedrockLLMClient(
            model_id=config['BEDROCK_MODEL_ID'],
            region=region,
            temperature=0.7,
            max_tokens=4096,
            enable_rate_limiting=True,
            max_retries=3
        )
        
        generator = DocumentGenerator(
            llm_client=llm_client,
            parser=parser,
            s3_client=s3_client
        )
        
        logger.info("Components initialized successfully")
        
        # 6. Generate document (main processing)
        logger.info("Step 6: Starting document generation pipeline")
        logger.info("-" * 80)
        
        result = generator.generate_document(
            execution_id=execution_id,
            transcription_s3_uri=transcription_uri,
            output_bucket=output_bucket
        )
        
        logger.info("-" * 80)
        logger.info("Document generation completed successfully")
        
        # 7. Update DynamoDB: COMPLETED
        logger.info("Step 7: Updating DynamoDB status -> COMPLETED")
        update_dynamodb_status(
            dynamodb=dynamodb,
            table_name=config['TRACKING_TABLE'],
            execution_id=execution_id,
            status='COMPLETED',
            data={
                'completed_at': datetime.now(timezone.utc).isoformat(),
                'markdown_s3_uri': result.markdown_s3_uri,
                'docx_s3_uri': result.docx_s3_uri,
                'tokens_used': {
                    'input': result.total_tokens.input_tokens,
                    'output': result.total_tokens.output_tokens,
                    'total': result.total_tokens.total_tokens
                },
                'cost_usd': result.total_cost_usd,
                'duration_seconds': result.duration_seconds,
                'chunks_processed': result.chunks_processed,
                'stage_count': len(result.stages)
            }
        )
        
        # 8. Prepare response
        total_duration = (datetime.now() - start_time).total_seconds()
        
        response_body = {
            'execution_id': execution_id,
            'markdown_s3_uri': result.markdown_s3_uri,
            'docx_s3_uri': result.docx_s3_uri,
            'tokens_used': {
                'input': result.total_tokens.input_tokens,
                'output': result.total_tokens.output_tokens,
                'total': result.total_tokens.total_tokens
            },
            'cost_usd': result.total_cost_usd,
            'duration_seconds': total_duration,
            'chunks_processed': result.chunks_processed,
            'stages_completed': len(result.stages)
        }
        
        logger.info("=" * 80)
        logger.info("ECS Processor Completed Successfully")
        logger.info(f"Duration: {total_duration:.2f}s")
        logger.info(f"Cost: ${result.total_cost_usd:.4f}")
        logger.info(f"Tokens: {result.total_tokens.total_tokens}")
        logger.info("=" * 80)
        
        return {
            'statusCode': 200,
            'body': response_body
        }
        
    except ConfigurationError as e:
        error_msg = f"Configuration error: {str(e)}"
        logger.error(error_msg)
        
        return {
            'statusCode': 400,
            'body': {
                'error': 'ConfigurationError',
                'message': error_msg
            }
        }
        
    except ProcessingError as e:
        error_msg = f"Processing error: {str(e)}"
        logger.error(error_msg)
        
        # Try to update DynamoDB
        try:
            execution_id = event.get('execution_id')
            if execution_id:
                update_dynamodb_status(
                    dynamodb=boto3.resource('dynamodb', region_name=config.get('AWS_REGION', 'us-east-1')),
                    table_name=config.get('TRACKING_TABLE', ''),
                    execution_id=execution_id,
                    status='FAILED',
                    error=error_msg
                )
        except Exception as update_error:
            logger.error(f"Failed to update DynamoDB with error: {update_error}")
        
        return {
            'statusCode': 500,
            'body': {
                'error': 'ProcessingError',
                'message': error_msg
            }
        }
        
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.exception(error_msg)
        
        # Try to update DynamoDB
        try:
            execution_id = event.get('execution_id')
            if execution_id and 'config' in locals():
                update_dynamodb_status(
                    dynamodb=boto3.resource('dynamodb', region_name=config.get('AWS_REGION', 'us-east-1')),
                    table_name=config.get('TRACKING_TABLE', ''),
                    execution_id=execution_id,
                    status='FAILED',
                    error=error_msg
                )
        except Exception as update_error:
            logger.error(f"Failed to update DynamoDB with error: {update_error}")
        
        return {
            'statusCode': 500,
            'body': {
                'error': 'InternalError',
                'message': error_msg
            }
        }


def main():
    """
    CLI entry point for local testing.
    
    Usage:
        python main.py '{"execution_id": "test-123", ...}'
    """
    if len(sys.argv) < 2:
        print("Usage: python main.py '<json_event>'")
        print("\nExample:")
        print('  python main.py \'{"execution_id": "test-123", '
              '"transcription_s3_uri": "s3://bucket/file.json", '
              '"video_s3_uri": "s3://bucket/video.mp4"}\'')
        sys.exit(1)
    
    try:
        event = json.loads(sys.argv[1])
        result = lambda_handler(event, None)
        print("\n" + "=" * 80)
        print("RESULT:")
        print(json.dumps(result, indent=2))
        print("=" * 80)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
