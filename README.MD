# Performance test with NFR gating in CI
 
JMeter load test of a three-step journey against `jsonplaceholder.typicode.com`, gated
in GitHub Actions against NFRs held as versioned configuration. Measured results:
[RESULTS.MD](RESULTS.MD).
 
```
thresholds.yaml          NFRs as code — the contract the pipeline enforces
tests/                   JMeter test plan
ci/check_thresholds.py   Gate — fails the build on breach
docs/baseline/           Committed baseline evidence
.github/workflows/       Pipeline
```
 
Thresholds provided in YAML, so modifying an NFR is easy and not a code change.
Percentiles are gated per transaction, never in aggregate. Latency is measured
excluding the ramp-up; errors and sample count across the full run. 
 
## Run locally
 
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
jmeter -n -t tests/<plan>.jmx -Jusers=20 -Jrampup=90 -Jduration=300 \
  -l results/baseline.jtl -e -o results/baseline-dashboard
python ci/check_thresholds.py results/baseline.jtl thresholds.yaml --warmup-seconds 90
```
 
Pinned: JMeter 5.6.3, Java 21, Python 3.13, PyYAML 6.0.2.
 
## Roadmap to production grade (GCP / AWS)
 
1. **Generate load next to the target.** Local p95 was 108ms against 17ms in CI — same
   plan, different network position. 
   Run generators
   in-VPC on ephemeral Terraform infrastructure: GKE or k6 Operator; EKS or Fargate.
2. **Correlate with server-side telemetry.** Cloud Monitoring and Trace, or CloudWatch
   and X-Ray, on a shared timeline with run-ID tagging.
3. **Test beyond load.** Soak, stress, failover and DR — exercised *under* load. GCP fault injection; AWS FIS.
4. **Realistic test data.** Generate synthetic data
   at production cardinality and skew (Dataflow / Glue); credentials from Secret
   Manager.
5. **Tier the pipeline.** Validation on PR, load nightly, soak and resilience per
   release — each with its own threshold file. Persist percentiles for run-over-run
   regression alongside fixed gates.
6. **Govern it.** Per-service budgets owned by service teams; NFRs sourced from
   requirements and production telemetry rather than from observed behaviour.