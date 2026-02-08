# SKUEL Grafana Dashboards

This directory contains version-controlled Grafana dashboards for SKUEL observability.

## Dashboards

### Phase 1: Foundation (Implemented)
- *(No dashboards yet - create in Grafana UI after Phase 2)*

### Phase 2: System Health (Planned)
- `system_health.json` - HTTP requests, Neo4j queries, system resources

### Phase 3: Domain Activity (Planned)
- `domain_activity.json` - Entity creation/completion, event bus metrics

### Phase 4: Graph Health (PRIMARY GOAL)
- `graph_health.json` - Graph density, lateral relationships, BLOCKS tracking

### Phase 5: Search & Intelligence (Planned)
- `search_intelligence.json` - Search quality, UserContext builds, recommendations

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

See: `/docs/observability/PROMETHEUS_METRICS.md` (to be created in Phase 5)
