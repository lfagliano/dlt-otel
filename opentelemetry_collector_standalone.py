"""Standalone OpenTelemetryCollector for testing

This script provides a standalone implementation of OpenTelemetryCollector
that can be used without modifying the dlt source code.

Usage:
    from opentelemetry_collector_standalone import OpenTelemetryCollector
    import dlt
    
    collector = OpenTelemetryCollector(
        otlp_endpoint="http://localhost:4318",
        service_name="my-pipeline"
    )
    
    pipeline = dlt.pipeline(
        pipeline_name="test",
        destination="duckdb",
        progress=collector
    )
"""
import os
import sys
import logging
import time
from collections import defaultdict
from typing import (
    Any,
    Dict,
    DefaultDict,
    NamedTuple,
    Optional,
    Union,
    TextIO,
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    from dlt.pipeline.trace import PipelineTrace, PipelineStepTrace
    from dlt.pipeline.typing import TPipelineStep
    from dlt.common.pipeline import SupportsPipeline
else:
    PipelineTrace = PipelineStepTrace = TPipelineStep = SupportsPipeline = Any

# Import base collector from dlt
from dlt.common.runtime.collector import LogCollector
from dlt.common import logger as dlt_logger


class OpenTelemetryCollector(LogCollector):
    """A Collector that sends metrics and traces to OpenTelemetry
    
    Extends LogCollector to maintain logging functionality while adding
    OpenTelemetry metrics and tracing support.
    """

    def __init__(
        self,
        log_period: float = 1.0,
        logger: Union[logging.Logger, TextIO] = sys.stdout,
        log_level: int = logging.INFO,
        dump_system_stats: bool = True,
        otlp_endpoint: Optional[str] = None,
        service_name: Optional[str] = None,
    ) -> None:
        """
        Collector that extends LogCollector to send metrics and traces to OpenTelemetry.

        Args:
            log_period (float, optional): Time period in seconds between log updates. Defaults to 1.0.
            logger (logging.Logger | TextIO, optional): Logger or text stream to write log messages to. Defaults to stdio.
            log_level (str, optional): Log level for the logger. Defaults to INFO level
            dump_system_stats (bool, optional): Log memory and cpu usage. Defaults to True
            otlp_endpoint (str, optional): OTLP endpoint URL. If not provided, uses OTEL_EXPORTER_OTLP_ENDPOINT env var.
            service_name (str, optional): Service name for OpenTelemetry. Defaults to None.
        """
        super().__init__(log_period, logger, log_level, dump_system_stats)
        self.otlp_endpoint = otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        self.service_name = service_name
        self._tracer = None
        self._meter = None
        self._current_transaction = None
        self._span_stack = []
        self._counter_instruments: Dict[str, Any] = {}
        self._initialized = False

    def _ensure_initialized(self, pipeline: SupportsPipeline) -> None:
        """Initialize OpenTelemetry if not already done"""
        if self._initialized:
            return

        if not self.otlp_endpoint:
            dlt_logger.warning(
                "OpenTelemetryCollector: OTLP endpoint not provided. "
                "Set otlp_endpoint parameter or OTEL_EXPORTER_OTLP_ENDPOINT environment variable."
            )
            return

        try:
            from opentelemetry import trace, metrics
            from opentelemetry.trace import SpanKind, Status, StatusCode
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
            from opentelemetry.sdk.resources import Resource
            from dlt.common.runtime.exec_info import dlt_version_info, kube_pod_info, github_info
            from dlt.common.configuration.specs import RuntimeConfiguration

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

            # Create OTLP span exporter
            span_exporter = OTLPSpanExporter(endpoint=self.otlp_endpoint)
            span_processor = BatchSpanProcessor(span_exporter)
            trace_provider.add_span_processor(span_processor)

            # Initialize metrics
            metric_exporter = OTLPMetricExporter(endpoint=self.otlp_endpoint)
            metric_reader = PeriodicExportingMetricReader(metric_exporter)
            metrics_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
            metrics.set_meter_provider(metrics_provider)

            self._tracer = trace.get_tracer(__name__)
            self._meter = metrics.get_meter(__name__)
            self._initialized = True
            
            dlt_logger.info(f"OpenTelemetryCollector initialized with endpoint: {self.otlp_endpoint}")
        except ImportError as e:
            dlt_logger.warning(
                f"OpenTelemetry packages not installed. Install with: "
                f"pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp"
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
        """Update counter and send metric to OpenTelemetry"""
        # Call parent to maintain logging behavior
        super().update(name, inc, total, inc_total, message, label)

        # Send metrics to OpenTelemetry if initialized
        if self._initialized and self._meter:
            try:
                counter_key = f"{name}_{label}" if label else name

                # Get or create counter instrument
                if counter_key not in self._counter_instruments:
                    # Create a counter metric
                    counter = self._meter.create_counter(
                        name=f"dlt.{name}",
                        description=f"Counter for {name}",
                        unit="1",
                    )
                    self._counter_instruments[counter_key] = counter

                # Record the increment
                counter = self._counter_instruments[counter_key]
                attributes = {}
                if label:
                    attributes["label"] = label
                if message:
                    attributes["message"] = message
                if total is not None:
                    attributes["total"] = total

                counter.add(inc, attributes)
            except Exception as e:
                dlt_logger.warning(f"Failed to send metric to OpenTelemetry: {e}")

    def on_start_trace(
        self, trace: PipelineTrace, step: TPipelineStep, pipeline: SupportsPipeline
    ) -> None:
        """Start a new trace transaction"""
        self._ensure_initialized(pipeline)
        if self._initialized and self._tracer:
            try:
                from opentelemetry.trace import SpanKind

                # Start a new transaction (root span)
                self._current_transaction = self._tracer.start_as_current_span(
                    name=step,
                    kind=SpanKind.SERVER,
                )
                self._span_stack = [self._current_transaction]

                # Add attributes
                self._current_transaction.set_attribute("pipeline_name", pipeline.pipeline_name)
                if pipeline.destination:
                    self._current_transaction.set_attribute(
                        "destination", pipeline.destination.destination_name
                    )
                if pipeline.dataset_name:
                    self._current_transaction.set_attribute("dataset_name", pipeline.dataset_name)
                self._current_transaction.set_attribute("transaction_id", trace.transaction_id)
            except Exception as e:
                dlt_logger.warning(f"Failed to start OpenTelemetry trace: {e}")

    def on_start_trace_step(
        self, trace: PipelineTrace, step: TPipelineStep, pipeline: SupportsPipeline
    ) -> None:
        """Start a new trace step (span)"""
        if self._initialized and self._tracer:
            try:
                # Start a child span for the step
                span = self._tracer.start_as_current_span(name=step)
                span.set_attribute("pipeline_name", pipeline.pipeline_name)
                if pipeline.destination:
                    span.set_attribute("destination", pipeline.destination.destination_name)
                if pipeline.dataset_name:
                    span.set_attribute("dataset_name", pipeline.dataset_name)
                span.set_attribute("transaction_id", trace.transaction_id)

                # Add to stack
                self._span_stack.append(span)
            except Exception as e:
                dlt_logger.warning(f"Failed to start OpenTelemetry trace step: {e}")

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

                # Pop and end the current span
                span = self._span_stack.pop()
                if span:
                    # Add step info as attributes
                    if step.step_exception:
                        span.set_status(Status(StatusCode.ERROR, step.step_exception))
                    else:
                        span.set_status(Status(StatusCode.OK))

                    if step.started_at and step.finished_at:
                        elapsed = (step.finished_at - step.started_at).total_seconds()
                        span.set_attribute("elapsed_seconds", elapsed)

                    span.__exit__(None, None, None)
            except Exception as e:
                dlt_logger.warning(f"Failed to end OpenTelemetry trace step: {e}")

    def on_end_trace(
        self, trace: PipelineTrace, pipeline: SupportsPipeline, send_state: bool
    ) -> None:
        """End the trace transaction"""
        if self._initialized and self._current_transaction:
            try:
                from opentelemetry.trace import Status, StatusCode

                # End all remaining spans
                while self._span_stack:
                    span = self._span_stack.pop()
                    if span:
                        span.__exit__(None, None, None)

                # End the transaction
                if self._current_transaction:
                    if trace.finished_at and trace.started_at:
                        elapsed = (trace.finished_at - trace.started_at).total_seconds()
                        self._current_transaction.set_attribute("total_elapsed_seconds", elapsed)

                    # Check if trace failed
                    if trace.steps and trace.steps[-1].step_exception:
                        self._current_transaction.set_status(
                            Status(StatusCode.ERROR, trace.steps[-1].step_exception)
                        )
                    else:
                        self._current_transaction.set_status(Status(StatusCode.OK))

                    self._current_transaction.__exit__(None, None, None)
                    self._current_transaction = None
            except Exception as e:
                dlt_logger.warning(f"Failed to end OpenTelemetry trace: {e}")

    def _stop(self) -> None:
        """Stop collecting and flush metrics"""
        # Clear counter instruments
        self._counter_instruments.clear()
        # Call parent to maintain logging behavior
        super()._stop()
