"""
Example: Using tqdm for progress + OpenTelemetry for metrics

This shows how to use CompositeCollector to get visual progress from tqdm
while simultaneously sending metrics and traces to OpenTelemetry.
"""

import dlt
from opentelemetry_integration import CompositeCollector, OpenTelemetryTracker
from dlt.common.runtime.collector import TqdmCollector

# Create test data
@dlt.resource
def test_data():
    """Generate test data"""
    for i in range(10000):
        yield {"id": i, "value": f"row_{i}"}

def main():
    print("=" * 70)
    print("Testing CompositeCollector: tqdm + OpenTelemetry")
    print("=" * 70)
    print()
    
    # Create a composite collector with both tqdm and OpenTelemetry
    collector = CompositeCollector([
        TqdmCollector(),  # Visual progress bars
        OpenTelemetryTracker(
            otlp_endpoint="http://localhost:4318",
            service_name="test-composite-pipeline"
        )
    ])
    
    print("✓ Created CompositeCollector with:")
    print("  - TqdmCollector (visual progress)")
    print("  - OpenTelemetryTracker (metrics & traces)")
    print()
    print("OTLP Endpoint: http://localhost:4318")
    print()
    print("Running pipeline with tqdm progress + OpenTelemetry observability...")
    print()
    
    # Create pipeline with composite collector
    pipeline = dlt.pipeline(
        pipeline_name="test_composite",
        destination="duckdb",
        dataset_name="test_composite_dataset",
        progress=collector  # Use composite collector
    )
    
    # Run the pipeline
    load_info = pipeline.run(test_data())
    
    print()
    print("=" * 70)
    print("✓ Pipeline completed successfully!")
    print("=" * 70)
    print()
    print("What happened:")
    print("  ✓ Tqdm showed visual progress bars")
    print("  ✓ OpenTelemetry sent metrics to http://localhost:4318")
    print("  ✓ Traces are available in your observability backend")
    print()
    print("Check your backends:")
    print("  - Jaeger UI: http://localhost:16686")
    print("  - Grafana Dashboard: Import grafana_dashboard.json")
    print()

if __name__ == "__main__":
    main()
