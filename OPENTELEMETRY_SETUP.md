# OpenTelemetry Collector Setup Guide

## Fixed Issues

### 1. Span Context Manager Issue
Fixed the span management to properly use OpenTelemetry context managers. Spans are now correctly entered and exited.

### 2. OTLP Endpoint Configuration

**Important**: The collector uses HTTP/Protobuf exporters, not gRPC.

#### Correct Endpoint Configuration

| Protocol | Default Port | Endpoint URL |
|----------|--------------|--------------|
| **HTTP** (what we use) | **4318** | **`http://localhost:4318`** |
| gRPC (not used) | 4317 | `http://localhost:4317` |

#### Common OpenTelemetry Backends

**Jaeger (All-in-One)**
```bash
# Start Jaeger with OTLP support
docker run -d --name jaeger \
  -e COLLECTOR_OTLP_ENABLED=true \
  -p 16686:16686 \
  -p 4318:4318 \
  jaegertracing/all-in-one:latest

# Set endpoint
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

**OpenTelemetry Collector**
```bash
# Start OTEL Collector
docker run -d --name otel-collector \
  -p 4318:4318 \
  -p 4317:4317 \
  otel/opentelemetry-collector:latest

# For HTTP (recommended)
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318

# For gRPC (requires changing exporter in code)
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

**Grafana Cloud / Other Cloud Providers**
```bash
# Usually provide HTTP endpoint
export OTEL_EXPORTER_OTLP_ENDPOINT=https://your-endpoint.grafana.net:443
```

## Usage

### Basic Usage

```python
from opentelemetry_collector_standalone import OpenTelemetryCollector
import dlt

# Option 1: Pass endpoint directly
collector = OpenTelemetryCollector(
    otlp_endpoint="http://localhost:4318",
    service_name="my-pipeline"
)

# Option 2: Use environment variable
# export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
collector = OpenTelemetryCollector(
    service_name="my-pipeline"
)

# Use with pipeline
pipeline = dlt.pipeline(
    pipeline_name="test",
    destination="duckdb",
    progress=collector
)

pipeline.run(my_data())
```

### Quick Test with Jaeger

1. **Start Jaeger:**
```bash
docker run -d --name jaeger \
  -e COLLECTOR_OTLP_ENABLED=true \
  -p 16686:16686 \
  -p 4318:4318 \
  jaegertracing/all-in-one:latest
```

2. **Run test:**
```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
python test_standalone_collector.py
```

3. **View traces:**
Open http://localhost:16686 in your browser

## Troubleshooting

### Error: `BadStatusLine` or `Connection aborted`

**Cause**: You're using port 4317 (gRPC) with HTTP exporters.

**Solution**: Change endpoint to port 4318:
```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

### Error: `'_AgnosticContextManager' object has no attribute 'set_attribute'`

**Cause**: Span context managers weren't properly entered.

**Solution**: This has been fixed in the latest version. Re-download `opentelemetry_collector_standalone.py`.

### Metrics export fails

**Cause**: OTLP endpoint not accepting requests or wrong protocol.

**Solution**: 
1. Verify endpoint is running: `curl http://localhost:4318/v1/metrics`
2. Check if you need authentication headers
3. Ensure you're using HTTP port (4318), not gRPC port (4317)

## What You'll See

### In Logs
```
-------------------------- Extract test_opentelemetry --------------------------
Resources: 1/1 (100.0%) | Time: 0.02s | Rate: 59.92/s
test_data: 10  | Time: 0.02s | Rate: 649.22/s
```

### In OpenTelemetry Backend
- **Traces**: Pipeline transactions with extract/normalize/load spans
- **Metrics**: `dlt.Resources`, `dlt.Items`, `dlt.Files`, `dlt.Jobs` counters
- **Attributes**: `pipeline_name`, `destination`, `dataset_name`, `transaction_id`

## Dependencies

Install OpenTelemetry packages:
```bash
pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp
```

The collector will work without these (logging only), but OpenTelemetry features won't be available.
