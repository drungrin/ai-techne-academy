"""
LLM Client for AWS Bedrock using LangChain

This module provides a client for interacting with AWS Bedrock's Claude Sonnet 4
model using LangChain. Includes retry logic, rate limiting, streaming support,
and circuit breaker for quota protection.

Author: AI Techne Academy
Version: 1.1.0
"""

import json
import logging
import time
import boto3
from botocore.config import Config
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List

from langchain.schema import HumanMessage, SystemMessage
from langchain_aws import ChatBedrock

from circuit_breaker import BedrockCircuitBreaker, CircuitBreakerOpen

logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    """Track token usage for cost calculation."""

    input_tokens: int
    output_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def calculate_cost(self) -> float:
        """
        Calculate cost in USD.

        Pricing for Claude Sonnet 4:
        - Input: $0.003 per 1K tokens
        - Output: $0.015 per 1K tokens
        """
        input_cost = (self.input_tokens / 1000) * 0.003
        output_cost = (self.output_tokens / 1000) * 0.015
        return round(input_cost + output_cost, 4)


class RateLimiter:
    """
    Rate limiter for Bedrock API calls.

    Default limits:
    - 10 requests per minute
    - 100K tokens per minute (input + output)
    """

    def __init__(
        self,
        requests_per_minute: int = 10,
        tokens_per_minute: int = 100000
    ):
        self.requests_per_minute = requests_per_minute
        self.tokens_per_minute = tokens_per_minute

        self.request_times: List[float] = []
        self.token_counts: List[tuple] = []  # (timestamp, token_count)

    def acquire(self, estimated_tokens: int = 0):
        """
        Wait if necessary before making a request.

        Args:
            estimated_tokens: Estimated tokens for this request
        """
        now = time.time()
        one_minute_ago = now - 60

        # Clean old entries
        self.request_times = [t for t in self.request_times if t > one_minute_ago]
        self.token_counts = [(t, c) for t, c in self.token_counts if t > one_minute_ago]

        # Check request rate
        if len(self.request_times) >= self.requests_per_minute:
            sleep_time = 60 - (now - self.request_times[0])
            if sleep_time > 0:
                logger.info(f"Rate limit reached. Sleeping {sleep_time:.2f}s")
                time.sleep(sleep_time)
                now = time.time()

        # Check token rate
        tokens_used = sum(c for _, c in self.token_counts)
        if tokens_used + estimated_tokens > self.tokens_per_minute:
            # Wait until oldest token count expires
            if self.token_counts:
                sleep_time = 60 - (now - self.token_counts[0][0])
                if sleep_time > 0:
                    logger.info(f"Token limit reached. Sleeping {sleep_time:.2f}s")
                    time.sleep(sleep_time)
                    now = time.time()

        # Record this request
        self.request_times.append(now)
        if estimated_tokens > 0:
            self.token_counts.append((now, estimated_tokens))


class BedrockLLMClient:
    """
    LangChain client for AWS Bedrock Claude Sonnet 4.

    Features:
    - Automatic retry with exponential backoff
    - Rate limiting
    - Streaming support
    - Token tracking
    - Error handling
    """

    def __init__(
        self,
        model_id: str = "anthropic.claude-sonnet-4-5-20250929-v1:0",
        region: str = "us-east-1",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        top_p: float = 0.95,
        top_k: int = 250,
        enable_rate_limiting: bool = True,
        enable_circuit_breaker: bool = True,
        max_retries: int = 3
    ):
        """
        Initialize Bedrock client.

        Args:
            model_id: Bedrock model identifier (or inference profile ARN)
            region: AWS region
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens in response
            top_p: Nucleus sampling parameter
            top_k: Top-k sampling parameter
            enable_rate_limiting: Enable rate limiting
            enable_circuit_breaker: Enable circuit breaker for quota protection
            max_retries: Maximum retry attempts
            read_timeout: Socket read timeout in seconds (default 900s)
        """
        self.model_id = model_id
        self.region = region
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries

        # Convert model ID to inference profile ARN if needed
        if model_id == "anthropic.claude-sonnet-4-5-20250929-v1:0":
            inference_profile = f"us.{model_id}"
            logger.info(f"Converting model ID to inference profile: {inference_profile}")
        elif model_id.startswith("arn:"):
            inference_profile = model_id
        else:
            inference_profile = model_id

        # Cria uma configuração personalizada do Boto3 para aumentar o timeout
        boto_config = Config(
            read_timeout=read_timeout,  # Evita o erro de timeout em requests longos
            connect_timeout=10,
            retries={
                'max_attempts': max_retries,
                'mode': 'standard'
            }
        )

        # Instancia o cliente boto3 explicitamente com a config
        bedrock_client = boto3.client(
            service_name='bedrock-runtime',
            region_name=region,
            config=boto_config
        )

        # Inicializa o LangChain injetando o cliente configurado
        self.model = ChatBedrock(
            client=bedrock_client,
            model_id=inference_profile,
            region_name=region,
            model_kwargs={
                "temperature": temperature,
                "max_tokens": max_tokens,
                "top_k": top_k
            }
        )

        # Rate limiter
        self.rate_limiter = RateLimiter() if enable_rate_limiting else None

        # Circuit breaker for quota protection
        self.circuit_breaker = BedrockCircuitBreaker(
            failure_threshold=5,
            timeout=300
        ) if enable_circuit_breaker else None

        # Track usage
        self.total_usage = TokenUsage(input_tokens=0, output_tokens=0)

        # Logging configuration
        self.logging_folder: Optional[str] = None
        self.stage_context: Optional[str] = None

        logger.info(
            f"Initialized Bedrock client: {model_id} in {region} "
            f"(circuit_breaker={'enabled' if enable_circuit_breaker else 'disabled'})"
        )

    def set_logging_folder(self, folder_path: str) -> None:
        """Set the base folder for logging chat interactions."""
        self.logging_folder = folder_path
        logger.info(f"LLM logging folder set to: {folder_path}")

    def set_stage_context(self, stage: str) -> None:
        """Set the current stage context for logging."""
        self.stage_context = stage
        logger.debug(f"LLM stage context set to: {stage}")

    def _log_chat_messages(
        self,
        prompt: str,
        system_prompt: Optional[str],
        response_text: str,
        error: Optional[str] = None
    ) -> None:
        """Log raw chat messages (input and output) to files."""
        if not self.logging_folder or not self.stage_context:
            return

        try:
            stage_dir = Path(self.logging_folder) / self.stage_context
            stage_dir.mkdir(parents=True, exist_ok=True)

            # Input content
            input_content = ""
            if system_prompt:
                input_content += f"# System Prompt\n\n{system_prompt}\n\n---\n\n"
            input_content += f"# User Prompt\n\n{prompt}"

            input_file = stage_dir / "chat_input.md"
            with open(input_file, 'w', encoding='utf-8') as f:
                f.write(input_content)

            # Output content
            output_content = ""
            if error:
                output_content = f"# ERROR\n\n{error}\n\n---\n\n# Partial Response (if any)\n\n{response_text}"
            else:
                output_content = f"# Response\n\n{response_text}"

            output_file = stage_dir / "chat_output.md"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(output_content)

            logger.info(f"Chat messages logged to {stage_dir}")

        except Exception as e:
            logger.warning(f"Failed to log chat messages: {str(e)}")

    def invoke(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None
    ) -> tuple[str, TokenUsage]:
        """
        Invoke the model with retry logic and circuit breaker protection.
        """
        logger.info(f"Invoking Bedrock model (prompt length: {len(prompt)} chars)")

        if self.circuit_breaker:
            try:
                return self.circuit_breaker.call(
                    self._invoke_internal,
                    prompt,
                    system_prompt,
                    temperature
                )
            except CircuitBreakerOpen:
                logger.error("Circuit breaker OPEN - Bedrock quota likely exceeded")
                raise
        else:
            return self._invoke_internal(prompt, system_prompt, temperature)

    def _invoke_internal(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None
    ) -> tuple[str, TokenUsage]:
        """Internal invoke implementation with retry logic."""

        estimated_tokens = self.estimate_tokens(prompt)
        if self.rate_limiter:
            self.rate_limiter.acquire(estimated_tokens)

        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))

        if temperature is not None:
            original_temp = self.model.model_kwargs.get("temperature")
            self.model.model_kwargs["temperature"] = temperature

        last_exception = None
        for attempt in range(self.max_retries):
            try:
                # O timeout configurado no init será respeitado aqui
                response = self.model.invoke(messages)

                response_text = response.content

                input_tokens = self.estimate_tokens(prompt)
                if system_prompt:
                    input_tokens += self.estimate_tokens(system_prompt)
                output_tokens = self.estimate_tokens(response_text)

                usage = TokenUsage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens
                )

                self.total_usage.input_tokens += usage.input_tokens
                self.total_usage.output_tokens += usage.output_tokens

                logger.info(
                    f"Bedrock response received: {len(response_text)} chars, "
                    f"{usage.total_tokens} tokens, ${usage.calculate_cost():.4f}"
                )

                self._log_chat_messages(prompt, system_prompt, response_text)

                if temperature is not None:
                    self.model.model_kwargs["temperature"] = original_temp

                return response_text, usage

            except Exception as e:
                last_exception = e
                error_name = type(e).__name__

                if "ValidationException" in error_name or "InvalidRequest" in error_name:
                    logger.error(f"Validation error: {str(e)}")
                    raise

                # O ReadTimeoutError será pego aqui se ainda assim estourar 15min
                if attempt < self.max_retries - 1:
                    sleep_time = 2 ** attempt
                    logger.warning(
                        f"Bedrock error ({error_name}), "
                        f"retry {attempt + 1}/{self.max_retries} in {sleep_time}s: {str(e)}"
                    )
                    time.sleep(sleep_time)
                else:
                    logger.error(f"All retries failed: {str(e)}")

        if last_exception:
            self._log_chat_messages(
                prompt,
                system_prompt,
                response_text="",
                error=str(last_exception)
            )

        if temperature is not None:
            self.model.model_kwargs["temperature"] = original_temp

        raise last_exception

    def invoke_with_streaming(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        callback: Optional[Callable[[str], None]] = None
    ) -> tuple[str, TokenUsage]:
        """Invoke model with streaming."""
        logger.info(f"Invoking Bedrock with streaming (prompt: {len(prompt)} chars)")

        estimated_tokens = self.estimate_tokens(prompt)
        if self.rate_limiter:
            self.rate_limiter.acquire(estimated_tokens)

        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))

        full_response = ""
        try:
            # Streaming geralmente sofre menos com ReadTimeout,
            # pois recebe o primeiro byte rápido.
            for chunk in self.model.stream(messages):
                chunk_text = chunk.content
                full_response += chunk_text

                if callback:
                    callback(chunk_text)

            input_tokens = self.estimate_tokens(prompt)
            if system_prompt:
                input_tokens += self.estimate_tokens(system_prompt)
            output_tokens = self.estimate_tokens(full_response)

            usage = TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens
            )

            self.total_usage.input_tokens += usage.input_tokens
            self.total_usage.output_tokens += usage.output_tokens

            logger.info(
                f"Streaming complete: {len(full_response)} chars, "
                f"{usage.total_tokens} tokens"
            )

            return full_response, usage

        except Exception as e:
            logger.error(f"Streaming error: {str(e)}")
            raise

    def invoke_with_json_output(
        self,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> tuple[Dict[str, Any], TokenUsage]:
        """Invoke model expecting JSON response."""
        response_text, usage = self.invoke(prompt, system_prompt)

        json_text = response_text.strip()

        if json_text.startswith("```json"):
            json_text = json_text[7:]
        elif json_text.startswith("```"):
            json_text = json_text[3:]

        if json_text.endswith("```"):
            json_text = json_text[:-3]

        json_text = json_text.strip()

        try:
            parsed = json.loads(json_text)
            return parsed, usage
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {str(e)}")
            logger.debug(f"Response text: {response_text}")
            raise

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimate token count for text."""
        return len(text) // 4

    def get_total_usage(self) -> TokenUsage:
        return self.total_usage

    def get_total_cost(self) -> float:
        return self.total_usage.calculate_cost()

    def reset_usage(self):
        self.total_usage = TokenUsage(input_tokens=0, output_tokens=0)
        logger.info("Usage tracking reset")

    def get_circuit_breaker_state(self) -> Optional[dict]:
        if self.circuit_breaker:
            return self.circuit_breaker.get_state()
        return None


class PromptTemplate:
    """Helper class for managing prompts with variables."""

    def __init__(self, template: str):
        self.template = template

    def format(self, **kwargs) -> str:
        try:
            return self.template.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"Missing template variable: {e}")

    def get_variables(self) -> List[str]:
        import re
        return re.findall(r'\{(\w+)\}', self.template)


# Utility functions

def create_system_prompt(role: str, instructions: str) -> str:
    """Create a structured system prompt."""
    return f"""You are a {role}.

{instructions}

Always provide accurate, well-structured responses based on the input provided."""


def create_xml_prompt(
    task: str,
    instructions: str,
    output_format: str,
    input_data: str,
    input_tag: str = "input"
) -> str:
    """Create XML-structured prompt (Claude best practice)."""
    return f"""<task>
{task}
</task>

<instructions>
{instructions}
</instructions>

<output_format>
{output_format}
</output_format>

<{input_tag}>
{input_data}
</{input_tag}>"""


def extract_xml_content(response: str, tag: str) -> Optional[str]:
    """Extract content from XML tags in response."""
    import re
    pattern = f"<{tag}>(.*?)</{tag}>"
    match = re.search(pattern, response, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None