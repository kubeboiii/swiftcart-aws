# SwiftCart: Zero-Trust, Event-Driven Architecture on AWS

A hands-on cloud engineering project that migrates a monolithic e-commerce
backend ("SwiftCart") into a **zero-trust, event-driven, partly-serverless**
system on AWS. Built and verified end-to-end in the AWS console + CLI in
`us-west-2`.

> This repository documents a completed hands-on implementation. Every claim
> below is backed by a console/CLI screenshot in [`screenshots/`](screenshots).

---

## What this demonstrates

- **Zero-Trust networking** — two isolated VPCs, one of them fully *dark*
  (no internet path), connected only through a Transit Gateway
- **AWS PrivateLink** — SNS/SQS reached from the dark VPC over interface
  endpoints, never the public internet
- **CQRS** — synchronous reads and asynchronous writes split into separate
  paths
- **SNS → SQS fan-out** — one event, two independent subscribers (email +
  durable queue)
- **Edge delivery** — a single CloudFront distribution multiplexing an S3
  static origin and a dynamic ALB origin
- **Persistent storage** — shared EFS for the web tier, dedicated XFS-on-gp3
  EBS for the backend
- **Serverless modernization** — the polling consumer replaced by an SQS-
  triggered Lambda; the web tier containerized with Docker
- **Observability & auditing** — CloudWatch logs/alarms + CloudTrail

## High-level architecture

```
                         ┌─────────────────────────────┐
        User ──────────► │      CloudFront (CDN)        │
                         │  /*  → S3 (static, cached)   │
                         │  /api/*, /checkout → ALB     │
                         └───────────────┬─────────────┘
                                         │
   VPC A — Public DMZ (10.10.0.0/16)     ▼
   ┌───────────────────────────────────────────────────┐
   │  ALB → Web Portal (Docker)   Bastion   EFS mount   │
   └───────────────┬───────────────────────────────────┘
                    │  Transit Gateway (only path between VPCs)
   VPC B — Dark / Private (10.20.0.0/16) │  no IGW · no NAT
   ┌────────────────▼──────────────────────────────────┐
   │  Inventory Service (Flask :5000) + gp3/XFS EBS     │
   │  PrivateLink endpoints → SNS, SQS                  │
   └───────────────────────────────────────────────────┘

   Async write path (regional, not in any VPC):
   Web Portal ─publish─► SNS ─┬─► Email subscriber
                              └─► SQS ─► Lambda (arm64, batch=10)
                                          └─► CloudWatch Logs
   CloudWatch Alarm (SQS depth ≥ 100) · CloudTrail → S3 audit
```

## Documentation

The design is documented by architectural domain:

1. [Networking & Zero-Trust Backbone](docs/01-networking-zero-trust.md)
2. [Application Layer: CQRS & Messaging](docs/02-application-cqrs-messaging.md)
3. [Edge Delivery & Persistent Storage](docs/03-edge-delivery-storage.md)
4. [Serverless Modernization & Observability](docs/04-serverless-observability.md)

## Repository layout

```
swiftcart-aws/
├── README.md
├── docs/                       # design docs, organized by domain
├── screenshots/                # real console/CLI evidence (01–13)
└── src/
    ├── web-portal/             # Flask front-end (EC2 + containerized)
    │   ├── web_portal_ec2.py
    │   ├── web_portal.py
    │   ├── requirements.txt
    │   ├── Dockerfile
    │   └── docker-compose.yml
    ├── inventory-service/      # VPC B Flask API + SQS consumer
    │   └── inventory_service.py
    ├── lambda/                 # serverless order processor
    │   └── lambda_function.py
    └── scripts/                # IaC-adjacent helpers
        ├── simple_upload.py
        ├── sqs-access-policy.json
        ├── mount-efs.sh
        ├── format-mount-ebs.sh
        └── install-docker.sh
```

## Verification highlights

| Evidence | Screenshot |
|----------|-----------|
| Two VPCs (public 10.10/16, dark 10.20/16) | `screenshots/01-vpcs.png` |
| Dark VPC reaches SNS/SQS via PrivateLink | `screenshots/06-vpc-endpoints.png` |
| CQRS read + write validated via curl | `screenshots/07-cqrs-curl-validation.png` |
| CloudFront multi-origin behaviors | `screenshots/09-cloudfront-behaviors.png` |
| Lambda SUCCESS trace (order id matches the `202` response) | `screenshots/11-cloudwatch-lambda-logs.png` |
| Containerized web tier running | `screenshots/13-docker-compose-up.png` |

The order ID `3380c03d-ce50-40df-98f2-494d7d5cc317` appears in **both** the
checkout response and the Lambda success log — a complete end-to-end trace
through the async path.

## Notes

- Region: **us-west-2** throughout.
- Source files contain placeholders (`YOUR_ACCOUNT_ID`, `10.20.1.X`,
  `fs-YOUR_EFS_ID`) — substitute real values before running.
- The in-memory inventory store is intentional for the lab; production would
  use DynamoDB/RDS behind the Lambda.

## Tech

AWS VPC · Transit Gateway · PrivateLink · IAM · SNS · SQS · ALB · CloudFront ·
S3 · EFS · EBS · Lambda · CloudWatch · CloudTrail · Python (Flask, boto3) ·
Docker / Docker Compose
