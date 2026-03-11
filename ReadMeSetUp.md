 # Spend Trend Skill — Setup Guide

  Automates weekly cloud cost spike analysis for CloudZero customers. Runs every Monday via cron, generates markdown reports, and optionally posts to Slack and email.

  ## What it does

  - Pulls this week's spend vs. prior week from the CloudZero API
  - Detects the top 3–5 cost spikes by resource type and cloud provider
  - Saves a formatted markdown report per client
  - Generates a cross-client weekly overview
  - Posts to Slack and sends email (both optional)

  ## Prerequisites

  - Python 3.8+ (no external libraries required — stdlib only)
  - CloudZero API key(s) for each client
  - Optional: Slack webhook URL, Gmail app password

  ## Setup

  ### 1. Configure your environment

  ```bash
  cp .env.example .env

  Edit .env and fill in:
  - One API key per client (e.g. CLIENT_A_API_KEY=...)
  - Optional Slack webhook and email credentials

  2. Configure your clients

  Edit spend_trend_runner.py and update the CLIENTS list:

  CLIENTS = [
      {"folder": "client-a",  "env_key": "CLIENT_A_API_KEY",  "name": "Client A"},
      {"folder": "client-b",  "env_key": "CLIENT_B_API_KEY",  "name": "Client B"},
  ]

  - folder — subfolder name under your clients directory (lowercase, no spaces)
  - env_key — matching key name in your .env file
  - name — display name used in reports

  3. Set your paths

  At the top of spend_trend_runner.py, set:

  CLIENTS_DIR = Path("/path/to/your/clients")
  OVERVIEW_DIR = Path("/path/to/spend-trend-overview")

  Or set these as environment variables:
  CLIENTS_DIR=/path/to/your/clients
  OVERVIEW_DIR=/path/to/spend-trend-overview

  4. Run manually

  python3 spend_trend_runner.py

  5. Set up cron (optional — runs every Monday at 7am)

  crontab -e

  Add:
  0 7 * * 1 /usr/bin/python3 /path/to/spend_trend_runner.py >> /path/to/logs/spend-trend.log 2>&1

  Using with Claude Code

  1. Open Claude Code in your clients directory
  2. Invoke: cost-analyst:cost-trend-analysis
  3. Say: "run spend trend for [Client], [start date] to [end date]"
  4. Claude pulls data and returns a formatted readout

  See SKILL.md for the full Claude instruction set.

  Output

  Per-client report: clients/[client-folder]/spend-trend/YYYY-MM-DD_to_YYYY-MM-DD.md

  Weekly overview: spend-trend-overview/YYYY-MM-DD_to_YYYY-MM-DD/overview.md

  Adding a new client

  1. Add an entry to CLIENTS in the runner
  2. Add the API key to .env
  3. Create the client folder if it doesn't exist

  No other code changes needed.

  ---

  ## 6. `spend-trend-skill/SKILL.md`

  ```markdown
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
  - AWS: `EC2:`, `RDS:`, `S3:`, `EKS:`, `CloudWatch:`, `ECR:`, `ELB:`, `DynamoDB:`, `VPC:`, `EFS:`, `Kinesis:`, `GuardDuty:`, `ElastiCache:`, `NetworkFirewall:`, `MSK:`, `Route53:`, `Glue:`, `Backup:`, `Lambda:`,
   `SNS:`, `SQS:`, `awskms:`, `DirectConnect:`, `CloudHSM:`, `Athena:`, `Config:`, `SecurityHub:`
  - Azure: `microsoft.`, `azure` (case-insensitive)
  - GCP: `Compute Engine:`, `Cloud Storage:`, `Cloud SQL:`, `Cloud Run:`, `BigQuery:`, `Cloud Armor:`, `Cloud Spanner:`
  - Snowflake: `Snowflake` or `snowflake`
  - Kubernetes: `EKS:`, `K8s:`, `microsoft.containerservice:`

  ### Within each cloud provider section, show:
  1. **Service** — which services spiked (starting point)
  2. **Resource Type** — main focus; which specific resource types drove the spike
  3. **Usage Family** — include if spikes are significant (e.g. Compute Instance, Data Transfer, Virtual Machines)

  Filter out any row where the dollar increase is under $1,000.
  Show top 5 per section.

  ### Business context
  Show a section at the end: spend spikes by the client's business context dimension.
  This varies per client — check `client-info.md` in the client's folder for the correct dimension name (e.g. `User:Defined:DepartmentName`, `User:Defined:Team`, etc.).

  ### CloudZero explorer URLs
  Each spike must include a CloudZero URL.

  URL format:
  https://app.cloudzero.com/explorer?activeCostType=real_cost&granularity=daily&partitions=costcontext%3AService%20Category&dateRange=Last%2030%20Days&costcontext%3AResource%20Type={RT}&showRightFlyout=filters

  URL encoding: `:` → `%3A`, space → `%20`, `/` → `%2F`

  ### API notes
  - Endpoint: `GET /v2/billing/costs`
  - Auth: `Authorization: <api-key>` (no Bearer prefix)
  - Params: `start_date`, `end_date`, `granularity=daily`, `group_by=<dimension>`
  - Only one `group_by` at a time
  - Available dimensions: `Service`, `CZ:Defined:ResourceType`, `UsageFamily`, `CloudProvider`, `User:Defined:*`

  ## Report format

  Spend Trend — [Client]

  Week: M/D/YYYY - M/D/YYYY
  Prior week: M/D/YYYY - M/D/YYYY

  Summary

  | | This Week | Prior Week | Change |
  ...

  Spend Spikes (3-5 total)

  1. [Spike title]

  - Resource Type: EC2: instance
  - This week: $X | Prior week: $Y | Change: +Z% (+$delta)
  - Context: [brief note]
  - URL: [CloudZero explorer link]

  Generated YYYY-MM-DD

  ## Where to save the output

  - Client-specific: `clients/[client-folder]/spend-trend/YYYY-MM-DD_to_YYYY-MM-DD.md`
  - Weekly overview: `spend-trend-overview/YYYY-MM-DD_to_YYYY-MM-DD/overview.md`

  ## Weekly overview folder naming
  Always use: `YYYY-MM-DD_to_YYYY-MM-DD` (Monday to Sunday)

