# Network Security Monitoring — Roadmap

**Status**: Informational — not actionable until Stage 2 (Droplet deployment)

---

## Wireshark: What It Is and Isn't

**Wireshark is a network protocol analyzer** (packet sniffer). It captures and displays network
traffic for manual inspection. It is excellent for debugging and incident investigation, but it
is **not** an IDS/IPS — it does not detect or block attacks automatically. It is passive and
manual.

### When Useful for SKUEL

- Debugging TLS issues during AuraDB migration (`neo4j+s://` connections)
- Verifying Neo4j bolt connection encryption (confirming no plaintext credentials on the wire)
- Investigating suspicious traffic during a security incident
- Profiling HTTP response sizes and latency for performance tuning

### When Not Useful

- Automated intrusion detection — Wireshark requires a human watching traffic in real time
- Production monitoring — no alerting, no dashboards, no persistent rules
- Prevention — Wireshark observes; it never blocks

---

## Actual IDS/IPS Tools

| Tool | Type | Description |
|------|------|-------------|
| **Snort** | Network IDS/IPS | Signature-based detection, open source, mature ecosystem |
| **Suricata** | Network IDS/IPS | Multi-threaded modern alternative to Snort, same ruleset compatibility |
| **Wazuh** | Host-based IDS | OSSEC fork — file integrity monitoring, log analysis, rootkit detection |
| **OSSEC** | Host-based IDS | Original host-based IDS — lighter than Wazuh, less actively maintained |
| **Fail2ban** | Host-based prevention | Monitors logs for brute force, bans IPs via firewall rules |

---

## When Relevant for SKUEL

| Stage | Need |
|-------|------|
| **Stage 1 (Docker, local)** | Not needed. No public exposure. |
| **Stage 2 (Droplet)** | Fail2ban for SSH brute force. Consider Suricata if traffic volume warrants. |
| **Stage 3 (AuraDB + App Platform)** | Network IDS shifts to cloud provider. Focus on application-level monitoring (Prometheus alerts, structured logging). |

---

## Recommended Learning Path

1. **Wireshark first** — understand network protocols, inspect bolt/HTTP traffic, build intuition
   for what normal traffic looks like
2. **Fail2ban** — immediate practical value for any public-facing server (SSH, HTTP endpoints)
3. **Suricata** — automated network detection when public traffic volume justifies it
4. **Wazuh** — host-level integrity monitoring for production servers

---

**Related**:
- `/docs/deployment/DO_MIGRATION_GUIDE.md` — Stage 2 deployment
- `/docs/deployment/AURADB_MIGRATION_GUIDE.md` — Stage 3 deployment
- `/docs/roadmap/security-hardening-deferred.md` — deferred security items
- `monitoring/README.md` — current Prometheus/Grafana observability stack
