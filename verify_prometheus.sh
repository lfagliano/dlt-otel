#!/bin/bash

# verify_prometheus.sh
# Quick script to verify Prometheus is scraping DLT metrics

set -e

PROMETHEUS_URL="${PROMETHEUS_URL:-http://localhost:9090}"

echo "============================================"
echo "DLT Metrics Verification Script"
echo "============================================"
echo ""
echo "Checking Prometheus at: $PROMETHEUS_URL"
echo ""

# Check if Prometheus is reachable
echo "1️⃣  Testing Prometheus connection..."
if curl -s "$PROMETHEUS_URL/-/healthy" > /dev/null; then
    echo "✅ Prometheus is reachable"
else
    echo "❌ Cannot reach Prometheus at $PROMETHEUS_URL"
    echo "   Set PROMETHEUS_URL environment variable if using a different URL"
    exit 1
fi

echo ""
echo "2️⃣  Checking for DLT metrics..."

# List of expected DLT metrics
METRICS=(
    "dlt_items_total"
    "dlt_jobs_total"
    "dlt_resources_total"
    "dlt_files_total"
    "dlt_system_memory_usage_mb"
    "dlt_system_cpu_percent"
)

FOUND_COUNT=0
TOTAL_COUNT=${#METRICS[@]}

for metric in "${METRICS[@]}"; do
    result=$(curl -s "$PROMETHEUS_URL/api/v1/query?query=$metric" | grep -o '"status":"success"' || true)
    
    if [ -n "$result" ]; then
        # Check if there are actual data points
        data_points=$(curl -s "$PROMETHEUS_URL/api/v1/query?query=$metric" | grep -o '"result":\[.*\]' | grep -o '\[.*\]' | grep -v '^\[\]$' || true)
        
        if [ -n "$data_points" ]; then
            echo "✅ $metric - FOUND with data"
            FOUND_COUNT=$((FOUND_COUNT + 1))
        else
            echo "⚠️  $metric - EXISTS but no data points yet"
        fi
    else
        echo "❌ $metric - NOT FOUND"
    fi
done

echo ""
echo "============================================"
echo "Summary: Found $FOUND_COUNT/$TOTAL_COUNT metrics with data"
echo "============================================"
echo ""

if [ $FOUND_COUNT -eq 0 ]; then
    echo "❌ No DLT metrics found in Prometheus!"
    echo ""
    echo "Troubleshooting steps:"
    echo "1. Run a DLT pipeline with OpenTelemetryCollector:"
    echo "   python3 test_standalone_collector.py"
    echo ""
    echo "2. Check OpenTelemetry Collector is running:"
    echo "   docker ps | grep otel"
    echo ""
    echo "3. Verify OTEL Collector config exports to Prometheus"
    echo "   (See GRAFANA_DASHBOARD_GUIDE.md for config example)"
    echo ""
    echo "4. Check Prometheus is scraping OTEL Collector:"
    echo "   curl $PROMETHEUS_URL/api/v1/targets"
    echo ""
    exit 1
elif [ $FOUND_COUNT -lt $TOTAL_COUNT ]; then
    echo "⚠️  Some metrics are missing. This might be okay if:"
    echo "   - You haven't run a pipeline yet (missing pipeline metrics)"
    echo "   - psutil is not installed (missing system metrics)"
    echo ""
    echo "The Grafana dashboard will work with available metrics."
    echo ""
else
    echo "✅ All DLT metrics are available!"
    echo ""
    echo "🎉 Ready to import Grafana dashboard!"
    echo ""
    echo "Next steps:"
    echo "1. Import grafana_dashboard.json into Grafana"
    echo "2. Select your Prometheus data source"
    echo "3. View the 'DLT Pipeline Observability' dashboard"
    echo ""
fi

# Show example queries
echo "============================================"
echo "Example Prometheus Queries"
echo "============================================"
echo ""
echo "View all DLT metrics:"
echo "  curl '$PROMETHEUS_URL/api/v1/label/__name__/values' | grep dlt"
echo ""
echo "Check pipeline throughput:"
echo "  curl '$PROMETHEUS_URL/api/v1/query?query=rate(dlt_items_total[5m])'"
echo ""
echo "View in Prometheus UI:"
echo "  $PROMETHEUS_URL/graph"
echo ""
