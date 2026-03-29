# Phase 3: Production Rollout Plan

**Extended Model Implementation - Production Deployment**

*Date: March 29, 2026*  
*Status: Ready for Production*

---

## Phase 3 Overview

| Phase | Task | Status | Owner |
|-------|------|--------|-------|
| 3.1 | Integration tests | ✅ Complete | Engineering |
| 3.2 | Documentation update | ✅ Complete | Engineering |
| 3.3 | Performance benchmarks | ⏳ Pending | QA |
| 3.4 | Production rollout | ⏳ Pending | DevOps |
| 3.5 | Monitoring setup | ⏳ Pending | DevOps |

---

## Rollout Strategy

### Staged Rollout (4 Phases)

| Stage | Duration | Traffic | Success Criteria | Rollback Trigger |
|-------|----------|---------|------------------|------------------|
| **Alpha** | 4 hours | Internal (1%) | No P0 bugs | Any P0 bug |
| **Beta** | 24 hours | 10% | Cost < $1/run | Cost > $2/run |
| **Canary** | 48 hours | 50% | Quality > 7.5/10 | Quality < 7/10 |
| **GA** | Ongoing | 100% | All metrics green | Any metric red |

---

## Pre-Rollout Checklist

### Infrastructure
- [ ] OpenRouter API key configured
- [ ] All 11 provider keys available (optional)
- [ ] Database schema updated for cost tracking
- [ ] Monitoring dashboard deployed

### Testing
- [ ] All unit tests pass (`pytest tests/test_extended_router.py`)
- [ ] All integration tests pass (`pytest tests/test_reasoning_integration.py`)
- [ ] Backward compatibility verified
- [ ] Performance benchmarks meet targets

### Documentation
- [ ] USAGE.md updated with router examples
- [ ] API documentation updated
- [ ] Migration guide published
- [ ] Runbook created for on-call

### Communication
- [ ] Release notes drafted
- [ ] Stakeholders notified
- [ ] Support team trained
- [ ] Status page updated

---

## Rollout Commands

### Phase 1: Alpha (Internal)

```bash
# Deploy to internal environment
kubectl set image deployment/berb-reasoning \
  reasoner=berb/reasoning:v2.0-extended \
  -n berb-internal

# Watch logs
kubectl logs -f deployment/berb-reasoning -n berb-internal

# Verify cost tracking
kubectl exec -it deployment/berb-reasoning -n berb-internal -- \
  python -c "from berb.metrics import get_cost_tracker; t = get_cost_tracker(); print(t.get_summary())"
```

### Phase 2: Beta (10% Traffic)

```bash
# Update traffic split (Istio example)
cat <<EOF | kubectl apply -f -
apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
metadata:
  name: berb-reasoning
spec:
  hosts:
  - berb-reasoning
  http:
  - route:
    - destination:
        host: berb-reasoning-v2
      weight: 10
    - destination:
        host: berb-reasoning-v1
      weight: 90
EOF

# Monitor metrics
kubectl port-forward svc/berb-reasoning 9090:9090
# Open: http://localhost:9090/metrics
```

### Phase 3: Canary (50% Traffic)

```bash
# Update traffic split to 50/50
kubectl patch virtualservice berb-reasoning --type='json' \
  -p='[{"op": "replace", "path": "/spec/http/0/route/0/weight", "value": 50},
       {"op": "replace", "path": "/spec/http/0/route/1/weight", "value": 50}]'

# Watch cost metrics
watch 'curl -s http://localhost:9090/metrics | grep berb_cost'
```

### Phase 4: General Availability (100%)

```bash
# Full rollout
kubectl set image deployment/berb-reasoning \
  reasoner=berb/reasoning:v2.0-extended \
  -n berb-production

# Update traffic to 100%
kubectl patch virtualservice berb-reasoning --type='json' \
  -p='[{"op": "replace", "path": "/spec/http/0/route/0/weight", "value": 100},
       {"op": "replace", "path": "/spec/http/0/route/1/weight", "value": 0}]'

# Tag release
git tag -a v2.0-extended-production -m "Production release: 97% cost savings"
git push origin v2.0-extended-production
```

---

## Monitoring Metrics

### Key Metrics to Track

| Metric | Target | Warning | Critical |
|--------|--------|---------|----------|
| Cost per run | < $1.00 | > $1.50 | > $2.00 |
| P99 latency | < 100ms | > 200ms | > 500ms |
| Error rate | < 1% | > 3% | > 5% |
| Fallback rate | < 10% | > 20% | > 30% |
| Provider diversity | All < 40% | Any > 50% | Any > 60% |
| Quality score | > 8/10 | < 7.5/10 | < 7/10 |

### Prometheus Alerts

```yaml
# alerts/berb-reasoning.yaml
groups:
- name: BerbReasoning
  rules:
  - alert: HighCostPerRun
    expr: avg(berb_reasoning_cost_per_run) > 2.0
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "Cost per run exceeds $2.00"
  
  - alert: HighErrorRate
    expr: rate(berb_reasoning_errors_total[5m]) > 0.05
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "Error rate exceeds 5%"
  
  - alert: ProviderConcentration
    expr: max(berb_provider_usage_percentage) > 60
    for: 10m
    labels:
      severity: warning
    annotations:
      summary: "Single provider exceeds 60% of usage"
  
  - alert: HighLatency
    expr: histogram_quantile(0.99, rate(berb_reasoning_latency_bucket[5m])) > 0.5
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "P99 latency exceeds 500ms"
```

### Grafana Dashboard

```json
{
  "dashboard": {
    "title": "Berb Reasoning - Extended Models",
    "panels": [
      {
        "title": "Cost per Run (7 days)",
        "targets": [{
          "expr": "avg(berb_reasoning_cost_per_run)"
        }]
      },
      {
        "title": "Provider Distribution",
        "targets": [{
          "expr": "berb_provider_usage_percentage"
        }]
      },
      {
        "title": "Error Rate",
        "targets": [{
          "expr": "rate(berb_reasoning_errors_total[5m])"
        }]
      },
      {
        "title": "Latency (P50, P95, P99)",
        "targets": [{
          "expr": "histogram_quantile(0.99, rate(berb_reasoning_latency_bucket[5m]))"
        }]
      }
    ]
  }
}
```

---

## Rollback Procedures

### Automatic Rollback Triggers

| Trigger | Action | Threshold |
|---------|--------|-----------|
| Cost spike | Rollback to v1 | > $5/run for 5min |
| Error spike | Rollback to v1 | > 10% for 5min |
| Latency spike | Rollback to v1 | P99 > 1s for 5min |
| Quality drop | Investigate | < 6/10 for 10min |

### Manual Rollback Commands

```bash
# Immediate rollback to v1
kubectl rollout undo deployment/berb-reasoning -n berb-production

# Revert traffic to v1
kubectl patch virtualservice berb-reasoning --type='json' \
  -p='[{"op": "replace", "path": "/spec/http/0/route/0/weight", "value": 0},
       {"op": "replace", "path": "/spec/http/0/route/1/weight", "value": 100}]'

# Notify stakeholders
curl -X POST -H 'Content-type: application/json' \
  --data '{"text":"🚨 Rolled back Berb Reasoning to v1 due to [REASON]"}' \
  $SLACK_WEBHOOK_URL
```

---

## Post-Rollout Verification

### Day 1 Checks

- [ ] Cost per run < $1.00
- [ ] Error rate < 1%
- [ ] P99 latency < 100ms
- [ ] All 9 methods functional
- [ ] Cost tracking operational
- [ ] Provider diversity maintained

### Week 1 Checks

- [ ] Cost savings > 95% vs baseline
- [ ] No quality regressions reported
- [ ] All alerts functioning
- [ ] Runbook tested
- [ ] Support team comfortable

### Month 1 Checks

- [ ] Cost savings validated ($267k/year projected)
- [ ] Zero P0 incidents
- [ ] User satisfaction > 90%
- [ ] Performance benchmarks met
- [ ] Documentation complete

---

## Success Criteria

### Phase 3 Complete When:

- ✅ All integration tests pass
- ✅ Documentation published
- ✅ Performance benchmarks meet targets
- ✅ Production rollout successful (4 stages)
- ✅ Monitoring dashboard operational
- ✅ On-call team trained
- ✅ Zero P0 incidents in first week

### Expected Outcomes:

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Cost per run | $23.00 | $0.69 | 97% |
| Monthly cost | $23,000 | $690 | 97% |
| Annual cost | $276,000 | $8,280 | 97% |
| Provider diversity | 100% OpenAI | 11 providers | Risk reduction |

---

## Contact Information

| Role | Name | Contact |
|------|------|---------|
| Engineering Lead | [Name] | [Email/Slack] |
| DevOps Lead | [Name] | [Email/Slack] |
| QA Lead | [Name] | [Email/Slack] |
| On-Call | Rotation | [PagerDuty] |

---

**Document Version:** 1.0  
**Last Updated:** March 29, 2026  
**Next Review:** After production rollout

---

## Appendix: Quick Reference

### Cost Tracking Query

```sql
-- Get cost summary for last 7 days
SELECT 
  method,
  SUM(cost_usd) as total_cost,
  AVG(cost_usd) as avg_cost,
  COUNT(*) as executions
FROM reasoning_costs
WHERE timestamp >= datetime('now', '-7 days')
GROUP BY method
ORDER BY total_cost DESC;
```

### Provider Diversity Query

```sql
-- Get provider distribution
SELECT 
  provider,
  COUNT(*) as calls,
  SUM(cost_usd) as cost,
  COUNT(*) * 100.0 / SUM(COUNT(*)) OVER() as percentage
FROM reasoning_costs
WHERE timestamp >= datetime('now', '-1 days')
GROUP BY provider
ORDER BY percentage DESC;
```

### Performance Query

```sql
-- Get P50/P95/P99 latency by method
SELECT 
  method,
  AVG(duration_ms) as avg_ms,
  -- Add percentile calculations based on your DB
FROM reasoning_costs
WHERE timestamp >= datetime('now', '-1 days')
GROUP BY method;
```
