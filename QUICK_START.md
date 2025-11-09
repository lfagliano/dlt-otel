# DLT OpenTelemetry Integration - Quick Start

## 🎯 The Problem

You want OpenTelemetry metrics/traces **AND** your favorite progress display (tqdm, enlighten, log).

## ✅ The Solution: CompositeCollector

Combine multiple collectors to get both!

## 🚀 Quick Start (30 seconds)

### 1. Copy the integration module
```bash
# Files you need:
# - opentelemetry_integration.py
# - test_composite_collector.py (optional test)
```

### 2. Use it in your pipeline

```python
import dlt
from opentelemetry_integration import CompositeCollector, OpenTelemetryTracker
from dlt.common.runtime.collector import TqdmCollector

# Create composite collector
collector = CompositeCollector([
    TqdmCollector(),  # Visual progress bars
    OpenTelemetryTracker(otlp_endpoint="http://localhost:4318")
])

# Use it!
pipeline = dlt.pipeline(
    pipeline_name="my_pipeline",
    destination="duckdb",
    progress=collector  # 👈 That's it!
)

pipeline.run(my_data())
```

### 3. Enjoy!

**You get:**
- ✅ Tqdm progress bars in terminal
- ✅ Metrics in Prometheus/Grafana
- ✅ Traces in Jaeger
- ✅ No trade-offs!

---

## 📚 More Examples

### With Enlighten (better for multiple pipelines)

```python
from dlt.common.runtime.collector import EnlightenCollector

collector = CompositeCollector([
    EnlightenCollector(),
    OpenTelemetryTracker(otlp_endpoint="http://localhost:4318")
])
```

### With Logging (server/background jobs)

```python
from dlt.common.runtime.collector import LogCollector

collector = CompositeCollector([
    LogCollector(log_period=1.0),
    OpenTelemetryTracker(otlp_endpoint="http://localhost:4318")
])
```

### Silent (no console output, only metrics)

```python
from dlt.common.runtime.collector import NullCollector

collector = CompositeCollector([
    NullCollector(),  # No console output
    OpenTelemetryTracker(otlp_endpoint="http://localhost:4318")
])
```

### Multiple observability backends

```python
collector = CompositeCollector([
    TqdmCollector(),
    OpenTelemetryTracker(otlp_endpoint="http://localhost:4318"),
    MyCustomTracker()  # Add your own!
])
```

---

## 🔧 Setup OpenTelemetry Backend

### Option 1: Jaeger All-in-One (easiest for testing)

```bash
docker run -d --name jaeger \
  -e COLLECTOR_OTLP_ENABLED=true \
  -p 16686:16686 \
  -p 4318:4318 \
  jaegertracing/all-in-one:latest

# View traces at: http://localhost:16686
```

### Option 2: OpenTelemetry Collector + Prometheus + Grafana

```bash
# See GRAFANA_DASHBOARD_GUIDE.md for full setup
# Includes pre-built Grafana dashboard with 11 panels
```

### Option 3: Cloud Services

```python
# Grafana Cloud
OpenTelemetryTracker(otlp_endpoint="https://otlp-gateway-prod-us-east-0.grafana.net/otlp")

# Datadog
OpenTelemetryTracker(otlp_endpoint="https://http-intake.logs.datadoghq.com/v1/input")

# Honeycomb
OpenTelemetryTracker(otlp_endpoint="https://api.honeycomb.io")
```

---

## 📊 What Metrics You Get

### Pipeline Metrics (Counters)
- `dlt.Resources` - Number of resources processed
- `dlt.{resource_name}` - Items from each resource
- `dlt.Items` - Total items normalized
- `dlt.Files` - Files created
- `dlt.Jobs` - Load jobs executed

### Trace Spans
- Pipeline transaction (root span)
- Extract, normalize, load steps (child spans)
- Timing, status, attributes

### Attributes on All Metrics
- `pipeline_name`
- `destination`
- `dataset_name`
- `step` (extract/normalize/load)
- Plus: `label`, `total`, `message`

**See METRICS_GUIDE.md for complete list and Prometheus queries**

---

## 🎛️ Configuration

### Environment Variables

```bash
# Set globally
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318

# Then use without explicit endpoint
collector = CompositeCollector([
    TqdmCollector(),
    OpenTelemetryTracker()  # Uses env var
])
```

### Constructor Options

```python
OpenTelemetryTracker(
    otlp_endpoint="http://localhost:4318",  # Required (or env var)
    service_name="my-pipeline",             # Optional (defaults to pipeline name)
    send_system_metrics=False               # Optional (CPU/memory, default False)
)
```

---

## 🧪 Test It

### Run the example

```bash
python test_composite_collector.py
```

**Expected output:**
```
Testing CompositeCollector: tqdm + OpenTelemetry
==================================================

✓ Created CompositeCollector with:
  - TqdmCollector (visual progress)
  - OpenTelemetryTracker (metrics & traces)

Running pipeline with tqdm progress + OpenTelemetry observability...

Extract: 100%|█████████████| 10000/10000 [00:01<00:00, 8523.45it/s]
Normalize: 100%|██████████| 10000/10000 [00:00<00:00, 12345.67it/s]
Load: 100%|█████████████████| 1/1 [00:00<00:00, 123.45it/s]

✓ Pipeline completed successfully!

What happened:
  ✓ Tqdm showed visual progress bars
  ✓ OpenTelemetry sent metrics to http://localhost:4318
  ✓ Traces are available in your observability backend
```

---

## 🐛 Troubleshooting

### "No data in Grafana"

**Check 1:** Is OpenTelemetry Collector running?
```bash
curl http://localhost:4318/v1/metrics
# Should NOT return 404
```

**Check 2:** Is Prometheus scraping?
```bash
./verify_prometheus.sh
```

**Check 3:** Did the pipeline run?
```bash
# Metrics only appear after pipeline runs
python test_composite_collector.py
```

### "ImportError: No module named opentelemetry"

```bash
pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp
```

### "Tqdm not showing"

**Issue:** Tqdm might be disabled in non-TTY environments

**Solution:**
```python
# Force tqdm to work
from dlt.common.runtime.collector import TqdmCollector

collector = CompositeCollector([
    TqdmCollector(force=True),  # 👈 Add force=True
    OpenTelemetryTracker(otlp_endpoint="http://localhost:4318")
])
```

---

## 📖 Documentation

- **INTEGRATION_APPROACHES.md** - Detailed comparison of all approaches
- **METRICS_GUIDE.md** - Complete metrics reference and Prometheus queries
- **GRAFANA_DASHBOARD_GUIDE.md** - How to import pre-built dashboard
- **OPENTELEMETRY_SETUP.md** - Backend configuration and troubleshooting

---

## 🎉 That's It!

You now have:
- ✅ Visual progress display (tqdm/enlighten/log)
- ✅ Distributed tracing
- ✅ Real-time metrics
- ✅ Grafana dashboards
- ✅ No compromises!

**Enjoy your observability!** 🚀

---

## One-Line Summary

```python
# Before: Choose between progress OR observability
pipeline = dlt.pipeline(progress="tqdm")  # No metrics ❌

# After: Get both!
collector = CompositeCollector([TqdmCollector(), OpenTelemetryTracker(otlp_endpoint="http://localhost:4318")])
pipeline = dlt.pipeline(progress=collector)  # Visual progress + metrics ✅
```
