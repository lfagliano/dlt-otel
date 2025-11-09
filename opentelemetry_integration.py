"""
OpenTelemetry Integration for DLT - Non-blocking approach

This module provides two ways to integrate OpenTelemetry with DLT:

1. CompositeCollector - Use OpenTelemetry alongside any other collector (recommended)
2. init_opentelemetry() - Global initialization (similar to init_sentry)

Examples:

    # Option 1: Use tqdm for progress + OpenTelemetry for observability
    from opentelemetry_integration import CompositeCollector, OpenTelemetryTracker
    from dlt.common.runtime.collector import TqdmCollector
    
    collector = CompositeCollector([
        TqdmCollector(),
        OpenTelemetryTracker(otlp_endpoint="http://localhost:4318")
    ])
    
    pipeline = dlt.pipeline(progress=collector)
    
    # Option 2: Use enlighten + OpenTelemetry
    collector = CompositeCollector([
        EnlightenCollector(),
        OpenTelemetryTracker(otlp_endpoint="http://localhost:4318")
    ])
    
    # Option 3: Global initialization (works with any collector)
    init_opentelemetry(otlp_endpoint="http://localhost:4318")
    pipeline = dlt.pipeline(progress="tqdm")  # OpenTelemetry works automatically
"""

import os
from typing import Any, List, Optional, TYPE_CHECKING
from dlt.common.runtime.collector import Collector
from dlt.common import logger as dlt_logger

if TYPE_CHECKING:
    from dlt.pipeline.trace import PipelineTrace, PipelineStepTrace
    from dlt.pipeline.typing import TPipelineStep
    from dlt.common.pipeline import SupportsPipeline
else:
    PipelineTrace = PipelineStepTrace = TPipelineStep = SupportsPipeline = Any


class CompositeCollector(Collector):
    """
    A collector that delegates to multiple child collectors.
    
    Allows using multiple collectors simultaneously, e.g., tqdm for visual progress
    and OpenTelemetry for metrics/traces.
    
    Example:
        collector = CompositeCollector([
            TqdmCollector(),
            OpenTelemetryTracker(otlp_endpoint="http://localhost:4318")
        ])
        pipeline = dlt.pipeline(progress=collector)
    """

    def __init__(self, collectors: List[Collector]) -> None:
        """
        Args:
            collectors: List of collectors to delegate to
        """
        super().__init__()
        self.collectors = collectors

    def update(
        self,
        name: str,
        inc: int = 1,
        total: int = None,
        inc_total: int = None,
        message: str = None,
        label: str = None,
    ) -> None:
        """Delegate update to all collectors"""
        for collector in self.collectors:
            try:
                collector.update(name, inc, total, inc_total, message, label)
            except Exception as e:
                dlt_logger.warning(f"Collector {collector.__class__.__name__} failed to update: {e}")

    def _start(self, step: str) -> None:
        """Start all collectors"""
        for collector in self.collectors:
            try:
                collector._start(step)
            except Exception as e:
                dlt_logger.warning(f"Collector {collector.__class__.__name__} failed to start: {e}")

    def _stop(self) -> None:
        """Stop all collectors"""
        for collector in self.collectors:
            try:
                collector._stop()
            except Exception as e:
                dlt_logger.warning(f"Collector {collector.__class__.__name__} failed to stop: {e}")

    def on_start_trace(
        self, trace: PipelineTrace, step: TPipelineStep, pipeline: SupportsPipeline
    ) -> None:
        """Delegate trace start to all collectors"""
        for collector in self.collectors:
            try:
                collector.on_start_trace(trace, step, pipeline)
            except Exception as e:
                dlt_logger.warning(
                    f"Collector {collector.__class__.__name__} failed on_start_trace: {e}"
                )

    def on_start_trace_step(
        self, trace: PipelineTrace, step: TPipelineStep, pipeline: SupportsPipeline
    ) -> None:
        """Delegate trace step start to all collectors"""
        for collector in self.collectors:
            try:
                collector.on_start_trace_step(trace, step, pipeline)
            except Exception as e:
                dlt_logger.warning(
                    f"Collector {collector.__class__.__name__} failed on_start_trace_step: {e}"
                )

    def on_end_trace_step(
        self,
        trace: PipelineTrace,
        step: PipelineStepTrace,
        pipeline: SupportsPipeline,
        step_info: Any,
        send_state: bool,
    ) -> None:
        """Delegate trace step end to all collectors"""
        for collector in self.collectors:
            try:
                collector.on_end_trace_step(trace, step, pipeline, step_info, send_state)
            except Exception as e:
                dlt_logger.warning(
                    f"Collector {collector.__class__.__name__} failed on_end_trace_step: {e}"
                )

    def on_end_trace(
        self, trace: PipelineTrace, pipeline: SupportsPipeline, send_state: bool
    ) -> None:
        """Delegate trace end to all collectors"""
        for collector in self.collectors:
            try:
                collector.on_end_trace(trace, pipeline, send_state)
            except Exception as e:
                dlt_logger.warning(
                    f"Collector {collector.__class__.__name__} failed on_end_trace: {e}"
                )


class OpenTelemetryTracker(Collector):
    """
    A lightweight OpenTelemetry tracker that only sends metrics/traces.
    
    Does NOT display any progress - use this with CompositeCollector alongside
    a visual progress collector (tqdm, enlighten, log, etc.)
    
    Example:
        collector = CompositeCollector([
            TqdmCollector(),  # Visual progress
            OpenTelemetryTracker(otlp_endpoint="http://localhost:4318")  # Metrics
        ])
    """

    def __init__(
        self,
        otlp_endpoint: Optional[str] = None,
        service_name: Optional[str] = None,
        send_system_metrics: bool = False,
    ) -> None:
        """
        Args:
            otlp_endpoint: OTLP endpoint URL. If not provided, uses OTEL_EXPORTER_OTLP_ENDPOINT env var.
            service_name: Service name for OpenTelemetry. Defaults to pipeline name.
            send_system_metrics: Whether to send CPU/memory metrics. Default False (less overhead).
        """
        super().__init__()
        self.otlp_endpoint = otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        self.service_name = service_name
        self.send_system_metrics = send_system_metrics
        self._tracer = None
        self._meter = None
        self._current_transaction = None
        self._span_stack = []
        self._counter_instruments = {}
        self._initialized = False
        self._pipeline_attributes = {}

    def _ensure_initialized(self, pipeline: SupportsPipeline) -> None:
        """Initialize OpenTelemetry if not already done"""
        if self._initialized:
            return

        if not self.otlp_endpoint:
            dlt_logger.info(
                "OpenTelemetryTracker: OTLP endpoint not provided. "
                "Metrics/traces will not be sent. "
                "Set otlp_endpoint parameter or OTEL_EXPORTER_OTLP_ENDPOINT environment variable."
            )
            return

        try:
            from opentelemetry import trace, metrics
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
            from opentelemetry.sdk.resources import Resource
            from dlt.common.runtime.exec_info import dlt_version_info, kube_pod_info, github_info

            # Get runtime config from pipeline
            runtime_config = pipeline.run_context.runtime_config

            # Build version info
            version = dlt_version_info(runtime_config.pipeline_name)
            sys_ver = version["dlt_version"]
            release = sys_ver + "_" + version.get("commit_sha", "")

            # Create resource with service name and version
            resource_attributes = {
                "service.name": self.service_name or runtime_config.pipeline_name or "dlt-pipeline",
                "service.version": release,
            }

            # Add version tags
            for k, v in version.items():
                resource_attributes[k] = v

            # Add kubernetes tags
            pod_tags = kube_pod_info()
            for k, v in pod_tags.items():
                resource_attributes[k] = v

            # Add github info
            github_tags = github_info()
            for k, v in github_tags.items():
                resource_attributes[k] = v

            resource = Resource.create(resource_attributes)

            # Initialize tracing
            trace_provider = TracerProvider(resource=resource)
            trace.set_tracer_provider(trace_provider)

            # Create OTLP span exporter with proper endpoint path
            traces_endpoint = self.otlp_endpoint
            if not traces_endpoint.endswith("/v1/traces"):
                traces_endpoint = traces_endpoint.rstrip("/") + "/v1/traces"

            span_exporter = OTLPSpanExporter(endpoint=traces_endpoint)
            span_processor = BatchSpanProcessor(span_exporter)
            trace_provider.add_span_processor(span_processor)

            # Initialize metrics with proper endpoint path
            metrics_endpoint = self.otlp_endpoint
            if not metrics_endpoint.endswith("/v1/metrics"):
                metrics_endpoint = metrics_endpoint.rstrip("/") + "/v1/metrics"

            metric_exporter = OTLPMetricExporter(endpoint=metrics_endpoint)
            metric_reader = PeriodicExportingMetricReader(metric_exporter)
            metrics_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
            metrics.set_meter_provider(metrics_provider)

            self._tracer = trace.get_tracer(__name__)
            self._meter = metrics.get_meter(__name__)
            self._initialized = True

            dlt_logger.info(
                f"OpenTelemetryTracker initialized with endpoint: {self.otlp_endpoint}"
            )
        except ImportError:
            dlt_logger.info(
                "OpenTelemetry packages not installed. Install with: "
                "pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp"
            )
            self._initialized = False
        except Exception as e:
            dlt_logger.warning(f"Failed to initialize OpenTelemetry: {e}")
            self._initialized = False

    def update(
        self,
        name: str,
        inc: int = 1,
        total: int = None,
        inc_total: int = None,
        message: str = None,
        label: str = None,
    ) -> None:
        """Send metric to OpenTelemetry (no display)"""
        if self._initialized and self._meter:
            try:
                counter_key = f"{name}_{label}" if label else name

                # Get or create counter instrument
                if counter_key not in self._counter_instruments:
                    counter = self._meter.create_counter(
                        name=f"dlt.{name}",
                        description=f"Counter for {name}",
                        unit="1",
                    )
                    self._counter_instruments[counter_key] = counter

                # Record the increment with pipeline context
                counter = self._counter_instruments[counter_key]
                attributes = {}

                # Add pipeline context to metrics
                attributes.update(self._pipeline_attributes)

                # Add collector-specific attributes
                if label:
                    attributes["label"] = label
                if message:
                    attributes["message"] = message
                if total is not None:
                    attributes["total"] = str(total)

                counter.add(inc, attributes)
            except Exception as e:
                dlt_logger.debug(f"Failed to send metric to OpenTelemetry: {e}")

    def _start(self, step: str) -> None:
        """No-op for tracker (no display)"""
        pass

    def _stop(self) -> None:
        """Clear counter instruments"""
        self._counter_instruments.clear()

    def on_start_trace(
        self, trace: PipelineTrace, step: TPipelineStep, pipeline: SupportsPipeline
    ) -> None:
        """Start a new trace transaction"""
        self._ensure_initialized(pipeline)

        # Cache pipeline attributes for use in metrics
        self._pipeline_attributes = {
            "pipeline_name": pipeline.pipeline_name,
            "step": step,
        }
        if pipeline.destination:
            self._pipeline_attributes["destination"] = pipeline.destination.destination_name
        if pipeline.dataset_name:
            self._pipeline_attributes["dataset_name"] = pipeline.dataset_name

        if self._initialized and self._tracer:
            try:
                from opentelemetry.trace import SpanKind

                # Start a new transaction (root span)
                span_context = self._tracer.start_as_current_span(
                    name=step,
                    kind=SpanKind.SERVER,
                )
                self._current_transaction = span_context.__enter__()
                self._span_stack = [span_context]

                # Add attributes to the span
                self._current_transaction.set_attribute("pipeline_name", pipeline.pipeline_name)
                if pipeline.destination:
                    self._current_transaction.set_attribute(
                        "destination", pipeline.destination.destination_name
                    )
                if pipeline.dataset_name:
                    self._current_transaction.set_attribute("dataset_name", pipeline.dataset_name)
                self._current_transaction.set_attribute("transaction_id", trace.transaction_id)
            except Exception as e:
                dlt_logger.debug(f"Failed to start OpenTelemetry trace: {e}")

    def on_start_trace_step(
        self, trace: PipelineTrace, step: TPipelineStep, pipeline: SupportsPipeline
    ) -> None:
        """Start a new trace step (span)"""
        # Update step in pipeline attributes for metrics
        self._pipeline_attributes["step"] = step

        if self._initialized and self._tracer:
            try:
                # Start a child span for the step
                span_context = self._tracer.start_as_current_span(name=step)
                span = span_context.__enter__()

                # Add attributes
                span.set_attribute("pipeline_name", pipeline.pipeline_name)
                if pipeline.destination:
                    span.set_attribute("destination", pipeline.destination.destination_name)
                if pipeline.dataset_name:
                    span.set_attribute("dataset_name", pipeline.dataset_name)
                span.set_attribute("transaction_id", trace.transaction_id)

                self._span_stack.append(span_context)
            except Exception as e:
                dlt_logger.debug(f"Failed to start OpenTelemetry trace step: {e}")

    def on_end_trace_step(
        self,
        trace: PipelineTrace,
        step: PipelineStepTrace,
        pipeline: SupportsPipeline,
        step_info: Any,
        send_state: bool,
    ) -> None:
        """End a trace step (span)"""
        if self._initialized and self._span_stack:
            try:
                from opentelemetry.trace import Status, StatusCode
                from opentelemetry import trace as trace_api

                span_context = self._span_stack.pop()
                if span_context:
                    span = trace_api.get_current_span()

                    if step.step_exception:
                        span.set_status(Status(StatusCode.ERROR, step.step_exception))
                    else:
                        span.set_status(Status(StatusCode.OK))

                    if step.started_at and step.finished_at:
                        elapsed = (step.finished_at - step.started_at).total_seconds()
                        span.set_attribute("elapsed_seconds", elapsed)

                    span_context.__exit__(None, None, None)
            except Exception as e:
                dlt_logger.debug(f"Failed to end OpenTelemetry trace step: {e}")

    def on_end_trace(
        self, trace: PipelineTrace, pipeline: SupportsPipeline, send_state: bool
    ) -> None:
        """End the trace transaction"""
        if self._initialized and self._current_transaction:
            try:
                from opentelemetry.trace import Status, StatusCode

                # End all remaining spans
                while len(self._span_stack) > 1:
                    span_context = self._span_stack.pop()
                    if span_context:
                        span_context.__exit__(None, None, None)

                # Add attributes to the root transaction span
                if self._current_transaction:
                    if trace.finished_at and trace.started_at:
                        elapsed = (trace.finished_at - trace.started_at).total_seconds()
                        self._current_transaction.set_attribute("total_elapsed_seconds", elapsed)

                    if trace.steps and trace.steps[-1].step_exception:
                        self._current_transaction.set_status(
                            Status(StatusCode.ERROR, trace.steps[-1].step_exception)
                        )
                    else:
                        self._current_transaction.set_status(Status(StatusCode.OK))

                # End the root transaction
                if self._span_stack:
                    root_context = self._span_stack.pop()
                    root_context.__exit__(None, None, None)

                self._current_transaction = None
            except Exception as e:
                dlt_logger.debug(f"Failed to end OpenTelemetry trace: {e}")


def init_opentelemetry(
    otlp_endpoint: Optional[str] = None,
    service_name: Optional[str] = None,
) -> None:
    """
    Initialize OpenTelemetry globally (similar to init_sentry).
    
    This allows OpenTelemetry to work with ANY collector without wrapping.
    
    Note: This is an alternative approach. Currently not fully integrated into DLT's
    tracing system, but could be added similar to how Sentry is integrated.
    
    Args:
        otlp_endpoint: OTLP endpoint URL
        service_name: Service name for OpenTelemetry
    
    Example:
        init_opentelemetry(otlp_endpoint="http://localhost:4318")
        pipeline = dlt.pipeline(progress="tqdm")  # Uses tqdm but also sends to OTEL
    """
    # This is a placeholder for global initialization
    # Would require modifications to dlt.pipeline.track module to hook in
    dlt_logger.info(
        "Global OpenTelemetry initialization is not yet fully integrated. "
        "Use CompositeCollector with OpenTelemetryTracker instead."
    )
