# DLT Pipeline Grafana Dashboard Guide

## Dashboard Overview

This dashboard provides comprehensive monitoring for DLT pipelines with 11 panels:

### 📊 **Panels Included:**

1. **Pipeline Throughput** - Real-time items/sec processing rate
2. **Total Items Processed** - Cumulative count with color thresholds
3. **Total Jobs Executed** - Job count with performance indicators
4. **Items by Pipeline Step** - Donut chart showing extract/normalize/load distribution
5. **Job Success Rate** - Gauge showing % of successful jobs (green > 99%)
6. **Memory Usage by Pipeline** - P50 and P95 memory percentiles over time
7. **CPU Usage by Pipeline** - P50 and P95 CPU percentiles over time
8. **Resources by Destination** - Stacked bar chart of resources → destinations
9. **Jobs Success/Failure Rate** - Trend showing success vs failed jobs by step
10. **File Creation Rate** - Files/sec during normalization
11. **Pipeline Summary Table** - Sortable table with pipeline stats

### 🎨 **Features:**

- Auto-refresh every 5 seconds
- Template variable to filter by pipeline name
- Color-coded thresholds for quick health checks
- Percentile-based metrics for accurate resource monitoring
- Dark theme optimized

---

## How to Import

### Option 1: Import via Grafana UI

1. **Open Grafana** in your browser (usually `http://localhost:3000`)

2. **Navigate to Dashboards:**
   - Click the **"+"** icon in the left sidebar
   - Select **"Import"**

3. **Upload JSON:**
   - Click **"Upload JSON file"**
   - Select `grafana_dashboard.json` from this directory
   - OR copy-paste the JSON content directly

4. **Configure:**
   - Select your **Prometheus data source** from the dropdown
   - Click **"Import"**

5. **Done!** The dashboard will open automatically

---

### Option 2: Import via Grafana API

```bash
# Set your Grafana credentials
GRAFANA_URL="http://localhost:3000"
GRAFANA_USER="admin"
GRAFANA_PASSWORD="admin"

# Import the dashboard
curl -X POST "$GRAFANA_URL/api/dashboards/db" \
  -u "$GRAFANA_USER:$GRAFANA_PASSWORD" \
  -H "Content-Type: application/json" \
  -d @grafana_dashboard.json
```

---

## Quick Test

### 1. **Ensure Prometheus is Scraping Metrics**

```bash
# Check if Prometheus is receiving DLT metrics
curl "http://localhost:9090/api/v1/query?query=dlt_items_total" | jq .

# You should see results like:
# {
#   "status": "success",
#   "data": {
#     "result": [
#       {
#         "metric": {
#           "pipeline_name": "test_opentelemetry",
#           "step": "normalize"
#         },
#         "value": [1699900000, "10000"]
#       }
#     ]
#   }
# }
```

If you see **empty results**, your OpenTelemetry Collector might not be exporting to Prometheus. Check your OTEL Collector config.

---

### 2. **Run a Test Pipeline**

```bash
# Export OpenTelemetry endpoint (OTEL Collector that exports to Prometheus)
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318

# Run the test pipeline
python3 test_standalone_collector.py
```

---

### 3. **View in Grafana**

1. Open the **"DLT Pipeline Observability"** dashboard
2. Select your pipeline from the **"Pipeline"** dropdown at the top
3. Set time range to **"Last 15 minutes"**
4. Enable auto-refresh (already set to 5s)

---

## Prometheus Configuration

Your Prometheus needs to scrape metrics from the **OpenTelemetry Collector**. 

### Example Prometheus Config

Add this to your `prometheus.yml`:

```yaml
scrape_configs:
  # Scrape OpenTelemetry Collector metrics endpoint
  - job_name: 'otel-collector'
    scrape_interval: 10s
    static_configs:
      - targets: ['localhost:8888']  # OTEL Collector metrics endpoint
      
  # If OTEL Collector exports to Prometheus receiver
  - job_name: 'dlt-pipelines'
    scrape_interval: 10s
    static_configs:
      - targets: ['localhost:8889']  # Prometheus exporter endpoint
```

**Common OTEL Collector → Prometheus Setup:**

```yaml
# otel-collector-config.yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

exporters:
  prometheus:
    endpoint: "0.0.0.0:8889"
    namespace: ""
    
service:
  pipelines:
    metrics:
      receivers: [otlp]
      exporters: [prometheus]
```

Then Prometheus scrapes from `localhost:8889`.

---

## Dashboard Customization

### Change Thresholds

Edit the JSON to adjust when colors change:

```json
"thresholds": {
  "mode": "absolute",
  "steps": [
    {"color": "green", "value": null},
    {"color": "yellow", "value": 500},   // ← Change these
    {"color": "red", "value": 1000}      // ← Change these
  ]
}
```

### Add More Panels

1. Click **"Add panel"** in the dashboard
2. Use Prometheus queries from `METRICS_GUIDE.md`
3. Examples:
   ```promql
   # Resource-specific throughput
   rate(dlt_users_total[5m])
   
   # Memory per step
   histogram_quantile(0.95, 
     sum(rate(dlt_system_memory_usage_mb_bucket[5m])) by (le, step)
   )
   ```

### Filter by Pipeline

The dashboard includes a template variable `$pipeline` that you can use:

```promql
# Filter queries by selected pipeline
rate(dlt_items_total{pipeline_name=~"$pipeline"}[5m])
```

---

## Troubleshooting

### "No data" in panels

**Check 1: Prometheus has data**
```bash
curl "http://localhost:9090/api/v1/label/__name__/values" | grep dlt
```
Should show: `dlt_items_total`, `dlt_jobs_total`, etc.

**Check 2: Time range**
- Ensure dashboard time range includes when you ran the pipeline
- Try "Last 1 hour" or "Last 6 hours"

**Check 3: Data source**
- Go to Grafana → Configuration → Data Sources
- Test your Prometheus connection

### Histogram queries not working

If you see errors like `histogram_quantile: not a histogram`, it means:
- System metrics aren't being exported (install `psutil`)
- Or OTEL Collector isn't configured for histogram metrics

**Workaround:** Use sum/avg instead:
```promql
# Instead of histogram_quantile
avg(dlt_system_memory_usage_mb) by (pipeline_name)
```

### Dashboard not importing

**Error: "Dashboard with UID already exists"**
- Change the `"uid"` field in the JSON to something else
- Or delete the existing dashboard first

---

## Example Screenshots of What You'll See

### Panel 1: Pipeline Throughput
```
📈 Line graph showing:
- test_opentelemetry: 1000 items/sec
- Mean: 850 | Last: 1000 | Max: 1200
```

### Panel 5: Job Success Rate
```
🎯 Gauge showing:
- 99.5% (GREEN)
```

### Panel 6: Memory Usage
```
📊 Time series with:
- test_opentelemetry (p95): 245 MB
- test_opentelemetry (p50): 180 MB
```

---

## Next Steps

1. **Run your actual pipelines** with the OpenTelemetry collector enabled
2. **Create alerts** based on thresholds (e.g., memory > 1GB, success rate < 95%)
3. **Add more resources** to track specific data sources
4. **Set up alerting** using Grafana's alert rules

Enjoy your observability! 🚀
