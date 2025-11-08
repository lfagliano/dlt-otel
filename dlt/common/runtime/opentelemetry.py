"""OpenTelemetry initialization and utilities for dlt"""
import logging
import os
from typing import Optional

from dlt.common.exceptions import MissingDependencyException

try:
    from opentelemetry import trace, metrics
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.sdk.resources import Resource
    _OPENTELEMETRY_AVAILABLE = True
except ModuleNotFoundError:
    _OPENTELEMETRY_AVAILABLE = False

from dlt.common.typing import DictStrAny, Any, StrAny
from dlt.common.configuration.specs import RuntimeConfiguration
from dlt.common.runtime.exec_info import dlt_version_info, kube_pod_info, github_info


def init_opentelemetry(
    config: RuntimeConfiguration,
    service_name: Optional[str] = None,
    otlp_endpoint: Optional[str] = None,
) -> None:
    """
    Initialize OpenTelemetry tracing and metrics.

    Args:
        config: RuntimeConfiguration instance
        service_name: Service name for OpenTelemetry resource. Defaults to pipeline_name.
        otlp_endpoint: OTLP endpoint URL. If not provided, uses OTEL_EXPORTER_OTLP_ENDPOINT env var.
    """
    if not _OPENTELEMETRY_AVAILABLE:
        raise MissingDependencyException(
            "opentelemetry telemetry",
            ["opentelemetry-api", "opentelemetry-sdk", "opentelemetry-exporter-otlp"],
            "Please install opentelemetry packages if you want to use OpenTelemetryCollector",
        )

    if not otlp_endpoint:
        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        if not otlp_endpoint:
            raise ValueError(
                "OTLP endpoint must be provided either as parameter or via OTEL_EXPORTER_OTLP_ENDPOINT environment variable"
            )

    version = dlt_version_info(config.pipeline_name)
    sys_ver = version["dlt_version"]
    release = sys_ver + "_" + version.get("commit_sha", "")

    # Create resource with service name and version
    resource = Resource.create(
        {
            "service.name": service_name or config.pipeline_name or "dlt-pipeline",
            "service.version": release,
        }
    )

    # Add version tags
    resource_attributes = dict(resource.attributes)
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
    span_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
    span_processor = BatchSpanProcessor(span_exporter)
    trace_provider.add_span_processor(span_processor)

    # Initialize metrics
    metric_exporter = OTLPMetricExporter(endpoint=otlp_endpoint)
    metric_reader = PeriodicExportingMetricReader(metric_exporter)
    metrics_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(metrics_provider)


def disable_opentelemetry() -> None:
    """Disable OpenTelemetry by clearing providers"""
    if _OPENTELEMETRY_AVAILABLE:
        from opentelemetry import trace, metrics
        trace.set_tracer_provider(None)
        metrics.set_meter_provider(None)
