# Migrating a Monolith to a Zero-Trust, Event-Driven System on AWS

*A technical walkthrough of the SwiftCart cloud migration — what I built, why
each decision was made, and how I verified it end to end.*

---

## The problem with the monolith

SwiftCart started as a single application where a customer *browsing* a
product and a customer *checking out* fought over the same database locks and
threads. One slow checkout degraded everyone's browsing. The network was flat:
once something got inside the perimeter, lateral movement was trivial.

The migration goal was a system that is **isolated by default**, **decoupled
under load**, and **cheap when idle** — without losing the ability to debug it
in production.

This post walks the architecture in four layers: the network, the application,
the edge and storage, and finally serverless + observability. Everything here
was built and verified in `us-west-2`.

---

## Layer 1 — A zero-trust network that assumes breach

The first decision was to stop trusting the network. Infrastructure is split
into two VPCs:

- **VPC A — Public DMZ** (`10.10.0.0/16`): ALB, Web Portal, Bastion. Has an
  Internet Gateway and NAT.
- **VPC B — Dark / Private** (`10.20.0.0/16`): the Inventory microservice.
  **No Internet Gateway. No NAT. No public egress at all.**

The only path between them is a **Transit Gateway**, with deliberately
asymmetric routing so VPC B can answer VPC A but can never originate traffic to
the internet (there is simply no IGW for its `0.0.0.0/0` route to reach).

That immediately raises a problem: if VPC B can't reach the internet, how does
it call SNS or SQS? The answer is **AWS PrivateLink**. Interface VPC endpoints
inject ENIs for SNS and SQS directly into VPC B's subnet, and API calls travel
the internal AWS backbone. The public internet is removed from the attack
surface, not just firewalled off.

Security groups reference *each other* instead of CIDRs wherever possible —
e.g. the Web Portal accepts port 80 only from the ALB's security group, and
SSH only from the bastion's. Access is scoped to identity, not location. And
there are **zero long-lived access keys** anywhere: EC2 instances assume IAM
roles through instance profiles and the metadata service rotates credentials
automatically.

> Verification: the VPC list shows the two CIDRs; the endpoints list shows
> `com.amazonaws.us-west-2.sqs` and `.sns` as `Interface` endpoints inside the
> dark VPC.

---

## Layer 2 — CQRS: reads and writes are not the same thing

With the network in place, the application splits along the CQRS seam.

**Reads are synchronous.** A product page needs an answer *now*, so the Web
Portal makes a direct HTTP call across the Transit Gateway to the Inventory
Service's Flask API. It uses a 2-second timeout — if the backend is slow, the
request fails fast instead of cascading.

**Writes are asynchronous.** A checkout is a mutation; doing it synchronously
would couple the web tier to the inventory database. Instead the Web Portal
publishes an event to SNS and immediately returns `202 Accepted`. The customer
gets an instant acknowledgement; stock deduction happens later.

The decoupling comes from an **SNS → SQS fan-out**. One `publish` reaches two
independent subscribers:

1. an **email subscription** for instant customer confirmation, and
2. an **SQS queue** that buffers work for the consumer.

SQS is the shock absorber. If the consumer falls behind, queue depth grows but
nothing is lost and the web tier never notices. This is eventual consistency,
made explicit and observable.

> Verification: `curl /checkout` returned
> `{"order_id":"3380c03d-…","status":"Accepted"}`, and a subsequent
> `curl /product/SKU-1001` returned `"stock":48` — proving an earlier order of
> 2 units (50 → 48) had been processed asynchronously.

---

## Layer 3 — One domain at the edge, the right disk per tier

Hitting the load balancer directly works but doesn't scale as a product. A
single **CloudFront distribution** becomes a Layer 7 router:

| Path | Origin | Cached? |
|------|--------|---------|
| `Default (*)` | S3 static bucket | Yes (CachingOptimized) |
| `/api/*`, `/checkout` | ALB | No (CachingDisabled, AllViewer) |

The S3 bucket has **Block all public access** on; CloudFront reads it through
an Origin Access Control. Static assets are cached hard at the edge, while
dynamic traffic is proxied over AWS's optimized network straight to the ALB —
and from there across the Transit Gateway into the dark VPC.

Storage is matched to the workload:

- **EFS** for the web tier — a shared NFS file system mounted by every Web
  Portal instance, so an upload on one box is visible on the others.
- **EBS gp3 + XFS** for the inventory tier — a dedicated 3000-IOPS block
  device that doesn't share IOPS with the OS root volume.

The mental model: EFS is a network drive many machines share; EBS is a fast
local disk bolted to one machine.

---

## Layer 4 — Going serverless, and being able to see it

The original consumer was a Python daemon thread running `while True` to
long-poll SQS. That pays for an EC2 instance even at zero orders and
bottlenecks on a single thread at high volume.

It was replaced with an **AWS Lambda** (`SwiftCart-Order-Processor`,
Python 3.12, **arm64/Graviton**) wired to SQS via an **event source mapping**
with batch size 10. Now AWS polls the queue; the function runs only when work
exists and scales out automatically. It returns `batchItemFailures` so a
poison message is retried (and eventually dead-lettered) without losing the
good messages in its batch.

The web tier was containerized at the same time — `python:3.11-slim`,
12-factor config from environment variables, run via `docker-compose`. The
container is immutable "cattle": if it misbehaves you replace it, you don't
patch it.

None of this is operable without observability:

- **CloudWatch Logs** capture every Lambda invocation. A real checkout
  produced `Lambda invoked → Processing Order ID 3380c03d-… → SUCCESS`, and
  that order ID is *the same one* the checkout endpoint returned — a complete
  trace through the async path.
- A **CloudWatch alarm** on `ApproximateNumberOfMessagesVisible ≥ 100` fires
  an SNS email alert when consumers fall behind.
- **CloudTrail** records every management API call to S3, so "who deleted the
  event source mapping" has a definitive answer.

---

## What I'd change for production

The lab keeps inventory in an in-memory dict. In production the Lambda would
write to **DynamoDB or RDS**, since Lambda is stateless. IAM would use inline
policies scoped to exact ARNs rather than managed full-access policies. And the
ALB would terminate TLS with ACM rather than serving plain HTTP behind
CloudFront.

## Takeaway

The interesting part of this migration wasn't any single service — it was the
*shape*: isolate aggressively, decouple writes, push static content to the
edge, make idle compute free, and instrument everything so the system can be
operated, not just deployed.

*Source code, per-domain design docs, and console screenshots:
[github repo link].*
