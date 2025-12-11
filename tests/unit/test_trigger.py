"""
Unit tests for Lambda Trigger Function
"""
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/functions/trigger'))

from app import (
    parse_s3_event,
    validate_video_file,
    extract_video_metadata,
    create_response
)


class TestParseS3Event:
    """Test S3 event parsing"""
    
    def test_parse_s3_direct_event(self):
        """Test parsing direct S3 event notification"""
        event = {
            'Records': [{
                's3': {
                    'bucket': {'name': 'test-bucket'},
                    'object': {'key': 'test-video.mp4'}
                }
            }]
        }
        
        result = parse_s3_event(event)
        assert result is not None
        assert result['bucket'] == 'test-bucket'
        assert result['key'] == 'test-video.mp4'
    
    def test_parse_eventbridge_event(self):
        """Test parsing EventBridge event"""
        event = {
            'detail': {
                'bucket': {'name': 'test-bucket'},
                'object': {'key': 'test-video.mp4'}
            }
        }
        
        result = parse_s3_event(event)
        assert result is not None
        assert result['bucket'] == 'test-bucket'
        assert result['key'] == 'test-video.mp4'
    
    def test_parse_invalid_event(self):
        """Test parsing invalid event"""
        event = {'invalid': 'data'}
        result = parse_s3_event(event)
        assert result is None


class TestValidateVideoFile:
    """Test video file validation"""
    
    def test_validate_supported_format(self):
        """Test validation of supported video format"""
        result = validate_video_file('video.mp4', 1024 * 1024)
        assert result['valid'] is True
    
    def test_validate_unsupported_format(self):
        """Test validation of unsupported format"""
        result = validate_video_file('video.txt', 1024 * 1024)
        assert result['valid'] is False
        assert 'Unsupported file format' in result['reason']
    
    def test_validate_file_too_large(self):
        """Test validation of file that's too large"""
        max_size = 5 * 1024 * 1024 * 1024  # 5 GB
        result = validate_video_file('video.mp4', max_size + 1)
        assert result['valid'] is False
        assert 'too large' in result['reason']
    
    def test_validate_empty_file(self):
        """Test validation of empty file"""
        result = validate_video_file('video.mp4', 0)
        assert result['valid'] is False
        assert 'empty' in result['reason']
    
    def test_validate_different_formats(self):
        """Test validation of different supported formats"""
        formats = ['.mp4', '.mov', '.avi', '.mkv', '.webm']
        for fmt in formats:
            result = validate_video_file(f'video{fmt}', 1024 * 1024)
            assert result['valid'] is True


class TestExtractVideoMetadata:
    """Test video metadata extraction"""
    
    def test_extract_basic_metadata(self):
        """Test basic metadata extraction"""
        bucket = 'test-bucket'
        key = 'videos/test-video.mp4'
        metadata = {
            'size': 10485760,  # 10 MB
            'etag': 'abc123',
            'last_modified': '2024-12-11T10:00:00'
        }
        
        result = extract_video_metadata(bucket, key, metadata)
        
        assert result['filename'] == 'test-video.mp4'
        assert result['extension'] == '.mp4'
        assert result['mime_type'] == 'video/mp4'
        assert result['size_bytes'] == 10485760
        assert result['size_mb'] == 10.0
        assert result['bucket'] == 'test-bucket'
        assert result['key'] == 'videos/test-video.mp4'
        assert result['s3_uri'] == 's3://test-bucket/videos/test-video.mp4'
    
    def test_extract_metadata_different_extensions(self):
        """Test metadata extraction for different file types"""
        test_cases = [
            ('video.mp4', '.mp4', 'video/mp4'),
            ('video.mov', '.mov', 'video/quicktime'),
            ('video.avi', '.avi', 'video/x-msvideo'),
            ('video.mkv', '.mkv', 'video/x-matroska')
        ]
        
        for filename, ext, mime in test_cases:
            metadata = {
                'size': 1024,
                'etag': 'test',
                'last_modified': '2024-12-11T10:00:00'
            }
            result = extract_video_metadata('bucket', filename, metadata)
            assert result['extension'] == ext
            assert result['mime_type'] == mime


class TestCreateResponse:
    """Test response creation"""
    
    def test_create_success_response(self):
        """Test creating success response"""
        response = create_response(200, {'message': 'success'})
        assert response['statusCode'] == 200
        assert 'application/json' in response['headers']['Content-Type']
        body = json.loads(response['body'])
        assert body['message'] == 'success'
    
    def test_create_error_response(self):
        """Test creating error response"""
        response = create_response(500, 'Internal error')
        assert response['statusCode'] == 500
        assert response['body'] == 'Internal error'
    
    def test_create_response_with_dict(self):
        """Test creating response with dict body"""
        data = {'key': 'value', 'number': 42}
        response = create_response(200, data)
        body = json.loads(response['body'])
        assert body == data


@pytest.fixture
def mock_env():
    """Mock environment variables"""
    with patch.dict(os.environ, {
        'TRACKING_TABLE': 'test-tracking-table',
        'ENVIRONMENT': 'test',
        'LOG_LEVEL': 'INFO'
    }):
        yield


class TestLambdaHandler:
    """Test Lambda handler integration"""
    
    @patch('app.s3_client')
    @patch('app.dynamodb')
    def test_handler_success(self, mock_dynamodb, mock_s3, mock_env):
        """Test successful Lambda invocation"""
        # Mock S3 head_object
        mock_s3.head_object.return_value = {
            'ContentLength': 1024 * 1024,
            'ContentType': 'video/mp4',
            'LastModified': '2024-12-11T10:00:00',
            'ETag': '"abc123"'
        }
        
        # Mock DynamoDB table
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        
        # Import after mocking
        from app import lambda_handler
        
        # Test event
        event = {
            'Records': [{
                's3': {
                    'bucket': {'name': 'test-bucket'},
                    'object': {'key': 'test-video.mp4'}
                }
            }]
        }
        
        response = lambda_handler(event, {})
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'success'
        assert 'execution_id' in body


if __name__ == '__main__':
    pytest.main([__file__, '-v'])