"""Overmind Lab tracing client for distributed tracing and monitoring."""

import logging
import time
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from config.settings import settings

logger = logging.getLogger(__name__)


class TraceContext:
    """Context for a distributed trace."""

    def __init__(self, request_id: UUID, operation_name: str):
        """Initialize trace context.

        Args:
            request_id: Unique request identifier
            operation_name: Name of the operation being traced
        """
        self.request_id = request_id
        self.operation_name = operation_name
        self.start_time = time.time()
        self.spans: Dict[str, "Span"] = {}
        self.metadata: Dict[str, Any] = {}

    def create_span(self, span_name: str, parent_span_id: Optional[str] = None) -> "Span":
        """Create a child span within this trace.

        Args:
            span_name: Name of the span
            parent_span_id: Optional parent span ID

        Returns:
            New Span instance
        """
        span = Span(
            span_id=str(uuid4()),
            span_name=span_name,
            trace_id=self.request_id,
            parent_span_id=parent_span_id,
        )
        self.spans[span.span_id] = span
        return span

    def end_trace(self, status: str) -> None:
        """End the trace with a status.

        Args:
            status: Trace status (success, failure, timeout, etc.)
        """
        duration_ms = (time.time() - self.start_time) * 1000
        logger.info(
            f"Trace ended: {self.operation_name} "
            f"[{self.request_id}] "
            f"status={status} "
            f"duration={duration_ms:.2f}ms "
            f"spans={len(self.spans)}"
        )


class Span:
    """Represents a span within a distributed trace."""

    def __init__(
        self,
        span_id: str,
        span_name: str,
        trace_id: UUID,
        parent_span_id: Optional[str] = None,
    ):
        """Initialize span.

        Args:
            span_id: Unique span identifier
            span_name: Name of the span
            trace_id: Parent trace ID
            parent_span_id: Optional parent span ID
        """
        self.span_id = span_id
        self.span_name = span_name
        self.trace_id = trace_id
        self.parent_span_id = parent_span_id
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.status: Optional[str] = None
        self.metadata: Dict[str, Any] = {}

    def set_attribute(self, key: str, value: Any) -> None:
        """Set an attribute on the span.

        Args:
            key: Attribute key
            value: Attribute value
        """
        self.metadata[key] = value

    def end_span(self, status: str) -> None:
        """End the span with a status.

        Args:
            status: Span status (success, failure, timeout, etc.)
        """
        self.end_time = time.time()
        self.status = status
        duration_ms = (self.end_time - self.start_time) * 1000
        logger.debug(
            f"Span ended: {self.span_name} "
            f"[{self.span_id}] "
            f"status={status} "
            f"duration={duration_ms:.2f}ms"
        )


class OvermindClient:
    """Client for Overmind Lab distributed tracing and monitoring."""

    def __init__(
        self,
        api_key: Optional[str] = settings.overmind_api_key,
        endpoint: str = settings.overmind_endpoint,
    ):
        """Initialize Overmind Lab client.

        Args:
            api_key: Overmind Lab API key
            endpoint: Overmind Lab API endpoint
        """
        self.api_key = api_key
        self.endpoint = endpoint
        self.enabled = api_key is not None

        if not self.enabled:
            logger.warning("Overmind Lab tracing disabled (no API key configured)")

    def start_trace(self, request_id: UUID, operation_name: str) -> TraceContext:
        """Start a new distributed trace.

        Args:
            request_id: Unique request identifier
            operation_name: Name of the operation being traced

        Returns:
            TraceContext instance
        """
        trace = TraceContext(request_id, operation_name)

        if self.enabled:
            logger.info(f"Started trace: {operation_name} [{request_id}]")
        else:
            logger.debug(f"Trace (disabled): {operation_name} [{request_id}]")

        return trace

    def log_agent_dispatch(
        self, trace: TraceContext, agent_name: str, song_name: str
    ) -> Span:
        """Log agent dispatch as a child span.

        Args:
            trace: Parent trace context
            agent_name: Name of the agent being dispatched
            song_name: Song name being enriched

        Returns:
            Span for the agent dispatch
        """
        span = trace.create_span(f"agent_dispatch_{agent_name}")
        span.set_attribute("agent_name", agent_name)
        span.set_attribute("song_name", song_name)

        if self.enabled:
            logger.debug(f"Agent dispatched: {agent_name} for '{song_name}'")

        return span

    def log_agent_response(
        self, span: Span, response_time_ms: int, status: str, completeness: float
    ) -> None:
        """Log agent response metrics.

        Args:
            span: Agent dispatch span
            response_time_ms: Response time in milliseconds
            status: Agent status (success, partial, failed)
            completeness: Completeness score
        """
        span.set_attribute("response_time_ms", response_time_ms)
        span.set_attribute("status", status)
        span.set_attribute("completeness", completeness)
        span.end_span(status)

        if self.enabled:
            logger.info(
                f"Agent response: {span.metadata.get('agent_name')} "
                f"status={status} "
                f"time={response_time_ms}ms "
                f"completeness={completeness:.2f}"
            )

    def log_metric(self, metric_name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Log a metric to Overmind Lab.

        Args:
            metric_name: Name of the metric
            value: Metric value
            tags: Optional tags for the metric
        """
        if self.enabled:
            logger.debug(f"Metric: {metric_name}={value} tags={tags}")
        else:
            logger.debug(f"Metric (disabled): {metric_name}={value}")

    def log_event(self, event_name: str, properties: Dict[str, Any]) -> None:
        """Log an event to Overmind Lab.

        Args:
            event_name: Name of the event
            properties: Event properties
        """
        if self.enabled:
            logger.info(f"Event: {event_name} properties={properties}")
        else:
            logger.debug(f"Event (disabled): {event_name}")


# Global Overmind client instance
overmind_client = OvermindClient()
