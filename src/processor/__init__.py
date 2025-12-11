"""
AI Techne Academy - ECS Processor Module

This module contains the main processing logic for generating
technical training and troubleshooting documents from video transcriptions.

Main components:
- transcription_parser: Parse and chunk AWS Transcribe output
- llm_client: AWS Bedrock (Claude Sonnet 4) client with LangChain
- document_generator: 6-stage pipeline for document generation
- main: Entry point and orchestration

Author: AI Techne Academy
Version: 1.0.0
"""

__version__ = '1.0.0'
__author__ = 'AI Techne Academy'

from .transcription_parser import TranscriptionParser, TranscriptionSegment, TranscriptionChunk
from .llm_client import BedrockLLMClient, TokenUsage, RateLimiter
from .document_generator import DocumentGenerator, DocumentGenerationResult, StageResult
from .main import lambda_handler

__all__ = [
    'TranscriptionParser',
    'TranscriptionSegment',
    'TranscriptionChunk',
    'BedrockLLMClient',
    'TokenUsage',
    'RateLimiter',
    'DocumentGenerator',
    'DocumentGenerationResult',
    'StageResult',
    'lambda_handler',
]