# Spend Trend Skill

Use this skill to run a weekly spend trend analysis for a client and generate the readout.

## What it does
- Pulls cost data from CloudZero for the current week (Mon–Sun) vs prior week (Mon–Sun)
- Identifies spend spikes (increases only) by cloud provider, resource type, and usage family
- Produces a formatted report saved to the client's spend-trend folder and the weekly overview

## API Keys
Store in a `.env` file in your working directory.
Each client has its own key (e.g. `CLIENT_A_API_KEY`, `CLIENT_B_API_KEY`).

## How to run it

1. Open Claude Code in your clients directory
2. Invoke the skill: `cost-analyst:cost-trend-analysis`
3. Tell Claude which client and which date range (Mon to Sun, e.g. "run spend trend for Client A, 3/8/2026 to 3/14/2026")
4. Claude will pull the data and return a readout

## Analysis approach

### Only show spend spikes (increases)
Do not include decreases. Focus on what went up and why.

### Limit to 3-5 spikes total across the entire report
Pick the most significant spikes — not 3-5 per section. Prioritize:
1. NEW costs (prior week = $0, this week > $0) — always include these if significant
2. Largest dollar increase
3. Largest percentage increase on meaningful spend
Remove any section that has no spikes. Do not pad with minor movements.

### Structure the report by cloud provider
Check which cloud providers the client has spend in. Common ones:
- AWS
- Azure
- GCP
- Snowflake (if present)
- Kubernetes (EKS, AKS, GKE — check resource type data for `EKS:`, `microsoft.containerservice:`, `K8s:`)

Run a separate section for each provider the client actually has.

### Identify provider from resource type names
The CloudZero API returns one `group_by` at a time. Split results by provider using name patterns:
- AWS: `EC2:`, `RDS:`, `S3:`, `EKS:`, `CloudWatch:`, `ECR:`, `ELB:`, `DynamoDB:`, `VPC:`, `EFS:`, `Kinesis:`, `GuardDuty:`, `ElastiCache:`, `NetworkFirewall:`, `MSK:`, `Route53:`, `Glue:`, `Backup:`, `Lambda:`, `SNS:`, `SQS:`, `awskms:`, `DirectConnect:`, `CloudHSM:`, `Athena:`, `Config:`, `SecurityHub:`
- Azure: `microsoft.`, `azure` (case-insensitive)
- GCP: `Compute Engine:`, `Cloud Storage:`, `Cloud SQL:`, `Cloud Run:`, `BigQuery:`, `Cloud Armor:`, `Cloud Spanner:`
- Snowflake: `Snowflake` or `snowflake`
- Kubernetes: `EKS:`, `K8s:`, `microsoft.containerservice:`

### Within each cloud provider section, show:
1. **Service** — which services spiked (starting point)
2. **Resource Type** — main focus; which specific resource types drove the spike
3. **Usage Family** — include if spikes are significant (e.g. Compute Instance, Data Transfer, Virtual Machines); helps explain the nature of spend

Filter out any row where the dollar increase is under $1,000.
Show top 5 per section.

### Business context
Show a section at the end: spend spikes by the client's business context dimension.
This varies per client — check `client-info.md` in the client's folder for the correct dimension name (e.g. `User:Defined:DepartmentName`, `User:Defined:Team`, etc.).

### CloudZero explorer URLs
Each spike in the report must include a CloudZero URL so the client can click directly into the view.

URL format:
```
https://app.cloudzero.com/explorer?activeCostType=real_cost&granularity=daily&partitions=costcontext%3AService%20Category&dateRange=Last%2030%20Days&costcontext%3AResource%20Type={RT}&showRightFlyout=filters
```

- `{RT}` = URL-encoded resource type value (e.g. `EC2%3A%20instance` for `EC2: instance`)
- Omit resource type filter if the spike is at the business context level only

URL encoding rules for common characters:
- `:` → `%3A`
- ` ` (space) → `%20`
- `/` → `%2F`

### API notes
- Endpoint: `GET /v2/billing/costs`
- Auth: `Authorization: <api-key>` (no Bearer prefix)
- Params: `start_date`, `end_date`, `granularity=daily`, `group_by=<dimension>`
- Only one `group_by` at a time — provider filtering is done by name pattern
- Available dimensions: `Service`, `CZ:Defined:ResourceType`, `UsageFamily`, `CloudProvider`, `User:Defined:*`

## Report format

```
# Spend Trend — [Client]
**Week:** M/D/YYYY - M/D/YYYY
**Prior week:** M/D/YYYY - M/D/YYYY

## Summary
| | This Week | Prior Week | Change |
...

## Spend Spikes (3-5 total)

### 1. [Spike title — e.g. "EC2: instance"]
- **Resource Type:** EC2: instance
- **This week:** $X | **Prior week:** $Y | **Change:** +Z% (+$delta)
- **Context:** [brief note]
- **URL:** [CloudZero explorer link]

### 2. ...

*Generated YYYY-MM-DD*
```

## Where to save the output

- Client-specific: `clients/[client-folder]/spend-trend/YYYY-MM-DD_to_YYYY-MM-DD.md`
- Weekly overview: `spend-trend-overview/YYYY-MM-DD_to_YYYY-MM-DD/overview.md`

## Weekly overview folder naming
Always use: `YYYY-MM-DD_to_YYYY-MM-DD` (Monday to Sunday)
Example: `2026-03-02_to_2026-03-08`
