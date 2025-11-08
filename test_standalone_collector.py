"""Example usage of standalone OpenTelemetryCollector

This script demonstrates how to use the standalone OpenTelemetryCollector
without modifying any dlt source code.
"""
import os
from opentelemetry_collector_standalone import OpenTelemetryCollector
import dlt


def main():
    """Example pipeline using OpenTelemetryCollector"""
    
    # Create the collector
    collector = OpenTelemetryCollector(
        otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"),
        service_name="test-pipeline",
        log_period=0.5,  # Log more frequently for testing
        dump_system_stats=True,
    )
    
    # Create pipeline and pass the collector directly
    pipeline = dlt.pipeline(
        pipeline_name="test_opentelemetry",
        destination="duckdb",
        progress=collector,  # Pass the collector instance
    )
    
    # Define a simple resource
    @dlt.resource
    def test_data():
        """Generate test data"""
        for i in range(10):
            yield {
                "id": i,
                "name": f"item_{i}",
                "value": i * 10,
            }
    
    # Run the pipeline
    print("Running pipeline with OpenTelemetryCollector...")
    print(f"OTLP Endpoint: {collector.otlp_endpoint}")
    print()
    
    info = pipeline.run(test_data())
    
    print(f"\n✓ Pipeline completed successfully!")
    print(f"  Loaded {len(info.loads_ids)} load package(s)")
    print(f"  Check your OpenTelemetry backend for traces and metrics!")


if __name__ == "__main__":
    main()
