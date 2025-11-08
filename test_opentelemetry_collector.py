"""Test script for OpenTelemetryCollector

This demonstrates how to test the OpenTelemetryCollector without integrating it
into the library's collector registry.

Usage:
    # Set your OTLP endpoint
    export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
    
    # Or pass it directly
    python test_opentelemetry_collector.py
"""
import os
from dlt.common.runtime.collector import OpenTelemetryCollector
import dlt


def test_basic_usage():
    """Test OpenTelemetryCollector with a simple pipeline"""
    
    # Create the collector directly
    collector = OpenTelemetryCollector(
        otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"),
        service_name="test-pipeline",
        log_period=0.5,  # Log more frequently for testing
    )
    
    # Use it directly with pipeline
    pipeline = dlt.pipeline(
        pipeline_name="test_opentelemetry",
        destination="duckdb",
        progress=collector,  # Pass the collector instance directly
    )
    
    # Simple test data
    @dlt.resource
    def test_data():
        for i in range(10):
            yield {"id": i, "name": f"item_{i}"}
    
    # Run the pipeline - this will trigger trace callbacks and metrics
    info = pipeline.run(test_data())
    print(f"Pipeline completed: {info}")
    print(f"Check your OpenTelemetry backend for traces and metrics!")


def test_with_logging():
    """Test that logging still works alongside OpenTelemetry"""
    
    collector = OpenTelemetryCollector(
        otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"),
        service_name="test-pipeline-with-logs",
        dump_system_stats=True,
    )
    
    pipeline = dlt.pipeline(
        pipeline_name="test_opentelemetry_logs",
        destination="duckdb",
        progress=collector,
    )
    
    @dlt.resource
    def test_data():
        for i in range(5):
            yield {"id": i, "value": i * 2}
    
    info = pipeline.run(test_data())
    print(f"Pipeline completed: {info}")


if __name__ == "__main__":
    print("Testing OpenTelemetryCollector...")
    print(f"OTLP Endpoint: {os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://localhost:4318')}")
    print()
    
    try:
        test_basic_usage()
        print("\n✓ Basic usage test passed")
    except Exception as e:
        print(f"\n✗ Basic usage test failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*50 + "\n")
    
    try:
        test_with_logging()
        print("\n✓ Logging test passed")
    except Exception as e:
        print(f"\n✗ Logging test failed: {e}")
        import traceback
        traceback.print_exc()
