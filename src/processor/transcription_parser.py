"""
Transcription Parser for AWS Transcribe JSON Output

This module handles parsing, chunking, and processing of AWS Transcribe
JSON output files. It supports adaptive chunking for long transcriptions
and speaker identification.

Author: AI Techne Academy
Version: 1.0.0
"""

import json
import math
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionSegment:
    """Represents a segment of transcription with metadata."""
    
    text: str
    start_time: float
    end_time: float
    speaker: Optional[str] = None
    confidence: float = 0.0


@dataclass
class TranscriptionChunk:
    """Represents a chunk of transcription for processing."""
    
    chunk_id: int
    total_chunks: int
    text: str
    tokens: int
    segments: List[TranscriptionSegment]
    speakers: List[str]
    timestamp_range: Tuple[float, float]
    metadata: Dict[str, Any]


class TranscriptionParser:
    """
    Parser for AWS Transcribe JSON output.
    
    Handles:
    - JSON parsing and validation
    - Speaker identification
    - Timestamp extraction
    - Adaptive chunking for long transcriptions
    - Token counting
    """
    
    def __init__(self, max_tokens_per_chunk: int = 100000):
        """
        Initialize the parser.
        
        Args:
            max_tokens_per_chunk: Maximum tokens per chunk (default: 100K)
        """
        self.max_tokens = max_tokens_per_chunk
        self.overlap_tokens = int(max_tokens_per_chunk * 0.1)  # 10% overlap
        
    def parse_transcribe_json(self, json_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse AWS Transcribe JSON output.
        
        Args:
            json_data: The Transcribe JSON response
            
        Returns:
            Dictionary with parsed transcription data:
            {
                'full_text': str,
                'segments': List[TranscriptionSegment],
                'speakers': List[str],
                'metadata': Dict
            }
            
        Raises:
            ValueError: If JSON structure is invalid
        """
        logger.info("Parsing AWS Transcribe JSON output")
        
        try:
            # Validate JSON structure
            if 'results' not in json_data:
                raise ValueError("Invalid Transcribe JSON: missing 'results' key")
            
            results = json_data['results']
            
            # Extract full transcript
            full_text = self._extract_full_text(results)
            
            # Extract segments with timestamps and speakers
            segments = self._extract_segments(results)
            
            # Extract unique speakers
            speakers = self._extract_speakers(segments)
            
            # Extract metadata
            metadata = self._extract_metadata(json_data)
            
            logger.info(
                f"Parsed transcription: {len(full_text)} chars, "
                f"{len(segments)} segments, {len(speakers)} speakers"
            )
            
            return {
                'full_text': full_text,
                'segments': segments,
                'speakers': speakers,
                'metadata': metadata
            }
            
        except Exception as e:
            logger.error(f"Error parsing Transcribe JSON: {str(e)}")
            raise ValueError(f"Failed to parse Transcribe JSON: {str(e)}")
    
    def _extract_full_text(self, results: Dict) -> str:
        """Extract full transcript text from results."""
        if 'transcripts' in results and len(results['transcripts']) > 0:
            return results['transcripts'][0].get('transcript', '')
        return ''
    
    def _extract_segments(self, results: Dict) -> List[TranscriptionSegment]:
        """
        Extract segments with timestamps and speaker labels.
        
        AWS Transcribe provides segments in the 'segments' array with
        speaker labels in the 'speaker_labels' section.
        """
        segments = []
        
        # Get speaker labels mapping
        speaker_map = self._build_speaker_map(results)
        
        # Extract segments from items
        if 'items' not in results:
            return segments
        
        current_segment = []
        current_start = None
        current_speaker = None
        
        for item in results['items']:
            item_type = item.get('type', 'pronunciation')
            
            if item_type == 'pronunciation':
                content = item.get('alternatives', [{}])[0].get('content', '')
                start_time = float(item.get('start_time', 0))
                end_time = float(item.get('end_time', 0))
                confidence = float(
                    item.get('alternatives', [{}])[0].get('confidence', 0)
                )
                
                # Get speaker for this time
                speaker = speaker_map.get(start_time, None)
                
                # Start new segment if speaker changes
                if current_speaker is not None and speaker != current_speaker:
                    # Save current segment
                    if current_segment:
                        segment_text = ' '.join(current_segment)
                        segments.append(TranscriptionSegment(
                            text=segment_text,
                            start_time=current_start,
                            end_time=end_time,
                            speaker=current_speaker,
                            confidence=confidence
                        ))
                    current_segment = []
                    current_start = None
                
                if current_start is None:
                    current_start = start_time
                
                current_segment.append(content)
                current_speaker = speaker
                
            elif item_type == 'punctuation':
                # Add punctuation to current segment
                content = item.get('alternatives', [{}])[0].get('content', '')
                if current_segment:
                    current_segment[-1] += content
        
        # Add final segment
        if current_segment:
            segments.append(TranscriptionSegment(
                text=' '.join(current_segment),
                start_time=current_start,
                end_time=end_time,
                speaker=current_speaker,
                confidence=0.0
            ))
        
        return segments
    
    def _build_speaker_map(self, results: Dict) -> Dict[float, str]:
        """Build mapping of timestamp to speaker label."""
        speaker_map = {}
        
        if 'speaker_labels' not in results:
            return speaker_map
        
        speaker_labels = results['speaker_labels']
        
        if 'segments' in speaker_labels:
            for segment in speaker_labels['segments']:
                speaker = segment.get('speaker_label', 'unknown')
                start_time = float(segment.get('start_time', 0))
                end_time = float(segment.get('end_time', 0))
                
                # Map all times in this range to this speaker
                if 'items' in segment:
                    for item in segment['items']:
                        item_start = float(item.get('start_time', 0))
                        speaker_map[item_start] = speaker
        
        return speaker_map
    
    def _extract_speakers(self, segments: List[TranscriptionSegment]) -> List[str]:
        """Extract unique list of speakers."""
        speakers = set()
        for segment in segments:
            if segment.speaker:
                speakers.add(segment.speaker)
        return sorted(list(speakers))
    
    def _extract_metadata(self, json_data: Dict) -> Dict[str, Any]:
        """Extract metadata from Transcribe JSON."""
        metadata = {
            'job_name': json_data.get('jobName', ''),
            'account_id': json_data.get('accountId', ''),
            'status': json_data.get('status', ''),
            'language_code': '',
            'media_format': '',
            'created_at': None
        }
        
        if 'results' in json_data:
            results = json_data['results']
            metadata['language_code'] = results.get('language_code', '')
        
        return metadata
    
    def count_tokens(self, text: str) -> int:
        """
        Estimate token count for text.
        
        Uses simple approximation: ~4 chars per token (Claude average).
        For production, use tiktoken library.
        
        Args:
            text: Text to count tokens for
            
        Returns:
            Estimated token count
        """
        # Simple approximation: 4 chars per token
        # This is Claude's approximate average
        return len(text) // 4
    
    def chunk_transcription(
        self,
        parsed_data: Dict[str, Any]
    ) -> List[TranscriptionChunk]:
        """
        Chunk transcription adaptively based on content.
        
        Strategy:
        1. Calculate total tokens
        2. If <= max_tokens: return single chunk
        3. If > max_tokens: apply adaptive chunking with:
           - Natural breakpoints (speaker changes, pauses)
           - 10% overlap between chunks
           - Metadata preservation
        
        Args:
            parsed_data: Output from parse_transcribe_json()
            
        Returns:
            List of TranscriptionChunk objects
        """
        full_text = parsed_data['full_text']
        segments = parsed_data['segments']
        speakers = parsed_data['speakers']
        
        total_tokens = self.count_tokens(full_text)
        
        logger.info(f"Chunking transcription: {total_tokens} tokens")
        
        # Single chunk if within limits
        if total_tokens <= self.max_tokens:
            logger.info("Transcription fits in single chunk")
            return [TranscriptionChunk(
                chunk_id=0,
                total_chunks=1,
                text=full_text,
                tokens=total_tokens,
                segments=segments,
                speakers=speakers,
                timestamp_range=(
                    segments[0].start_time if segments else 0,
                    segments[-1].end_time if segments else 0
                ),
                metadata={
                    'is_single_chunk': True,
                    'original_tokens': total_tokens
                }
            )]
        
        # Multi-chunk with adaptive strategy
        logger.info(f"Applying adaptive chunking (target: {self.max_tokens} tokens/chunk)")
        return self._adaptive_chunking(segments, speakers, total_tokens)
    
    def _adaptive_chunking(
        self,
        segments: List[TranscriptionSegment],
        speakers: List[str],
        total_tokens: int
    ) -> List[TranscriptionChunk]:
        """
        Perform adaptive chunking based on natural breakpoints.
        
        Breakpoints:
        1. Speaker changes
        2. Long pauses (>5 seconds)
        3. Target chunk size reached
        """
        chunks = []
        
        # Calculate target number of chunks
        num_chunks = math.ceil(total_tokens / self.max_tokens)
        target_tokens_per_chunk = total_tokens // num_chunks
        
        logger.info(
            f"Creating {num_chunks} chunks "
            f"(~{target_tokens_per_chunk} tokens each)"
        )
        
        current_chunk_segments = []
        current_chunk_tokens = 0
        chunk_id = 0
        
        for i, segment in enumerate(segments):
            segment_tokens = self.count_tokens(segment.text)
            
            # Check if we should start a new chunk
            should_break = False
            
            # Condition 1: Reached target size
            if current_chunk_tokens + segment_tokens > self.max_tokens:
                should_break = True
            
            # Condition 2: Good breakpoint (speaker change + near target)
            if (current_chunk_tokens > target_tokens_per_chunk * 0.8 and
                i > 0 and
                segment.speaker != segments[i-1].speaker):
                should_break = True
            
            # Condition 3: Long pause (>5 seconds)
            if (i > 0 and 
                segment.start_time - segments[i-1].end_time > 5.0 and
                current_chunk_tokens > target_tokens_per_chunk * 0.5):
                should_break = True
            
            if should_break and current_chunk_segments:
                # Create chunk
                chunk = self._create_chunk(
                    chunk_id=chunk_id,
                    total_chunks=num_chunks,
                    segments=current_chunk_segments,
                    speakers=speakers
                )
                chunks.append(chunk)
                
                # Start new chunk with overlap
                overlap_segments = self._get_overlap_segments(
                    current_chunk_segments,
                    self.overlap_tokens
                )
                current_chunk_segments = overlap_segments
                current_chunk_tokens = sum(
                    self.count_tokens(s.text) for s in overlap_segments
                )
                chunk_id += 1
            
            current_chunk_segments.append(segment)
            current_chunk_tokens += segment_tokens
        
        # Add final chunk
        if current_chunk_segments:
            chunk = self._create_chunk(
                chunk_id=chunk_id,
                total_chunks=num_chunks,
                segments=current_chunk_segments,
                speakers=speakers
            )
            chunks.append(chunk)
        
        logger.info(f"Created {len(chunks)} chunks")
        return chunks
    
    def _create_chunk(
        self,
        chunk_id: int,
        total_chunks: int,
        segments: List[TranscriptionSegment],
        speakers: List[str]
    ) -> TranscriptionChunk:
        """Create a TranscriptionChunk from segments."""
        text = ' '.join(s.text for s in segments)
        tokens = self.count_tokens(text)
        
        # Extract speakers in this chunk
        chunk_speakers = list(set(
            s.speaker for s in segments if s.speaker
        ))
        
        return TranscriptionChunk(
            chunk_id=chunk_id,
            total_chunks=total_chunks,
            text=text,
            tokens=tokens,
            segments=segments,
            speakers=chunk_speakers,
            timestamp_range=(
                segments[0].start_time,
                segments[-1].end_time
            ),
            metadata={
                'num_segments': len(segments),
                'avg_confidence': sum(s.confidence for s in segments) / len(segments)
                if segments else 0.0
            }
        )
    
    def _get_overlap_segments(
        self,
        segments: List[TranscriptionSegment],
        target_overlap_tokens: int
    ) -> List[TranscriptionSegment]:
        """Get last N segments that sum to approximately target_overlap_tokens."""
        overlap = []
        tokens = 0
        
        for segment in reversed(segments):
            segment_tokens = self.count_tokens(segment.text)
            if tokens + segment_tokens > target_overlap_tokens:
                break
            overlap.insert(0, segment)
            tokens += segment_tokens
        
        return overlap
    
    def format_with_timestamps(
        self,
        segments: List[TranscriptionSegment],
        include_speakers: bool = True
    ) -> str:
        """
        Format segments with timestamps for display or processing.
        
        Args:
            segments: List of TranscriptionSegment objects
            include_speakers: Whether to include speaker labels
            
        Returns:
            Formatted string with timestamps
        """
        formatted_lines = []
        
        for segment in segments:
            timestamp = self._format_timestamp(segment.start_time)
            
            if include_speakers and segment.speaker:
                line = f"[{timestamp}] {segment.speaker}: {segment.text}"
            else:
                line = f"[{timestamp}] {segment.text}"
            
            formatted_lines.append(line)
        
        return '\n'.join(formatted_lines)
    
    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        """Format seconds as HH:MM:SS."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"


# Utility functions

def load_transcription_from_s3(
    s3_client,
    bucket: str,
    key: str
) -> Dict[str, Any]:
    """
    Load transcription JSON from S3.
    
    Args:
        s3_client: boto3 S3 client
        bucket: S3 bucket name
        key: S3 object key
        
    Returns:
        Parsed JSON dictionary
    """
    logger.info(f"Loading transcription from s3://{bucket}/{key}")
    
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        json_content = response['Body'].read().decode('utf-8')
        return json.loads(json_content)
    except Exception as e:
        logger.error(f"Error loading transcription from S3: {str(e)}")
        raise


def parse_s3_uri(s3_uri: str) -> Tuple[str, str]:
    """
    Parse S3 URI into bucket and key.
    
    Supports both formats:
    - s3://bucket/key
    - https://s3.region.amazonaws.com/bucket/key
    - https://bucket.s3.region.amazonaws.com/key
    
    Args:
        s3_uri: S3 URI in any supported format
        
    Returns:
        Tuple of (bucket, key)
    """
    # Handle s3:// format
    if s3_uri.startswith('s3://'):
        parts = s3_uri[5:].split('/', 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid S3 URI format: {s3_uri}")
        return parts[0], parts[1]
    
    # Handle https:// format
    if s3_uri.startswith('https://'):
        # Pattern 1: https://s3.region.amazonaws.com/bucket/key
        pattern1 = r'https://s3[.-]([^.]+)\.amazonaws\.com/([^/]+)/(.+)'
        match = re.match(pattern1, s3_uri)
        if match:
            return match.group(2), match.group(3)
        
        # Pattern 2: https://bucket.s3.region.amazonaws.com/key
        pattern2 = r'https://([^.]+)\.s3[.-]([^.]+)\.amazonaws\.com/(.+)'
        match = re.match(pattern2, s3_uri)
        if match:
            return match.group(1), match.group(3)
    
    raise ValueError(f"Invalid S3 URI: {s3_uri}")