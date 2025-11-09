"""Quick demo: tqdm + OpenTelemetry working together"""
import dlt
from opentelemetry_integration import CompositeCollector, OpenTelemetryTracker
from dlt.common.runtime.collector import TqdmCollector

@dlt.resource
def sample_data():
    """Generate 1000 rows"""
    for i in range(1000):
        yield {"id": i, "value": f"row_{i}"}

# Create composite collector
collector = CompositeCollector([
    TqdmCollector(),  # Visual progress bars
    OpenTelemetryTracker(  # Metrics to OpenTelemetry
        otlp_endpoint="http://localhost:4318",
        service_name="demo-pipeline"
    )
])

print("Running pipeline with tqdm + OpenTelemetry...")
print()

pipeline = dlt.pipeline(
    pipeline_name="quick_demo",
    destination="duckdb",
    progress=collector  # Both collectors work!
)

pipeline.run(sample_data())

print()
print("✓ Done! You saw tqdm progress AND metrics were sent to OpenTelemetry")
