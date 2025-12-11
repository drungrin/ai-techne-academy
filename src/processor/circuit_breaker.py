"""
Circuit Breaker Pattern for Bedrock API Protection

Protects against cascading failures when Bedrock quotas are exceeded.
Implements the Circuit Breaker pattern with three states:
- CLOSED: Normal operation
- OPEN: Quota exceeded, blocking calls
- HALF_OPEN: Testing if service recovered

Author: AI Techne Academy
Version: 1.0.0
"""

import time
import logging
from enum import Enum
from typing import Callable, Any, List

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    
    CLOSED = "CLOSED"        # Normal operation
    OPEN = "OPEN"            # Quota exceeded, blocking calls
    HALF_OPEN = "HALF_OPEN"  # Testing if quota recovered


class CircuitBreakerOpen(Exception):
    """Exception raised when circuit breaker is open."""
    
    def __init__(self, message: str, time_remaining: float = 0):
        self.time_remaining = time_remaining
        super().__init__(message)


class BedrockCircuitBreaker:
    """
    Circuit breaker for Bedrock API calls.
    
    Prevents cascading failures when quota is exceeded by:
    1. Tracking consecutive failures
    2. Opening circuit after threshold is reached
    3. Attempting reset after timeout period
    4. Gracefully failing fast when circuit is open
    
    Usage:
        breaker = BedrockCircuitBreaker(failure_threshold=5, timeout=300)
        
        def call_bedrock():
            # Your Bedrock API call here
            pass
        
        try:
            result = breaker.call(call_bedrock)
        except CircuitBreakerOpen as e:
            logger.error(f"Circuit open: {e}")
            # Handle gracefully
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: int = 300,
        expected_error_codes: List[str] = None
    ):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            timeout: Seconds to wait before attempting reset (default: 5 minutes)
            expected_error_codes: List of error codes/names to track
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.expected_errors = expected_error_codes or [
            'ThrottlingException',
            'TooManyRequestsException',
            'ServiceQuotaExceededException',
            'ModelStreamErrorException',
            'ModelTimeoutException'
        ]
        
        # State tracking
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED
        self.last_success_time = None
        
        logger.info(
            f"Circuit breaker initialized: threshold={failure_threshold}, "
            f"timeout={timeout}s"
        )
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.
        
        Args:
            func: Function to call
            *args: Positional arguments for function
            **kwargs: Keyword arguments for function
            
        Returns:
            Function result
            
        Raises:
            CircuitBreakerOpen: If circuit is open
            Exception: Any exception from the called function
        """
        # Check circuit state
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                logger.info("Circuit breaker transitioning to HALF_OPEN (testing recovery)")
                self.state = CircuitState.HALF_OPEN
            else:
                time_remaining = self.timeout - (time.time() - self.last_failure_time)
                raise CircuitBreakerOpen(
                    f"Circuit breaker OPEN: Bedrock quota likely exceeded. "
                    f"Automatic retry in {time_remaining:.0f}s. "
                    f"Failed {self.failure_count} times.",
                    time_remaining=time_remaining
                )
        
        # Attempt call
        try:
            result = func(*args, **kwargs)
            
            # Success - reset if in HALF_OPEN
            if self.state == CircuitState.HALF_OPEN:
                logger.info("Circuit breaker reset to CLOSED (service recovered)")
                self._reset()
            
            self.last_success_time = time.time()
            return result
            
        except Exception as e:
            error_name = type(e).__name__
            error_str = str(e)
            
            # Check if this is a quota-related error
            is_quota_error = any(
                err in error_str or err == error_name 
                for err in self.expected_errors
            )
            
            if is_quota_error:
                self._record_failure()
                logger.warning(
                    f"Circuit breaker failure {self.failure_count}/{self.failure_threshold}: "
                    f"{error_name} - {error_str}"
                )
                
                if self.state == CircuitState.OPEN:
                    logger.error(
                        f"Circuit breaker OPENED after {self.failure_count} consecutive failures"
                    )
            
            raise
    
    def _record_failure(self):
        """Record a failure and potentially open circuit."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.critical(
                f"⚠️ CIRCUIT BREAKER OPENED ⚠️\n"
                f"Bedrock quota likely exceeded after {self.failure_count} failures.\n"
                f"Circuit will auto-retry in {self.timeout}s.\n"
                f"Consider: 1) Requesting quota increase, 2) Reducing concurrent load"
            )
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self.last_failure_time is None:
            return True
        
        elapsed = time.time() - self.last_failure_time
        return elapsed >= self.timeout
    
    def _reset(self):
        """Reset circuit breaker to CLOSED state."""
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED
        logger.info("Circuit breaker fully reset")
    
    def get_state(self) -> dict:
        """
        Get current circuit breaker state.
        
        Returns:
            Dictionary with state information
        """
        uptime = None
        if self.last_success_time:
            uptime = time.time() - self.last_success_time
        
        time_since_failure = None
        if self.last_failure_time:
            time_since_failure = time.time() - self.last_failure_time
        
        return {
            'state': self.state.value,
            'failure_count': self.failure_count,
            'threshold': self.failure_threshold,
            'timeout_seconds': self.timeout,
            'last_failure_time': self.last_failure_time,
            'last_success_time': self.last_success_time,
            'time_since_failure_seconds': time_since_failure,
            'uptime_seconds': uptime,
            'is_healthy': self.state == CircuitState.CLOSED
        }
    
    def force_open(self):
        """Manually open the circuit breaker."""
        logger.warning("Circuit breaker manually opened")
        self.state = CircuitState.OPEN
        self.failure_count = self.failure_threshold
        self.last_failure_time = time.time()
    
    def force_reset(self):
        """Manually reset the circuit breaker."""
        logger.info("Circuit breaker manually reset")
        self._reset()
    
    def __repr__(self) -> str:
        return (
            f"BedrockCircuitBreaker("
            f"state={self.state.value}, "
            f"failures={self.failure_count}/{self.failure_threshold})"
        )