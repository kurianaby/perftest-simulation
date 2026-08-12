# REST API Load Test Results

## Scope

Load test of three REST endpoints at `jsonplaceholder.typicode.com`:

| Transaction | Method | Path |
|---|---:|---|
| `100_Create_Post` | `POST` | `/posts` |
| `200_List_Posts` | `GET` | `/posts` |
| `300_Get_Single_Post` | `GET` | `/posts/{id}` |

The endpoints were exercised as a simulated three-step business journey rather than in isolation.

### Simulated journey

1. Create a post.
2. List all posts and select one at random.
3. Retrieve that post and assert that its `id` and `title` match the values observed in the list response.

---

## Key metrics

### Local baseline

**Profile:** 20 users, 90-second ramp-up, 300-second steady state.  
**Execution:** Local.

| Window | Samples | Throughput |
|---|---:|---:|
| Full run | 4,896 | 16.4 requests/s |
| Steady state, post-ramp | 3,978 | 19.1 requests/s |

### Steady-state response times

Response times are in milliseconds. The steady-state window excludes the ramp-up period.

| Transaction | Samples | p50 | p90 | p95 | p99 | Max |
|---|---:|---:|---:|---:|---:|---:|
| `100_Create_Post` | 1,328 | 99 | 105 | 108 | 144 | 343 |
| `200_List_Posts` | 1,322 | 22 | 27 | 29 | 60 | 110 |
| `300_Get_Single_Post` | 1,328 | 21 | 27 | 31 | 67 | 80 |

### Full-run response times

Response times are in milliseconds and include the ramp-up window.

| Transaction | Samples | p50 | p90 | p95 | p99 | Max |
|---|---:|---:|---:|---:|---:|---:|
| `100_Create_Post` | 1,640 | 99 | 105 | 133 | 153 | 727 |
| `200_List_Posts` | 1,630 | 22 | 27 | 29 | 60 | 307 |
| `300_Get_Single_Post` | 1,626 | 21 | 27 | 32 | 67 | 104 |

---

## Observations

### Write latency is materially higher

The write path is approximately **4.5× slower** than the read paths at the median: 99 ms for `POST /posts`, compared with 21–22 ms for the two `GET` transactions.

Because JSONPlaceholder does not persist writes, this difference cannot be attributed to storage or application compute for a newly created resource. A likely explanation is that the `GET` endpoints are served from a CDN edge, while the `POST` requires a full round trip to the origin.

### Percentile gates must be transaction-specific

Latency thresholds should be evaluated per transaction, never as a single aggregate percentile.

The three transactions have materially different latency profiles, with `100_Create_Post` dominating the upper end of the combined distribution. An aggregate percentile would change when the transaction mix changes, even if the behaviour of every endpoint remains unchanged. It would therefore measure the load model as much as the system under test.


### The ramp-up period affects the write path

Excluding the ramp-up window lowers the `POST` p95 from 133 ms to 108 ms and reduces its maximum from 727 ms to 343 ms. The two `GET` transactions are effectively unchanged between the full-run and steady-state windows.

This pattern is consistent with TLS handshake and connection-pool establishment overhead on the origin round trip, which is amortised after connections are warm. For this reason, it is better for latency gates to evaluate the post-warm-up, steady-state window only.

---

## CI error rate

The CI run recorded a **0.02% error rate**: one failed sample out of 5,079. This is well below the configured 0.5% threshold.

The local baseline run recorded no failed samples.

---

## Limitations

- **JSONPlaceholder does not persist writes.** `POST /posts` always returns `id: 101`, and the created resource cannot subsequently be retrieved. The current journey therefore verifies an existing record rather than a true read-after-write flow.
- **Correlation pattern is demonstrated but not exercised end-to-end.** Against a real API, the created `id` would be extracted from the POST response and used in the subsequent GET. This is the pattern that detects read-after-write consistency issues in replicated data stores. The extractor is present and commented in the test plan.
- **Public internet conditions affect results.** This test measures DNS resolution, TLS negotiation, CDN behaviour and network-path variability alongside application performance. Percentile variation is therefore influenced substantially by factors outside the system under test.
- **The baseline is based on one run.** Running the same profile three times at different times of day would help distinguish system behaviour from network variance. A production calibration should use a distribution of results rather than a single point estimate.
- **Only one load profile is currently used.** Pull request, scheduled and manual triggers all execute the same 20-user profile against the same threshold file.

---

## Scaling to a broader NFT strategy

The current baseline can be expanded into a broader non-functional testing strategy.

### Trigger-specific profiles

| Trigger | Intended profile | Purpose |
|---|---|---|
| Pull request | Low-volume validation run | Fast feedback and regression gating for every change |
| Nightly scheduled run | Full load profile | Detect performance drift under representative load |
| Manual run | Selectable profile | Support targeted diagnosis, release validation and exploratory testing |

### Additional test exercises

- **Soak testing:** Run sustained representative load to identify resource leaks, gradual latency degradation and connection exhaustion.
- **Stress testing:** Increase load beyond the expected operating range to find saturation points and validate graceful degradation.
- **Failover testing:** Introduce controlled dependency, node or availability-zone failures while maintaining load to validate resilience and recovery behaviour.
- **Disaster recovery testing:** Validate recovery-time and recovery-point objectives under a rehearsed regional or service-level disruption scenario.

### Correlate client and server telemetry

Client-side timings should be correlated with server-side observability data to identify the source of performance changes. Useful telemetry includes:

- Pod or container CPU and memory utilisation.
- Connection-pool utilisation and saturation.
- Garbage-collection pauses.
- Database query latency, lock waits and connection usage.
- Upstream dependency latency and error rates.
- Network, ingress and CDN metrics.

### **Time taken:** over 2 hours across scripting, calibration, CI wiring and writeup