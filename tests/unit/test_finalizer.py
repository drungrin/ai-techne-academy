"""
Unit tests for Lambda Finalizer Function
"""
import json
import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError

# Import function under test
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/functions/finalizer'))
from app import (
    lambda_handler,
    parse_input_event,
    determine_final_status,
    build_execution_summary,
    calculate_processing_cost,
    update_tracking_with_retry,
    publish_sns_notification,
    build_success_notification,
    build_failure_notification,
    build_partial_success_notification,
    record_cloudwatch_metrics,
    create_response
)


# Test fixtures
@pytest.fixture
def success_event():
    """Success event from Step Functions"""
    return {
        'execution_id': '550e8400-e29b-41d4-a716-446655440000',
        'status': 'COMPLETED',
        'video_key': 'videos/meeting.mp4',
        'bucket': 'input-bucket',
        'processing_results': {
            'transcription': {
                'status': 'COMPLETED',
                'duration_seconds': 7200,
                'speakers_detected': 3,
                'transcript_uri': 's3://transcripts/550e8400/transcript.json'
            },
            'llm_processing': {
                'status': 'COMPLETED',
                'documents_generated': ['training', 'troubleshooting'],
                'output_uri': 's3://output/550e8400/documents.zip',
                'document_size_bytes': 2457600,
                'tokens_used': 45000,
                'processing_time_seconds': 180
            }
        },
        'timestamps': {
            'started_at': '2024-12-11T10:00:00Z',
            'completed_at': '2024-12-11T12:03:00Z'
        },
        'metadata': {
            'filename': 'meeting.mp4',
            'size_mb': 1500.0
        }
    }


@pytest.fixture
def failure_event():
    """Failure event from Step Functions"""
    return {
        'execution_id': '550e8400-e29b-41d4-a716-446655440001',
        'status': 'FAILED',
        'video_key': 'videos/meeting2.mp4',
        'bucket': 'input-bucket',
        'error': {
            'stage': 'llm_processing',
            'error_code': 'BedrockQuotaExceeded',
            'error_message': 'Rate limit exceeded',
            'timestamp': '2024-12-11T11:30:00Z'
        },
        'processing_results': {
            'transcription': {
                'status': 'COMPLETED',
                'transcript_uri': 's3://transcripts/550e8400/transcript.json'
            },
            'llm_processing': {
                'status': 'FAILED'
            }
        },
        'timestamps': {
            'started_at': '2024-12-11T10:00:00Z',
            'failed_at': '2024-12-11T11:30:00Z'
        },
        'metadata': {
            'filename': 'meeting2.mp4'
        }
    }


@pytest.fixture
def partial_success_event():
    """Partial success event from Step Functions"""
    return {
        'execution_id': '550e8400-e29b-41d4-a716-446655440002',
        'status': 'PARTIAL_SUCCESS',
        'video_key': 'videos/meeting3.mp4',
        'bucket': 'input-bucket',
        'processing_results': {
            'transcription': {
                'status': 'COMPLETED',
                'speakers_detected': 2,
                'transcript_uri': 's3://transcripts/transcript.json'
            },
            'llm_processing': {
                'status': 'PARTIAL',
                'documents_generated': ['training'],
                'failed_documents': ['troubleshooting'],
                'output_uri': 's3://output/docs.zip',
                'tokens_used': 30000
            }
        },
        'timestamps': {
            'started_at': '2024-12-11T10:00:00Z',
            'completed_at': '2024-12-11T11:30:00Z'
        },
        'metadata': {
            'filename': 'meeting3.mp4'
        }
    }


# Test Suite 1: Input Parsing
class TestInputParsing:
    """Test input event parsing and validation"""
    
    def test_parse_success_event(self, success_event):
        """Should parse valid success event"""
        result = parse_input_event(success_event)
        
        assert result is not None
        assert result['execution_id'] == '550e8400-e29b-41d4-a716-446655440000'
        assert result['status'] == 'COMPLETED'
        assert 'processing_results' in result
        assert 'timestamps' in result
    
    def test_parse_failure_event(self, failure_event):
        """Should parse valid failure event"""
        result = parse_input_event(failure_event)
        
        assert result is not None
        assert result['execution_id'] == '550e8400-e29b-41d4-a716-446655440001'
        assert result['status'] == 'FAILED'
        assert 'error' in result
    
    def test_parse_partial_success_event(self, partial_success_event):
        """Should parse valid partial success event"""
        result = parse_input_event(partial_success_event)
        
        assert result is not None
        assert result['status'] == 'PARTIAL_SUCCESS'
    
    def test_parse_missing_execution_id(self):
        """Should return None for missing execution_id"""
        event = {'status': 'COMPLETED'}
        result = parse_input_event(event)
        
        assert result is None
    
    def test_parse_invalid_event_format(self):
        """Should return None for invalid event format"""
        result = parse_input_event(None)
        assert result is None
        
        result = parse_input_event("invalid")
        assert result is None


# Test Suite 2: Status Determination
class TestStatusDetermination:
    """Test final status determination logic"""
    
    def test_determine_completed_status(self):
        """Should return COMPLETED for all successful stages"""
        event = {
            'status': 'UNKNOWN',
            'processing_results': {
                'transcription': {'status': 'COMPLETED'},
                'llm_processing': {'status': 'COMPLETED'}
            }
        }
        
        status = determine_final_status(event)
        assert status == 'COMPLETED'
    
    def test_determine_failed_status_transcription(self):
        """Should return FAILED when transcription fails"""
        event = {
            'status': 'UNKNOWN',
            'processing_results': {
                'transcription': {'status': 'FAILED'},
                'llm_processing': {'status': 'COMPLETED'}
            }
        }
        
        status = determine_final_status(event)
        assert status == 'FAILED'
    
    def test_determine_partial_success_llm_failed(self):
        """Should return PARTIAL_SUCCESS when transcription OK but LLM fails"""
        event = {
            'status': 'UNKNOWN',
            'processing_results': {
                'transcription': {'status': 'COMPLETED'},
                'llm_processing': {'status': 'FAILED'}
            }
        }
        
        status = determine_final_status(event)
        assert status == 'PARTIAL_SUCCESS'
    
    def test_determine_partial_success_llm_partial(self):
        """Should return PARTIAL_SUCCESS when LLM is partial"""
        event = {
            'status': 'UNKNOWN',
            'processing_results': {
                'transcription': {'status': 'COMPLETED'},
                'llm_processing': {'status': 'PARTIAL'}
            }
        }
        
        status = determine_final_status(event)
        assert status == 'PARTIAL_SUCCESS'
    
    def test_use_explicit_status(self):
        """Should use explicit status from event if valid"""
        event = {
            'status': 'COMPLETED',
            'processing_results': {}
        }
        
        status = determine_final_status(event)
        assert status == 'COMPLETED'
    
    def test_default_to_failed_unknown(self):
        """Should default to FAILED for unknown status combinations"""
        event = {
            'status': 'UNKNOWN',
            'processing_results': {
                'transcription': {'status': 'UNKNOWN'},
                'llm_processing': {'status': 'UNKNOWN'}
            }
        }
        
        status = determine_final_status(event)
        assert status == 'FAILED'


# Test Suite 3: Metrics and Cost Calculation
class TestMetricsCalculation:
    """Test metrics extraction and cost calculation"""
    
    def test_calculate_processing_cost_full(self):
        """Should calculate cost correctly for complete processing"""
        metrics = {
            'transcription_duration_seconds': 7200,  # 2 hours = 120 min
            'tokens_used': 45000
        }
        
        cost = calculate_processing_cost(metrics)
        
        # 120 min * $0.024 = $2.88 (transcribe)
        # 45K tokens: 30.15K input * $0.003/1K + 14.85K output * $0.015/1K ≈ $0.31 (bedrock)
        # Total ≈ $3.19
        assert cost > 3.0
        assert cost < 3.5
        assert isinstance(cost, float)
    
    def test_calculate_cost_zero_metrics(self):
        """Should handle zero metrics gracefully"""
        metrics = {
            'transcription_duration_seconds': 0,
            'tokens_used': 0
        }
        
        cost = calculate_processing_cost(metrics)
        assert cost == 0.0
    
    def test_calculate_cost_missing_fields(self):
        """Should handle missing fields with defaults"""
        metrics = {}
        
        cost = calculate_processing_cost(metrics)
        assert cost == 0.0
    
    def test_build_execution_summary(self, success_event):
        """Should build complete execution summary"""
        final_status = 'COMPLETED'
        summary = build_execution_summary(success_event, final_status)
        
        assert summary['execution_id'] == success_event['execution_id']
        assert summary['final_status'] == final_status
        assert summary['duration_seconds'] > 0
        assert summary['cost_usd'] > 0
        assert 'metrics' in summary
        assert summary['metrics']['tokens_used'] == 45000
        assert summary['documents_generated'] == 2
    
    def test_build_summary_missing_timestamps(self):
        """Should handle missing timestamps"""
        event = {
            'execution_id': 'test-id',
            'processing_results': {},
            'timestamps': {},
            'metadata': {}
        }
        
        summary = build_execution_summary(event, 'FAILED')
        
        assert summary['duration_seconds'] == 0
        assert 'metrics' in summary


# Test Suite 4: DynamoDB Updates with Retry
class TestDynamoDBRetry:
    """Test DynamoDB update with exponential backoff retry"""
    
    @patch('app.dynamodb')
    @patch('app.time.sleep')
    def test_update_success_first_attempt(self, mock_sleep, mock_dynamodb):
        """Should succeed on first attempt"""
        mock_table = Mock()
        mock_table.update_item = Mock()
        mock_dynamodb.Table.return_value = mock_table
        
        summary = {
            'execution_id': 'test-id',
            'completion_time': '2024-12-11T12:00:00Z',
            'duration_seconds': 7200,
            'cost_usd': 1.45,
            'metrics': {
                'tokens_used': 45000,
                'document_size_bytes': 2457600
            }
        }
        
        result = update_tracking_with_retry('test-id', 'COMPLETED', summary, max_attempts=3)
        
        assert result is True
        assert mock_table.update_item.call_count == 1
        assert mock_sleep.call_count == 0
    
    @patch('app.dynamodb')
    @patch('app.time.sleep')
    @patch('app.random.uniform', return_value=0.1)
    def test_retry_after_throttling(self, mock_random, mock_sleep, mock_dynamodb):
        """Should retry after throttling error"""
        mock_table = Mock()
        mock_table.update_item = Mock(side_effect=[
            ClientError({'Error': {'Code': 'ProvisionedThroughputExceededException'}}, 'UpdateItem'),
            None  # Success on second attempt
        ])
        mock_dynamodb.Table.return_value = mock_table
        
        summary = {
            'completion_time': '2024-12-11T12:00:00Z',
            'duration_seconds': 100,
            'cost_usd': 1.0,
            'metrics': {}
        }
        
        result = update_tracking_with_retry('test-id', 'COMPLETED', summary, max_attempts=3)
        
        assert result is True
        assert mock_table.update_item.call_count == 2
        assert mock_sleep.call_count == 1
    
    @patch('app.dynamodb')
    @patch('app.time.sleep')
    def test_fail_after_max_retries(self, mock_sleep, mock_dynamodb):
        """Should raise error after max retries"""
        mock_table = Mock()
        mock_table.update_item = Mock(side_effect=ClientError(
            {'Error': {'Code': 'ServiceUnavailable'}}, 'UpdateItem'
        ))
        mock_dynamodb.Table.return_value = mock_table
        
        summary = {
            'completion_time': '2024-12-11T12:00:00Z',
            'duration_seconds': 100,
            'cost_usd': 1.0,
            'metrics': {}
        }
        
        with pytest.raises(ClientError):
            update_tracking_with_retry('test-id', 'COMPLETED', summary, max_attempts=3)
        
        assert mock_table.update_item.call_count == 3
        assert mock_sleep.call_count == 2
    
    @patch('app.dynamodb')
    def test_no_retry_on_validation_error(self, mock_dynamodb):
        """Should not retry on validation errors"""
        mock_table = Mock()
        mock_table.update_item = Mock(side_effect=ClientError(
            {'Error': {'Code': 'ValidationException'}}, 'UpdateItem'
        ))
        mock_dynamodb.Table.return_value = mock_table
        
        summary = {
            'completion_time': '2024-12-11T12:00:00Z',
            'duration_seconds': 100,
            'cost_usd': 1.0,
            'metrics': {}
        }
        
        with pytest.raises(ClientError):
            update_tracking_with_retry('test-id', 'COMPLETED', summary, max_attempts=3)
        
        # Should fail immediately without retries
        assert mock_table.update_item.call_count == 1
    
    @patch.dict(os.environ, {'TRACKING_TABLE': ''})
    def test_skip_update_if_not_configured(self):
        """Should skip update if TRACKING_TABLE not configured"""
        summary = {
            'completion_time': '2024-12-11T12:00:00Z',
            'duration_seconds': 100,
            'cost_usd': 1.0,
            'metrics': {}
        }
        
        result = update_tracking_with_retry('test-id', 'COMPLETED', summary)
        assert result is False


# Test Suite 5: SNS Notifications
class TestSNSNotifications:
    """Test SNS notification building and publishing"""
    
    def test_build_success_notification(self, success_event):
        """Should build complete success notification"""
        summary = {
            'video_filename': 'meeting.mp4',
            'duration_seconds': 7380,
            'cost_usd': 1.45,
            'completion_time': '2024-12-11T12:03:00Z'
        }
        
        subject, message = build_success_notification(success_event, summary)
        
        assert '✅' in subject
        assert 'meeting.mp4' in subject
        assert message['status'] == 'COMPLETED'
        assert message['execution_id'] == success_event['execution_id']
        assert 'video' in message
        assert 'processing' in message
        assert 'results' in message
        assert message['processing']['cost_estimate_usd'] == 1.45
    
    def test_build_failure_notification(self, failure_event):
        """Should build complete failure notification"""
        summary = {
            'video_filename': 'meeting2.mp4',
            'duration_seconds': 0,
            'cost_usd': 0.0
        }
        
        subject, message = build_failure_notification(failure_event, summary)
        
        assert '❌' in subject
        assert 'meeting2.mp4' in subject
        assert message['status'] == 'FAILED'
        assert 'error' in message
        assert message['error']['error_code'] == 'BedrockQuotaExceeded'
        assert 'recommended_actions' in message
        assert len(message['recommended_actions']) > 0
    
    def test_build_partial_success_notification(self, partial_success_event):
        """Should build partial success notification"""
        summary = {
            'video_filename': 'meeting3.mp4',
            'duration_seconds': 5400,
            'cost_usd': 0.95
        }
        
        subject, message = build_partial_success_notification(partial_success_event, summary)
        
        assert '⚠️' in subject
        assert 'meeting3.mp4' in subject
        assert message['status'] == 'PARTIAL_SUCCESS'
        assert 'completed' in message
        assert 'failed' in message
        assert 'next_steps' in message
    
    @patch('app.sns_client')
    def test_publish_notification_success(self, mock_sns, success_event):
        """Should successfully publish SNS notification"""
        mock_sns.publish.return_value = {'MessageId': 'msg-123'}
        
        summary = {
            'video_filename': 'test.mp4',
            'duration_seconds': 100,
            'cost_usd': 1.0,
            'completion_time': '2024-12-11T12:00:00Z'
        }
        
        result = publish_sns_notification(success_event, 'COMPLETED', summary)
        
        assert result is True
        assert mock_sns.publish.call_count == 1
        
        call_args = mock_sns.publish.call_args
        assert 'TopicArn' in call_args[1]
        assert 'Subject' in call_args[1]
        assert 'MessageAttributes' in call_args[1]
    
    @patch('app.sns_client')
    def test_publish_notification_failure(self, mock_sns, success_event):
        """Should handle SNS publish failure"""
        mock_sns.publish.side_effect = ClientError(
            {'Error': {'Code': 'InvalidParameter'}}, 'Publish'
        )
        
        summary = {
            'video_filename': 'test.mp4',
            'duration_seconds': 100,
            'cost_usd': 1.0,
            'completion_time': '2024-12-11T12:00:00Z'
        }
        
        result = publish_sns_notification(success_event, 'COMPLETED', summary)
        
        assert result is False
    
    @patch.dict(os.environ, {'NOTIFICATION_TOPIC_ARN': ''})
    def test_skip_notification_if_not_configured(self, success_event):
        """Should skip notification if ARN not configured"""
        summary = {'video_filename': 'test.mp4', 'duration_seconds': 100, 'cost_usd': 1.0, 'completion_time': '2024-12-11T12:00:00Z'}
        
        result = publish_sns_notification(success_event, 'COMPLETED', summary)
        assert result is False


# Test Suite 6: CloudWatch Metrics
class TestCloudWatchMetrics:
    """Test CloudWatch metrics recording"""
    
    @patch('app.cloudwatch')
    def test_record_all_metrics(self, mock_cloudwatch):
        """Should record all custom metrics"""
        mock_cloudwatch.put_metric_data = Mock()
        
        summary = {
            'duration_seconds': 7380,
            'cost_usd': 1.45,
            'metrics': {
                'tokens_used': 45000,
                'document_size_bytes': 2457600,
                'speakers_detected': 3
            }
        }
        
        result = record_cloudwatch_metrics('test-id', 'COMPLETED', summary)
        
        assert result is True
        assert mock_cloudwatch.put_metric_data.call_count == 1
        
        call_args = mock_cloudwatch.put_metric_data.call_args
        metric_data = call_args[1]['MetricData']
        
        # Should have 8 metrics
        assert len(metric_data) == 8
        
        # Verify metric names
        metric_names = [m['MetricName'] for m in metric_data]
        assert 'ProcessingDuration' in metric_names
        assert 'ProcessingSuccess' in metric_names
        assert 'ProcessingFailure' in metric_names
        assert 'TokensProcessed' in metric_names
        assert 'ProcessingCost' in metric_names
    
    @patch('app.cloudwatch')
    def test_handle_metrics_failure(self, mock_cloudwatch):
        """Should handle CloudWatch metrics failure gracefully"""
        mock_cloudwatch.put_metric_data.side_effect = ClientError(
            {'Error': {'Code': 'InvalidParameterValue'}}, 'PutMetricData'
        )
        
        summary = {
            'duration_seconds': 100,
            'cost_usd': 1.0,
            'metrics': {'tokens_used': 1000}
        }
        
        result = record_cloudwatch_metrics('test-id', 'COMPLETED', summary)
        
        # Should return False but not raise exception
        assert result is False
    
    @patch('app.cloudwatch')
    def test_metric_dimensions_correct(self, mock_cloudwatch):
        """Should set correct dimensions on metrics"""
        mock_cloudwatch.put_metric_data = Mock()
        
        summary = {
            'duration_seconds': 100,
            'cost_usd': 1.0,
            'metrics': {'tokens_used': 1000}
        }
        
        record_cloudwatch_metrics('test-id', 'COMPLETED', summary)
        
        call_args = mock_cloudwatch.put_metric_data.call_args
        metric_data = call_args[1]['MetricData']
        
        # Check first metric has proper dimensions
        first_metric = metric_data[0]
        assert 'Dimensions' in first_metric
        dimensions = {d['Name']: d['Value'] for d in first_metric['Dimensions']}
        assert 'Environment' in dimensions


# Test Suite 7: Lambda Handler Integration
class TestLambdaHandler:
    """Test complete Lambda handler execution"""
    
    @patch('app.record_cloudwatch_metrics')
    @patch('app.publish_sns_notification')
    @patch('app.update_tracking_with_retry')
    def test_successful_execution(
        self,
        mock_update,
        mock_publish,
        mock_metrics,
        success_event
    ):
        """Should complete full execution successfully"""
        mock_update.return_value = True
        mock_publish.return_value = True
        mock_metrics.return_value = True
        
        response = lambda_handler(success_event, None)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'success'
        assert body['final_status'] == 'COMPLETED'
        assert body['tracking_updated'] is True
        assert body['notification_sent'] is True
        assert body['metrics_recorded'] is True
    
    @patch('app.record_cloudwatch_metrics')
    @patch('app.publish_sns_notification')
    @patch('app.update_tracking_with_retry')
    def test_execution_with_dynamodb_failure(
        self,
        mock_update,
        mock_publish,
        mock_metrics,
        success_event
    ):
        """Should continue even if DynamoDB update fails"""
        mock_update.side_effect = Exception("DynamoDB error")
        mock_publish.return_value = True
        mock_metrics.return_value = True
        
        response = lambda_handler(success_event, None)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['tracking_updated'] is False
        assert body['notification_sent'] is True  # Should continue
        assert body['metrics_recorded'] is True  # Should continue
    
    @patch('app.record_cloudwatch_metrics')
    @patch('app.publish_sns_notification')
    @patch('app.update_tracking_with_retry')
    def test_execution_with_partial_failures(
        self,
        mock_update,
        mock_publish,
        mock_metrics,
        success_event
    ):
        """Should handle partial failures gracefully"""
        mock_update.return_value = True
        mock_publish.side_effect = Exception("SNS error")
        mock_metrics.side_effect = Exception("Metrics error")
        
        response = lambda_handler(success_event, None)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['tracking_updated'] is True
        assert body['notification_sent'] is False
        assert body['metrics_recorded'] is False
    
    def test_invalid_input_event(self):
        """Should return 400 for invalid input"""
        invalid_event = {'invalid': 'data'}
        
        response = lambda_handler(invalid_event, None)
        
        assert response['statusCode'] == 400
        assert 'Invalid input' in response['body']
    
    @patch('app.parse_input_event')
    def test_exception_handling(self, mock_parse):
        """Should return 500 on unexpected error"""
        mock_parse.side_effect = Exception("Unexpected error")
        
        response = lambda_handler({'execution_id': 'test'}, None)
        
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert body['status'] == 'error'
        assert 'FinalizationError' in body['error']


# Test Suite 8: Response Creation
class TestResponseCreation:
    """Test response formatting"""
    
    def test_create_response_with_dict(self):
        """Should create response with dict body"""
        body = {'status': 'success', 'data': 'test'}
        response = create_response(200, body)
        
        assert response['statusCode'] == 200
        assert response['headers']['Content-Type'] == 'application/json'
        parsed_body = json.loads(response['body'])
        assert parsed_body['status'] == 'success'
    
    def test_create_response_with_string(self):
        """Should create response with string body"""
        response = create_response(400, "Error message")
        
        assert response['statusCode'] == 400
        assert response['body'] == "Error message"
    
    def test_create_error_response(self):
        """Should create proper error response"""
        error_body = {
            'status': 'error',
            'error': 'TestError',
            'message': 'Test error message'
        }
        response = create_response(500, error_body)
        
        assert response['statusCode'] == 500
        parsed_body = json.loads(response['body'])
        assert parsed_body['status'] == 'error'