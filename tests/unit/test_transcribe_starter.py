"""
Unit tests for Lambda Transcribe Starter Function
"""
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from botocore.exceptions import ClientError

# Import the functions to test
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/functions/transcribe'))
from app import (
    lambda_handler,
    parse_input_event,
    validate_s3_uri,
    parse_s3_uri,
    get_media_format,
    generate_job_name,
    start_transcription_job,
    update_tracking_record,
    create_response
)


class TestParseInputEvent:
    """Test input event parsing"""
    
    def test_parse_direct_invocation_format(self):
        """Test parsing direct invocation with s3_uri"""
        event = {
            'execution_id': '550e8400-e29b-41d4-a716-446655440000',
            's3_uri': 's3://bucket/video.mp4',
            'language_code': 'pt-BR',
            'max_speakers': 10
        }
        
        result = parse_input_event(event)
        
        assert result is not None
        assert result['execution_id'] == '550e8400-e29b-41d4-a716-446655440000'
        assert result['s3_uri'] == 's3://bucket/video.mp4'
        assert result['language_code'] == 'pt-BR'
        assert result['max_speakers'] == 10
    
    def test_parse_step_functions_format(self):
        """Test parsing Step Functions event format"""
        event = {
            'execution_id': '550e8400-e29b-41d4-a716-446655440000',
            'bucket': 'test-bucket',
            'video_key': 'videos/meeting.mp4'
        }
        
        result = parse_input_event(event)
        
        assert result is not None
        assert result['execution_id'] == '550e8400-e29b-41d4-a716-446655440000'
        assert result['s3_uri'] == 's3://test-bucket/videos/meeting.mp4'
    
    def test_parse_step_functions_with_metadata(self):
        """Test parsing Step Functions event with metadata"""
        event = {
            'execution_id': '550e8400-e29b-41d4-a716-446655440000',
            'metadata': {
                's3_uri': 's3://bucket/video.mp4',
                'filename': 'video.mp4'
            }
        }
        
        result = parse_input_event(event)
        
        assert result is not None
        assert result['execution_id'] == '550e8400-e29b-41d4-a716-446655440000'
        assert result['s3_uri'] == 's3://bucket/video.mp4'
    
    def test_parse_invalid_format(self):
        """Test parsing invalid event format"""
        event = {
            'invalid': 'data'
        }
        
        result = parse_input_event(event)
        
        assert result is None


class TestValidateS3Uri:
    """Test S3 URI validation"""
    
    def test_valid_s3_uri(self):
        """Test valid S3 URI"""
        assert validate_s3_uri('s3://bucket/key') is True
        assert validate_s3_uri('s3://my-bucket-123/path/to/file.mp4') is True
        assert validate_s3_uri('s3://bucket.with.dots/file.mp4') is True
    
    def test_invalid_s3_uri(self):
        """Test invalid S3 URI"""
        assert validate_s3_uri('http://bucket/key') is False
        assert validate_s3_uri('s3://') is False
        assert validate_s3_uri('bucket/key') is False
        assert validate_s3_uri('') is False


class TestParseS3Uri:
    """Test S3 URI parsing"""
    
    def test_parse_simple_uri(self):
        """Test parsing simple S3 URI"""
        bucket, key = parse_s3_uri('s3://my-bucket/video.mp4')
        
        assert bucket == 'my-bucket'
        assert key == 'video.mp4'
    
    def test_parse_uri_with_path(self):
        """Test parsing S3 URI with path"""
        bucket, key = parse_s3_uri('s3://my-bucket/path/to/video.mp4')
        
        assert bucket == 'my-bucket'
        assert key == 'path/to/video.mp4'


class TestGetMediaFormat:
    """Test media format detection"""
    
    def test_supported_formats(self):
        """Test all supported media formats"""
        assert get_media_format('video.mp4') == 'mp4'
        assert get_media_format('audio.mp3') == 'mp3'
        assert get_media_format('audio.wav') == 'wav'
        assert get_media_format('audio.flac') == 'flac'
        assert get_media_format('video.webm') == 'webm'
        assert get_media_format('audio.m4a') == 'mp4'
    
    def test_case_insensitive(self):
        """Test case insensitive format detection"""
        assert get_media_format('VIDEO.MP4') == 'mp4'
        assert get_media_format('Audio.MP3') == 'mp3'
    
    def test_unsupported_format(self):
        """Test unsupported format returns None"""
        assert get_media_format('video.avi') is None
        assert get_media_format('document.pdf') is None


class TestGenerateJobName:
    """Test job name generation"""
    
    def test_generate_valid_job_name(self):
        """Test job name generation"""
        execution_id = '550e8400-e29b-41d4-a716-446655440000'
        job_name = generate_job_name(execution_id)
        
        assert job_name == f'transcribe-{execution_id}'
        assert job_name.startswith('transcribe-')
    
    def test_job_name_sanitization(self):
        """Test job name sanitizes invalid characters"""
        execution_id = 'test@id#with$special%chars'
        job_name = generate_job_name(execution_id)
        
        assert '@' not in job_name
        assert '#' not in job_name
        assert '$' not in job_name
        assert '%' not in job_name


class TestStartTranscriptionJob:
    """Test starting transcription jobs"""
    
    @patch('app.transcribe_client')
    def test_start_job_success(self, mock_client):
        """Test successful job start"""
        mock_client.start_transcription_job.return_value = {
            'TranscriptionJob': {
                'TranscriptionJobName': 'test-job',
                'TranscriptionJobStatus': 'IN_PROGRESS',
                'LanguageCode': 'pt-BR',
                'MediaFormat': 'mp4',
                'CreationTime': datetime(2024, 12, 11, 10, 0, 0)
            }
        }
        
        result = start_transcription_job(
            job_name='test-job',
            media_uri='s3://bucket/video.mp4',
            media_format='mp4',
            language_code='pt-BR',
            max_speakers=10,
            output_bucket='output-bucket',
            output_key='test/'
        )
        
        assert result is not None
        assert result['job_name'] == 'test-job'
        assert result['job_status'] == 'IN_PROGRESS'
        assert result['language_code'] == 'pt-BR'
        
        # Verify the API was called with correct parameters
        mock_client.start_transcription_job.assert_called_once()
        call_args = mock_client.start_transcription_job.call_args[1]
        assert call_args['TranscriptionJobName'] == 'test-job'
        assert call_args['Media']['MediaFileUri'] == 's3://bucket/video.mp4'
        assert call_args['Settings']['ShowSpeakerLabels'] is True
        assert call_args['Settings']['MaxSpeakerLabels'] == 10
    
    @patch('app.transcribe_client')
    def test_start_job_conflict_existing_job(self, mock_client):
        """Test handling of duplicate job name"""
        # Mock conflict exception on start
        mock_client.start_transcription_job.side_effect = ClientError(
            {'Error': {'Code': 'ConflictException', 'Message': 'Job already exists'}},
            'StartTranscriptionJob'
        )
        
        # Mock successful get of existing job
        mock_client.get_transcription_job.return_value = {
            'TranscriptionJob': {
                'TranscriptionJobName': 'test-job',
                'TranscriptionJobStatus': 'IN_PROGRESS',
                'LanguageCode': 'pt-BR',
                'MediaFormat': 'mp4',
                'CreationTime': datetime(2024, 12, 11, 10, 0, 0)
            }
        }
        
        result = start_transcription_job(
            job_name='test-job',
            media_uri='s3://bucket/video.mp4',
            media_format='mp4',
            language_code='pt-BR',
            max_speakers=10,
            output_bucket='output-bucket',
            output_key='test/'
        )
        
        assert result is not None
        assert result['job_name'] == 'test-job'
        mock_client.get_transcription_job.assert_called_once()
    
    @patch('app.transcribe_client')
    def test_start_job_quota_exceeded(self, mock_client):
        """Test handling of quota exceeded error"""
        mock_client.start_transcription_job.side_effect = ClientError(
            {'Error': {'Code': 'LimitExceededException', 'Message': 'Quota exceeded'}},
            'StartTranscriptionJob'
        )
        
        with pytest.raises(ClientError):
            start_transcription_job(
                job_name='test-job',
                media_uri='s3://bucket/video.mp4',
                media_format='mp4',
                language_code='pt-BR',
                max_speakers=10,
                output_bucket='output-bucket',
                output_key='test/'
            )
    
    @patch('app.transcribe_client')
    def test_start_job_bad_request(self, mock_client):
        """Test handling of bad request error"""
        mock_client.start_transcription_job.side_effect = ClientError(
            {'Error': {'Code': 'BadRequestException', 'Message': 'Invalid parameters'}},
            'StartTranscriptionJob'
        )
        
        result = start_transcription_job(
            job_name='test-job',
            media_uri='s3://bucket/video.mp4',
            media_format='mp4',
            language_code='pt-BR',
            max_speakers=10,
            output_bucket='output-bucket',
            output_key='test/'
        )
        
        assert result is None


class TestUpdateTrackingRecord:
    """Test DynamoDB tracking updates"""
    
    @patch('app.dynamodb')
    @patch('app.TRACKING_TABLE', 'test-table')
    def test_update_success(self, mock_dynamodb):
        """Test successful DynamoDB update"""
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.update_item.return_value = {'Attributes': {}}
        
        job_details = {
            'job_name': 'test-job',
            'job_status': 'IN_PROGRESS',
            'language_code': 'pt-BR',
            'media_format': 'mp4',
            'created_at': '2024-12-11T10:00:00'
        }
        
        result = update_tracking_record(
            execution_id='550e8400-e29b-41d4-a716-446655440000',
            job_name='test-job',
            job_details=job_details
        )
        
        assert result is True
        mock_table.update_item.assert_called_once()
    
    @patch('app.dynamodb')
    @patch('app.TRACKING_TABLE', 'test-table')
    def test_update_record_not_found(self, mock_dynamodb):
        """Test update when record doesn't exist"""
        mock_table = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.update_item.side_effect = ClientError(
            {'Error': {'Code': 'ConditionalCheckFailedException', 'Message': 'Not found'}},
            'UpdateItem'
        )
        
        job_details = {
            'job_name': 'test-job',
            'job_status': 'IN_PROGRESS',
            'language_code': 'pt-BR',
            'media_format': 'mp4',
            'created_at': '2024-12-11T10:00:00'
        }
        
        result = update_tracking_record(
            execution_id='550e8400-e29b-41d4-a716-446655440000',
            job_name='test-job',
            job_details=job_details
        )
        
        assert result is False
    
    @patch('app.TRACKING_TABLE', None)
    def test_update_no_table_configured(self):
        """Test update when table not configured"""
        job_details = {
            'job_name': 'test-job',
            'job_status': 'IN_PROGRESS',
            'language_code': 'pt-BR',
            'media_format': 'mp4',
            'created_at': '2024-12-11T10:00:00'
        }
        
        result = update_tracking_record(
            execution_id='550e8400-e29b-41d4-a716-446655440000',
            job_name='test-job',
            job_details=job_details
        )
        
        # Should return True (skip update gracefully)
        assert result is True


class TestCreateResponse:
    """Test response creation"""
    
    def test_create_success_response(self):
        """Test creating success response"""
        body = {'status': 'success', 'message': 'Job started'}
        response = create_response(200, body)
        
        assert response['statusCode'] == 200
        assert 'body' in response
        assert json.loads(response['body']) == body
        assert response['headers']['Content-Type'] == 'application/json'
    
    def test_create_error_response_with_string(self):
        """Test creating error response with string body"""
        response = create_response(400, 'Invalid input')
        
        assert response['statusCode'] == 400
        assert response['body'] == 'Invalid input'


class TestLambdaHandler:
    """Test Lambda handler integration"""
    
    @patch('app.update_tracking_record')
    @patch('app.start_transcription_job')
    @patch('app.OUTPUT_BUCKET', 'output-bucket')
    @patch('app.LANGUAGE_CODE', 'pt-BR')
    @patch('app.MAX_SPEAKERS', 10)
    def test_handler_success(self, mock_start_job, mock_update):
        """Test successful Lambda execution"""
        event = {
            'execution_id': '550e8400-e29b-41d4-a716-446655440000',
            's3_uri': 's3://input-bucket/videos/meeting.mp4'
        }
        
        mock_start_job.return_value = {
            'job_name': 'transcribe-550e8400-e29b-41d4-a716-446655440000',
            'job_status': 'IN_PROGRESS',
            'language_code': 'pt-BR',
            'media_format': 'mp4',
            'created_at': '2024-12-11T10:00:00'
        }
        
        mock_update.return_value = True
        
        response = lambda_handler(event, None)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'success'
        assert 'transcription_job' in body
        assert body['transcription_job']['job_name'] == 'transcribe-550e8400-e29b-41d4-a716-446655440000'
        
        # Verify functions were called
        mock_start_job.assert_called_once()
        mock_update.assert_called_once()
    
    @patch('app.OUTPUT_BUCKET', 'output-bucket')
    def test_handler_invalid_input(self):
        """Test handler with invalid input"""
        event = {
            'invalid': 'data'
        }
        
        response = lambda_handler(event, None)
        
        assert response['statusCode'] == 400
        assert 'Invalid input format' in response['body']
    
    @patch('app.OUTPUT_BUCKET', 'output-bucket')
    def test_handler_invalid_s3_uri(self):
        """Test handler with invalid S3 URI"""
        event = {
            'execution_id': '550e8400-e29b-41d4-a716-446655440000',
            's3_uri': 'invalid-uri'
        }
        
        response = lambda_handler(event, None)
        
        assert response['statusCode'] == 400
        assert 'Invalid S3 URI' in response['body']
    
    @patch('app.OUTPUT_BUCKET', 'output-bucket')
    def test_handler_unsupported_format(self):
        """Test handler with unsupported media format"""
        event = {
            'execution_id': '550e8400-e29b-41d4-a716-446655440000',
            's3_uri': 's3://bucket/document.pdf'
        }
        
        response = lambda_handler(event, None)
        
        assert response['statusCode'] == 400
        assert 'Unsupported media format' in response['body']
    
    @patch('app.start_transcription_job')
    @patch('app.OUTPUT_BUCKET', 'output-bucket')
    def test_handler_transcribe_failure(self, mock_start_job):
        """Test handler when transcribe job fails to start"""
        event = {
            'execution_id': '550e8400-e29b-41d4-a716-446655440000',
            's3_uri': 's3://bucket/video.mp4'
        }
        
        mock_start_job.return_value = None
        
        response = lambda_handler(event, None)
        
        assert response['statusCode'] == 500
        assert 'Failed to start transcription job' in response['body']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])