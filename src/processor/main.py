"""
ECS Processor Main Entry Point

This is the main entry point for the ECS Fargate task that processes
video transcriptions and generates technical training documents.

The processor reads all configuration from environment variables and
runs as a standalone CLI application in the ECS container.

Required Environment Variables:
- EXECUTION_ID: Unique execution identifier
- VIDEO_S3_URI: S3 URI of the video file
- TRANSCRIPTION_S3_URI: S3 URI of the transcription JSON file
- TRACKING_TABLE: DynamoDB table name
- OUTPUT_BUCKET: S3 bucket for outputs

Optional Environment Variables:
- AWS_REGION: AWS region (default: us-east-1)
- BEDROCK_MODEL_ID: Bedrock model identifier
- LOG_LEVEL: Logging level (default: INFO)
- MAX_TOKENS_PER_CHUNK: Maximum tokens per chunk (default: 100000)

Usage:
    python main.py

Author: AI Techne Academy
Version: 2.0.0
"""

import os
import json
import logging
import sys
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from decimal import Decimal
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
    - EXECUTION_ID: Unique execution identifier
    - VIDEO_S3_URI: S3 URI of the video file (for tracking)
    - TRANSCRIPTION_S3_URI: S3 URI of the transcription JSON file
    - TRACKING_TABLE: DynamoDB table name
    - OUTPUT_BUCKET: S3 bucket for outputs
    
    Optional:
    - AWS_REGION: AWS region (default: us-east-1)
    - BEDROCK_MODEL_ID: Bedrock model identifier (default: anthropic.claude-sonnet-4-5-20250929-v1:0)
    - LOG_LEVEL: Logging level (default: INFO)
    - MAX_TOKENS_PER_CHUNK: Maximum tokens per chunk (default: 100000)
    
    Returns:
        Configuration dictionary
        
    Raises:
        ConfigurationError: If required variables are missing
    """
    required_vars = [
        'EXECUTION_ID',
        'VIDEO_S3_URI',
        'TRANSCRIPTION_S3_URI',
        'TRACKING_TABLE',
        'OUTPUT_BUCKET'
    ]
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
    config['MAX_OUTPUT_TOKENS'] = int(
        os.environ.get('MAX_OUTPUT_TOKENS', '65536')  # 64K default
    )
    
    logger.info(f"Configuration loaded: {list(config.keys())}")
    return config


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
    
    # Add error if present (error is a reserved keyword)
    if error:
        update_expression += ", #error = :error"
        expression_values[':error'] = error
        expression_names['#error'] = 'error'
    
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


def process_video_transcription() -> Dict[str, Any]:
    """
    Main processing function for ECS task.
    
    Reads configuration from environment variables and processes
    video transcription to generate technical training documents.
    
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
        # 1. Load configuration from environment variables
        logger.info("Step 1: Loading configuration from environment variables")
        config = load_config()
        
        execution_id = config['EXECUTION_ID']
        transcription_uri = config['TRANSCRIPTION_S3_URI']
        video_uri = config['VIDEO_S3_URI']
        output_bucket = config['OUTPUT_BUCKET']
        
        logger.info(f"Processing execution: {execution_id}")
        logger.info(f"Video URI: {video_uri}")
        logger.info(f"Transcription URI: {transcription_uri}")
        logger.info(f"Output bucket: {output_bucket}")
        
        # 2. Initialize AWS clients
        logger.info("Step 2: Initializing AWS clients")
        region = config['AWS_REGION']
        s3_client = boto3.client('s3', region_name=region)
        dynamodb = boto3.resource('dynamodb', region_name=region)
        
        # 3. Update DynamoDB: PROCESSING
        logger.info("Step 3: Updating DynamoDB status -> PROCESSING")
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
        
        # 4. Initialize processing components
        logger.info("Step 4: Initializing processing components")
        
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
            s3_client=s3_client,
            max_output_tokens=config['MAX_OUTPUT_TOKENS']
        )
        
        logger.info("Components initialized successfully")
        
        # 5. Generate document (main processing)
        logger.info("Step 5: Starting document generation pipeline")
        logger.info("-" * 80)
        
        result = generator.generate_document(
            execution_id=execution_id,
            transcription_s3_uri=transcription_uri,
            output_bucket=output_bucket
        )
        
        logger.info("-" * 80)
        logger.info("Document generation completed successfully")
        
        # 6. Update DynamoDB: COMPLETED
        logger.info("Step 6: Updating DynamoDB status -> COMPLETED")
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
        
        # 7. Prepare response
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
            if 'config' in locals():
                update_dynamodb_status(
                    dynamodb=boto3.resource('dynamodb', region_name=config.get('AWS_REGION', 'us-east-1')),
                    table_name=config.get('TRACKING_TABLE', ''),
                    execution_id=config.get('EXECUTION_ID', ''),
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
            if 'config' in locals():
                update_dynamodb_status(
                    dynamodb=boto3.resource('dynamodb', region_name=config.get('AWS_REGION', 'us-east-1')),
                    table_name=config.get('TRACKING_TABLE', ''),
                    execution_id=config.get('EXECUTION_ID', ''),
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
    Main entry point for ECS processor.
    
    Reads configuration from environment variables and processes
    video transcription to generate technical training documents.
    
    Required environment variables:
    - EXECUTION_ID: Unique execution identifier
    - VIDEO_S3_URI: S3 URI of the video file
    - TRANSCRIPTION_S3_URI: S3 URI of the transcription JSON file
    - TRACKING_TABLE: DynamoDB table name
    - OUTPUT_BUCKET: S3 bucket for outputs
    
    Optional environment variables:
    - AWS_REGION: AWS region (default: us-east-1)
    - BEDROCK_MODEL_ID: Bedrock model identifier
    - LOG_LEVEL: Logging level (default: INFO)
    - MAX_TOKENS_PER_CHUNK: Maximum tokens per chunk (default: 100000)
    
    Exit codes:
    - 0: Success
    - 1: Configuration error
    - 2: Processing error
    - 3: Unexpected error
    """
    try:
        result = process_video_transcription()
        print("\n" + "=" * 80)
        print("PROCESSING RESULT:")
        print(json.dumps(result, indent=2))
        print("=" * 80)
        
        if result.get('statusCode') == 200:
            sys.exit(0)
        elif result.get('statusCode') == 400:
            sys.exit(1)
        else:
            sys.exit(2)
            
    except ConfigurationError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except ProcessingError as e:
        logger.error(f"Processing error: {e}")
        sys.exit(2)
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        sys.exit(3)


if __name__ == '__main__':
    main()
