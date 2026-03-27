"""Unit tests for Overmind Lab tracing client."""

from uuid import uuid4


from src.tracing.overmind_client import OvermindClient, Span, TraceContext


def test_trace_context_creation():
    """Test trace context creation."""
    request_id = uuid4()
    trace = TraceContext(request_id, "test_operation")

    assert trace.request_id == request_id
    assert trace.operation_name == "test_operation"
    assert trace.start_time > 0
    assert len(trace.spans) == 0
    assert len(trace.metadata) == 0


def test_trace_context_create_span():
    """Test creating spans within a trace."""
    request_id = uuid4()
    trace = TraceContext(request_id, "test_operation")

    span = trace.create_span("test_span")

    assert span.span_name == "test_span"
    assert span.trace_id == request_id
    assert span.span_id in trace.spans
    assert trace.spans[span.span_id] == span


def test_trace_context_create_child_span():
    """Test creating child spans."""
    request_id = uuid4()
    trace = TraceContext(request_id, "test_operation")

    parent_span = trace.create_span("parent_span")
    child_span = trace.create_span("child_span", parent_span_id=parent_span.span_id)

    assert child_span.parent_span_id == parent_span.span_id
    assert child_span.trace_id == request_id


def test_trace_context_end_trace():
    """Test ending a trace."""
    request_id = uuid4()
    trace = TraceContext(request_id, "test_operation")

    # Should not raise exception
    trace.end_trace("success")


def test_span_creation():
    """Test span creation."""
    trace_id = uuid4()
    span = Span(
        span_id="test_span_id",
        span_name="test_span",
        trace_id=trace_id,
    )

    assert span.span_id == "test_span_id"
    assert span.span_name == "test_span"
    assert span.trace_id == trace_id
    assert span.parent_span_id is None
    assert span.start_time > 0
    assert span.end_time is None
    assert span.status is None


def test_span_set_attribute():
    """Test setting span attributes."""
    span = Span(
        span_id="test_span_id",
        span_name="test_span",
        trace_id=uuid4(),
    )

    span.set_attribute("key1", "value1")
    span.set_attribute("key2", 42)

    assert span.metadata["key1"] == "value1"
    assert span.metadata["key2"] == 42


def test_span_end_span():
    """Test ending a span."""
    span = Span(
        span_id="test_span_id",
        span_name="test_span",
        trace_id=uuid4(),
    )

    span.end_span("success")

    assert span.status == "success"
    assert span.end_time is not None
    assert span.end_time > span.start_time


def test_overmind_client_disabled():
    """Test Overmind client when disabled (no API key)."""
    client = OvermindClient(api_key=None)

    assert client.enabled is False


def test_overmind_client_enabled():
    """Test Overmind client when enabled."""
    client = OvermindClient(api_key="test_key")

    assert client.enabled is True


def test_overmind_client_start_trace():
    """Test starting a trace."""
    client = OvermindClient(api_key="test_key")
    request_id = uuid4()

    trace = client.start_trace(request_id, "test_operation")

    assert trace.request_id == request_id
    assert trace.operation_name == "test_operation"


def test_overmind_client_log_agent_dispatch():
    """Test logging agent dispatch."""
    client = OvermindClient(api_key="test_key")
    request_id = uuid4()
    trace = client.start_trace(request_id, "test_operation")

    span = client.log_agent_dispatch(trace, "spotify", "Test Song")

    assert span.span_name == "agent_dispatch_spotify"
    assert span.metadata["agent_name"] == "spotify"
    assert span.metadata["song_name"] == "Test Song"


def test_overmind_client_log_agent_response():
    """Test logging agent response."""
    client = OvermindClient(api_key="test_key")
    request_id = uuid4()
    trace = client.start_trace(request_id, "test_operation")
    span = client.log_agent_dispatch(trace, "spotify", "Test Song")

    client.log_agent_response(span, 150, "success", 0.85)

    assert span.metadata["response_time_ms"] == 150
    assert span.metadata["status"] == "success"
    assert span.metadata["completeness"] == 0.85
    assert span.status == "success"
    assert span.end_time is not None


def test_overmind_client_log_metric():
    """Test logging metrics."""
    client = OvermindClient(api_key="test_key")

    # Should not raise exception
    client.log_metric("test_metric", 42.5, tags={"env": "test"})


def test_overmind_client_log_event():
    """Test logging events."""
    client = OvermindClient(api_key="test_key")

    # Should not raise exception
    client.log_event("test_event", {"key": "value"})


def test_overmind_client_disabled_operations():
    """Test that disabled client still works without errors."""
    client = OvermindClient(api_key=None)
    request_id = uuid4()

    # All operations should work without errors
    trace = client.start_trace(request_id, "test_operation")
    span = client.log_agent_dispatch(trace, "spotify", "Test Song")
    client.log_agent_response(span, 150, "success", 0.85)
    client.log_metric("test_metric", 42.5)
    client.log_event("test_event", {"key": "value"})
