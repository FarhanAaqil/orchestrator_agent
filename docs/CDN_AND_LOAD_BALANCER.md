# Load Balancer, Reverse Proxy & Edge CDN Architecture

This document describes the production load balancing, reverse proxying, and Edge CDN caching tier for the **Orchestrator Agent**.

---

## 1. Architectural Overview

```
                          [ Internet / Users ]
                                   │
                                   ▼
                   ┌───────────────────────────────┐
                   │   Edge CDN Layer (Cloudflare) │
                   │  - DDoS Protection & SSL      │
                   │  - Static Asset Edge Caching  │
                   └───────────────┬───────────────┘
                                   │
                                   ▼
                   ┌───────────────────────────────┐
                   │   Nginx / Caddy Reverse Proxy │
                   │  - Rate Limiting (30 req/s)   │
                   │  - Microcache for Assets      │
                   │  - Least-Connections LB       │
                   └───────────────┬───────────────┘
                                   │
                     ┌─────────────┴─────────────┐
                     ▼                           ▼
            ┌─────────────────┐         ┌─────────────────┐
            │  Orchestrator   │         │  Orchestrator   │
            │  Node 1 (:8000) │         │  Node 2 (:8000) │
            └─────────────────┘         └─────────────────┘
```

---

## 2. Load Balancer Configuration (Nginx)

The [`nginx/nginx.conf`](../nginx/nginx.conf) file configures:
- **Upstream Pool (`orchestrator_backend`)**: Distributes incoming traffic using the `least_conn` algorithm across worker instances.
- **Failover & Health Probing**: Automatically detects unhealthy nodes (`max_fails=3 fail_timeout=10s`) and routes traffic exclusively to healthy replicas.
- **Connection Keepalive**: Reuses persistent TCP connections (`keepalive 32`) to the backend to eliminate connection handshake overhead.
- **Rate Limiting (`limit_req_zone`)**: Enforces a 30 req/sec cap per client IP with a burst allowance of 15 for `/route` and `/dispatch`.
- **Streaming Support**: Disables buffering (`proxy_buffering off`) for LLM streaming and long-lived agent completions.

---

## 3. Edge CDN Caching Rules (Cloudflare / Fastly)

When fronting Orchestrator Agent with a CDN (such as Cloudflare, Fastly, or CloudFront), configure the following Cache Rules:

| Rule Name | URI Pattern | Action | Edge TTL | Browser TTL |
|---|---|---|---|---|
| **Static Assets** | `/static/*` | **Cache Everything** | 7 Days | 7 Days |
| **Favicon & Web Fonts** | `/*.ico`, `*.woff2` | **Cache Everything** | 30 Days | 30 Days |
| **API Endpoints** | `/route`, `/dispatch`, `/pipeline/*` | **Bypass Cache** | 0s | 0s |
| **Approval Actions** | `/approvals/*` | **Bypass Cache** | 0s | 0s |
| **Health Check** | `/health` | **Bypass Cache** | 0s | 0s |

### Recommended Cloudflare Page Rules / Transform Rules:
1. **Cache Control**: Enable `Origin Cache Control` so headers emitted by the application are honored.
2. **Minification**: Enable Brotli compression and Early Hints.
3. **WebSockets**: Enable WebSockets for live status updates if required.

---

## 4. Multi-Container Orchestration (`docker-compose.yml`)

The primary `docker-compose.yml` can orchestrate both the FastAPI application and the Nginx load balancer:

```bash
# Start the full stack with Nginx load balancer
docker compose up -d
```

Nginx will listen on port `80` (or `443` with SSL certs) and transparently proxy requests to the internal `orchestrator` cluster.
