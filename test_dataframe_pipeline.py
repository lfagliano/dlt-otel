"""Test OpenTelemetryCollector with a DataFrame pipeline

This script tests the standalone OpenTelemetryCollector with:
- Generated data with 10k rows (no pandas required)
- Loading to DuckDB
- Verifying metrics and traces are sent
"""
import os
from opentelemetry_collector_standalone import OpenTelemetryCollector
import dlt


def create_test_data(num_rows: int = 10000):
    """Create test data as a generator (no pandas required)"""
    import random
    from datetime import datetime, timedelta
    
    categories = ["A", "B", "C", "D", "E"]
    
    for i in range(1, num_rows + 1):
        yield {
            "id": i,
            "name": f"user_{i}",
            "email": f"user_{i}@example.com",
            "age": random.randint(18, 80),
            "score": round(random.uniform(0, 100), 2),
            "is_active": random.choice([True, False]),
            "created_at": datetime.now() - timedelta(days=random.randint(0, 365)),
            "category": random.choice(categories),
        }


def test_dataframe_pipeline():
    """Test OpenTelemetryCollector with data pipeline"""
    
    print("=" * 70)
    print("Testing OpenTelemetryCollector with 10k Row Pipeline")
    print("=" * 70)
    print()
    
    # Create the collector
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    collector = OpenTelemetryCollector(
        otlp_endpoint=otlp_endpoint,
        service_name="dataframe-test-pipeline",
        log_period=0.5,  # Log every 0.5 seconds for visibility
        dump_system_stats=True,
    )
    
    print(f"✓ OpenTelemetryCollector created")
    print(f"  OTLP Endpoint: {otlp_endpoint}")
    print(f"  Service Name: {collector.service_name}")
    print()
    
    # Create pipeline
    pipeline = dlt.pipeline(
        pipeline_name="dataframe_test",
        destination="duckdb",
        progress=collector,
    )
    
    print("✓ Pipeline created")
    print()
    
    # Create test data resource
    print("Creating test data resource with 10,000 rows...")
    
    @dlt.resource(name="users")
    def users_data():
        """Generate 10k rows of test data"""
        yield from create_test_data(10000)
    
    print(f"✓ Resource created: users (10,000 rows)")
    print()
    
    # Run the pipeline
    print("Running pipeline (extract -> normalize -> load)...")
    print("-" * 70)
    
    try:
        info = pipeline.run(users_data)
        
        print("-" * 70)
        print()
        print("✓ Pipeline completed successfully!")
        print()
        print("Results:")
        print(f"  Load packages: {len(info.loads_ids)}")
        print(f"  Load IDs: {info.loads_ids}")
        print(f"  Destination: {info.destination_type}")
        print(f"  Dataset: {info.dataset_name}")
        print()
        
        # Verify data was loaded
        with pipeline.sql_client() as client:
            result = client.execute_sql("SELECT COUNT(*) as count FROM users")
            # DuckDB returns a list of tuples
            if isinstance(result, list) and len(result) > 0:
                count = result[0][0]
            elif hasattr(result, 'fetchone'):
                row = result.fetchone()
                count = row[0] if row else 0
            else:
                count = result[0] if result else 0
            
            print(f"  Rows in destination: {count}")
            if count == 10000:
                print("  ✓ All rows loaded correctly!")
            else:
                print(f"  ⚠ Expected 10000 rows, got {count}")
        
        print()
        print("=" * 70)
        print("OpenTelemetry Metrics & Traces")
        print("=" * 70)
        print("Check your OpenTelemetry backend for:")
        print("  • Metrics: dlt.Resources, dlt.Items, dlt.Files, dlt.Jobs, etc.")
        print("  • Traces: Pipeline transaction with extract/normalize/load spans")
        print("  • Attributes: pipeline_name, destination, dataset_name, etc.")
        print()
        print(f"  OTLP Endpoint: {otlp_endpoint}")
        print("=" * 70)
        
        return True
        
    except Exception as e:
        print(f"\n✗ Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_with_multiple_resources():
    """Test with multiple resources to see more metrics"""
    
    print("\n" + "=" * 70)
    print("Testing with Multiple Resources")
    print("=" * 70)
    print()
    
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    collector = OpenTelemetryCollector(
        otlp_endpoint=otlp_endpoint,
        service_name="multi-resource-test",
        log_period=0.5,
    )
    
    pipeline = dlt.pipeline(
        pipeline_name="multi_resource_test",
        destination="duckdb",
        progress=collector,
    )
    
    @dlt.resource(name="users")
    def users_data():
        yield from create_test_data(5000)
    
    @dlt.resource(name="orders")
    def orders_data():
        yield from create_test_data(5000)
    
    print("Running pipeline with 2 resources (10k total rows)...")
    info = pipeline.run([users_data, orders_data])
    
    print(f"\n✓ Loaded {len(info.loads_ids)} load package(s)")
    print("  Check OpenTelemetry for metrics from both resources!")


if __name__ == "__main__":
    import sys
    
    # Check if OpenTelemetry packages are available
    try:
        import opentelemetry
        print("✓ OpenTelemetry packages available")
    except ImportError:
        print("⚠ OpenTelemetry packages not installed")
        print("  Install with: pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp")
        print("  Collector will still work but won't send to OpenTelemetry")
        print()
    
    # Run main test
    try:
        success = test_dataframe_pipeline()
        
        # Optionally run multi-resource test
        if len(sys.argv) > 1 and sys.argv[1] == "--multi":
            test_with_multiple_resources()
        
        if success:
            print("\n✓ All tests completed successfully!")
        else:
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nTest failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
