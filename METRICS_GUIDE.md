# DLT OpenTelemetry Metrics Guide

## Complete Metrics List

### Pipeline Metrics (Counters)

| Metric Name | Type | What It Measures | When | Example Value |
|-------------|------|------------------|------|---------------|
| `dlt.Resources` | Counter | Number of data resources processed | Extract step | 2 (if processing users + orders) |
| `dlt.{resource_name}` | Counter | Rows extracted from specific resource | Extract step | 10000 (rows from "users" resource) |
| `dlt.Items` | Counter | Total rows/items normalized | Normalize step | 10000 |
| `dlt.Files` | Counter | Files created during normalization | Normalize step | 5 (e.g., 5 parquet files) |
| `dlt.Jobs` | Counter | Load jobs executed | Load step | 5 (one job per file) |

### System Metrics (Histograms)

| Metric Name | Type | What It Measures | Unit | Example Value |
|-------------|------|------------------|------|---------------|
| `dlt.system.memory_usage_mb` | Histogram | Process memory usage | MB | 245.67 MB |
| `dlt.system.memory_percent` | Histogram | System memory usage | percent | 42.5% |
| `dlt.system.cpu_percent` | Histogram | Process CPU usage | percent | 15.2% |

## Metric Attributes

All metrics include these attributes:

```python
{
    # Pipeline context
    "pipeline_name": "test_opentelemetry",
    "destination": "dlt.destinations.duckdb", 
    "dataset_name": "test_opentelemetry_dataset",
    "step": "extract",  # or "normalize" or "load"
    
    # Optional (if present)
    "label": "Completed",  # or "Failed"
    "total": "10000",      # Expected total count
    "message": "Processing batch 3",  # Progress message
}
```

Plus **Resource attributes** (from OpenTelemetry Resource):
```python
{
    "service.name": "test-pipeline",
    "service.version": "1.18.2_abc123",
    "dlt_version": "1.18.2",
    "commit_sha": "abc123",
    # ... plus kubernetes and github metadata if available
}
```

## Prometheus Query Examples

### Pipeline Throughput

```promql
# Items processed per second
rate(dlt_items_total[1m])

# Items by pipeline step
rate(dlt_items_total{step="normalize"}[5m])

# Resources processed by destination
sum by (destination) (dlt_resources_total)

# Jobs per pipeline
rate(dlt_jobs_total{pipeline_name="my_pipeline"}[5m])
```

### Resource-Specific Metrics

```promql
# Rows from specific resource
dlt_test_data_total{pipeline_name="test_opentelemetry"}

# Rate of rows from users resource
rate(dlt_users_total[1m])

# Multiple resources comparison
sum by (pipeline_name) (
  rate(dlt_users_total[5m]) + 
  rate(dlt_orders_total[5m])
)
```

### System Metrics

```promql
# Memory usage over time
dlt_system_memory_usage_mb{pipeline_name="test_opentelemetry"}

# CPU usage by pipeline
avg by (pipeline_name) (dlt_system_cpu_percent)

# Memory usage during load step
dlt_system_memory_usage_mb{step="load"}

# Alert on high memory usage
dlt_system_memory_usage_mb > 1000
```

### Performance Monitoring

```promql
# Files processed per second during normalization
rate(dlt_files_total{step="normalize"}[1m])

# Jobs throughput during load
rate(dlt_jobs_total{step="load"}[5m])

# Total pipeline throughput
sum(rate(dlt_items_total[5m])) by (pipeline_name)
```

### Error Tracking (with labels)

```promql
# Failed jobs
dlt_jobs_total{label="Failed"}

# Success rate
(
  sum(dlt_jobs_total{label!="Failed"}) / 
  sum(dlt_jobs_total)
) * 100
```

## Real-World Example

For a pipeline processing users + orders:

```python
@dlt.resource
def users():
    yield from range(10000)  # 10k users

@dlt.resource
def orders():
    yield from range(50000)  # 50k orders

pipeline.run([users, orders])
```

**Metrics you'll see:**

```promql
# Pipeline metrics
dlt_resources_total{step="extract"} = 2
dlt_users_total{step="extract"} = 10000
dlt_orders_total{step="extract"} = 50000
dlt_items_total{step="normalize"} = 60000
dlt_files_total{step="normalize"} = 10
dlt_jobs_total{step="load"} = 10

# System metrics (sampled every log_period)
dlt_system_memory_usage_mb{step="load"} = 342.5
dlt_system_cpu_percent{step="load"} = 45.2
```

## Grafana Dashboard Panels

### Panel 1: Pipeline Throughput
```promql
sum(rate(dlt_items_total[5m])) by (pipeline_name)
```

### Panel 2: Step Duration (from traces)
Use trace data to show step durations

### Panel 3: Resource Breakdown
```promql
sum by (step) (rate(dlt_items_total[5m]))
```

### Panel 4: System Resources
```promql
# Memory
dlt_system_memory_usage_mb

# CPU
dlt_system_cpu_percent
```

### Panel 5: Job Success Rate
```promql
sum(rate(dlt_jobs_total{label!="Failed"}[5m])) / 
sum(rate(dlt_jobs_total[5m])) * 100
```

## Metric Collection Frequency

- **Pipeline metrics**: Updated in real-time as pipeline processes data
- **System metrics**: Sampled every `log_period` seconds (default: 1.0s)
- **Export frequency**: Controlled by OpenTelemetry `PeriodicExportingMetricReader` (default: 60s)

## Notes

- **Histograms** are used for system metrics (better for percentile analysis)
- **Counters** are used for pipeline events (monotonically increasing)
- All metrics include full pipeline context as attributes
- System metrics require `psutil` to be installed (`pip install psutil`)
