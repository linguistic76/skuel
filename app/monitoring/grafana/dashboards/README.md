# SKUEL Grafana Dashboards

This directory contains version-controlled Grafana dashboards for SKUEL observability.

## Dashboards

- `system_health.json` — HTTP requests, Neo4j queries
- `domain_activity.json` — Entity creation/completion by domain
- `graph_health.json` — Graph density, lateral relationships, BLOCKS tracking, Knowledge Subgraph Health row (ADR-080 H1: Ku totals, orphan ratio, composition coverage, degree, prerequisite/ORGANIZES edges)
- `event_bus.json` — Event publication rate, handler latency, errors

## Workflow

1. **Create dashboard in Grafana UI**: http://localhost:3000
2. **Export dashboard**:
   ```bash
   # Get dashboard UID from URL: /d/{uid}/...
   curl -H "Authorization: Bearer {api_key}" \
     http://localhost:3000/api/dashboards/uid/{uid} | jq .dashboard > {name}.json
   ```
3. **Commit to version control**
4. **Auto-loads on restart** (via provisioning config)

## Dashboard Style Guide

- **Panel titles**: Clear, action-oriented (e.g., "HTTP Request Rate" not "Requests")
- **Time ranges**: Default to Last 6 hours for development
- **Variables**: Use label-based filtering for operational dimensions (e.g., `$search_type`, `$layer`). Do NOT use `user_uid` — per-user data belongs in Neo4j, not Prometheus.
- **Colors**: Blue (hierarchical), Green (lateral), Orange (semantic), Purple (cross-domain)
- **Units**: Use appropriate units (ops/s, ms, %, bytes)

See: `/docs/observability/PROMETHEUS_METRICS.md`
