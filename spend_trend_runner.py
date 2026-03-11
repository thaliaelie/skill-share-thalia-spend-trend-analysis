#!/usr/bin/env python3
"""
Weekly Spend Trend Runner
Runs every Monday morning via cron.

For each client:
  - Pulls last week's total spend from CloudZero
  - Compares to the prior week
  - Identifies top spend spikes by resource type
  - Saves a full report to: clients/[client]/spend-trend/[week].md
  - Saves a combined overview to: clients/spend-trend-overview/[week]/overview.md
  - Posts to Slack (if SLACK_WEBHOOK_URL is set in .env)
  - Sends an email summary (if GMAIL_APP_PASSWORD and EMAIL_RECIPIENT are set in .env)
"""

import json
import smtplib
import sys
import urllib.request
import urllib.parse
import urllib.error
from collections import defaultdict
from datetime import date, timedelta
from email.mime.text import MIMEText
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

CLIENTS_DIR = Path("/Users/thaliaelie/clients")
ENV_FILE = CLIENTS_DIR / "fam-foundational-files" / ".env"
OVERVIEW_DIR = CLIENTS_DIR / "spend-trend-overview"
CLOUDZERO_BASE = "https://api.cloudzero.com"

# ── Clients ───────────────────────────────────────────────────────────────────

CLIENTS = [
    {"folder": "teradata",  "env_key": "TERADATA_API_KEY",  "name": "Teradata"},
    {"folder": "cloudera",  "env_key": "CLOUDERA_API_KEY",  "name": "Cloudera"},
    {"folder": "ncr-voyix", "env_key": "NCRV_API_KEY",      "name": "NCR Voyix"},
    {"folder": "nextgen",   "env_key": "NEXTGEN_API_KEY",   "name": "NextGen"},
    {"folder": "premier",   "env_key": "PREMIER_API_KEY",   "name": "Premier"},
    {"folder": "sandboxaq", "env_key": "SANDBOXAQ_API_KEY", "name": "SandboxAQ"},
    {"folder": "signifyd",  "env_key": "SIGNIFYD_API_KEY",  "name": "Signifyd"},
]

# ── Env reader ────────────────────────────────────────────────────────────────

def read_env(path: Path) -> dict:
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            env[key.strip()] = val.strip()
    return env

# ── Date helpers ──────────────────────────────────────────────────────────────

def get_week_ranges():
    """
    Returns (last_start, last_end, prior_start, prior_end).
    last week  = the Mon-Sun that just completed
    prior week = the Mon-Sun before that
    """
    today = date.today()
    last_monday = today - timedelta(days=today.weekday() + 7)
    last_sunday = last_monday + timedelta(days=6)
    prior_monday = last_monday - timedelta(days=7)
    prior_sunday = last_monday - timedelta(days=1)
    return last_monday, last_sunday, prior_monday, prior_sunday

def folder_label(start: date, end: date) -> str:
    return f"{start.strftime('%Y-%m-%d')}_to_{end.strftime('%Y-%m-%d')}"

def display_label(start: date, end: date) -> str:
    return f"{start.strftime('%-m/%-d/%Y')} - {end.strftime('%-m/%-d/%Y')}"

# ── CloudZero API ─────────────────────────────────────────────────────────────

def fetch_costs(api_key: str, start: date, end: date, group_by: str = None, limit: int = 1000) -> list:
    """
    Fetch cost records for a date range, handling pagination.
    Returns a flat list of cost records.
    """
    all_costs = []
    cursor = None
    total_expected = None

    for _ in range(20):  # max pages safety
        params = {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "granularity": "daily",
            "limit": limit,
        }
        if group_by:
            params["group_by"] = group_by
        if cursor:
            params["next_cursor"] = cursor

        url = f"{CLOUDZERO_BASE}/v2/billing/costs?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url)
        req.add_header("Authorization", api_key)

        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())

        batch = data.get("costs", [])
        all_costs.extend(batch)

        pagination = data.get("pagination", {})
        cursor_obj = pagination.get("cursor", {})

        if total_expected is None:
            total_expected = pagination.get("total_count", 0)

        has_next = cursor_obj.get("has_next", False)
        next_cursor = cursor_obj.get("next_cursor")

        if len(all_costs) >= total_expected or not has_next or not next_cursor:
            break
        cursor = next_cursor

    if total_expected:
        return all_costs[:total_expected]
    return all_costs

def sum_by_dim(costs: list, dim_key: str) -> dict:
    """Sum costs by a dimension key. Returns {value: total_cost}."""
    totals = {}
    for row in costs:
        key = row.get(dim_key, "Unknown")
        totals[key] = totals.get(key, 0.0) + float(row.get("cost", 0))
    return totals

# ── Provider identification ───────────────────────────────────────────────────

def identify_provider(rt: str) -> str:
    """Identify cloud provider from resource type name."""
    rt_lower = rt.lower()
    if any(x in rt_lower for x in ["microsoft.", "azure."]):
        return "Azure"
    if any(x in rt_lower for x in [
        "app engine", "artifact registry", "bigquery", "cloud armor", "cloud build",
        "cloud cdn", "cloud dataflow", "cloud dns", "cloud filestore", "cloud functions",
        "cloud interconnect", "cloud load balancing", "cloud logging", "cloud memorystore",
        "cloud monitoring", "cloud nat", "cloud pub/sub", "cloud router", "cloud run",
        "cloud scheduler", "cloud spanner", "cloud sql", "cloud storage", "cloud tasks",
        "cloud trace", "compute engine", "gke", "kubernetes engine", "vertex", "dataflow",
        "dataproc", "composer", "looker", "bigtable", "firestore", "alloydb",
    ]):
        return "GCP"
    if "snowflake" in rt_lower:
        return "Snowflake"
    if "datadog" in rt_lower:
        return "Datadog"
    if "databricks" in rt_lower or "premium_" in rt_lower or "standard_" in rt_lower:
        return "Databricks"
    return "AWS"

# ── Spike detection ───────────────────────────────────────────────────────────

def find_spikes(this_week: dict, prior_week: dict, min_dollar: float = 500, top_n: int = 5) -> list:
    """
    Find top cost spikes (increases only), sorted by dollar increase.
    Returns list of spike dicts.
    """
    spikes = []
    for rt, this in this_week.items():
        prior = prior_week.get(rt, 0.0)
        diff = this - prior
        if diff < min_dollar:
            continue
        pct = (diff / prior * 100) if prior > 0 else None
        spikes.append({
            "rt": rt,
            "this": this,
            "prior": prior,
            "diff": diff,
            "pct": pct,
            "provider": identify_provider(rt),
            "is_new": prior == 0,
        })
    spikes.sort(key=lambda x: x["diff"], reverse=True)
    return spikes[:top_n]

# ── URL builder ───────────────────────────────────────────────────────────────

def explorer_url(rt: str) -> str:
    rt_encoded = urllib.parse.quote(rt)
    return (
        "https://app.cloudzero.com/explorer"
        "?activeCostType=real_cost"
        "&granularity=daily"
        "&partitions=costcontext%3AService%20Category"
        "&dateRange=Last%2030%20Days"
        f"&costcontext%3AResource%20Type={rt_encoded}"
        "&showRightFlyout=filters"
    )

# ── Trend helpers ─────────────────────────────────────────────────────────────

def trend_line(this_cost: float, prior_cost: float) -> str:
    if prior_cost <= 0:
        return "no prior week data"
    change = ((this_cost - prior_cost) / prior_cost) * 100
    direction = "up" if change >= 0 else "down"
    return f"{direction} {abs(change):.1f}%"

def trend_symbol(this_cost: float, prior_cost: float) -> str:
    if prior_cost <= 0:
        return "—"
    change = ((this_cost - prior_cost) / prior_cost) * 100
    arrow = "up" if change >= 0 else "down"
    return f"{arrow} {abs(change):.1f}%"

# ── Report builders ───────────────────────────────────────────────────────────

def build_client_report(
    name: str,
    week_display: str,
    prior_display: str,
    this_total: float,
    prior_total: float,
    provider_this: dict,
    provider_prior: dict,
    spikes: list,
    generated_date: str,
) -> str:
    lines = []

    lines += [
        f"# Spend Trend - {name}",
        f"**Week:** {week_display}",
        f"**Prior week:** {prior_display}",
        f"",
        f"---",
        f"",
        f"## Summary",
        f"",
        f"| | This Week | Prior Week | Change |",
        f"|---|---|---|---|",
        f"| Total | ${this_total:,.0f} | ${prior_total:,.0f} | {trend_line(this_total, prior_total)} |",
    ]

    # Provider rows — only show providers with meaningful spend
    for provider in ["AWS", "Azure", "GCP", "Snowflake", "Databricks", "Datadog", "Oracle Cloud"]:
        t = provider_this.get(provider, 0)
        p = provider_prior.get(provider, 0)
        if t > 100 or p > 100:
            lines.append(f"| {provider} | ${t:,.0f} | ${p:,.0f} | {trend_line(t, p)} |")

    lines += ["", "---", "", "## Spend Spikes", ""]

    if not spikes:
        lines.append("No significant spikes this week.")
    else:
        for i, s in enumerate(spikes, 1):
            rt = s["rt"]
            if s["is_new"]:
                change_str = f"NEW (+${s['diff']:,.0f})"
            else:
                change_str = f"+{s['pct']:.1f}% (+${s['diff']:,.0f})"

            lines += [
                f"### {i}. {rt} ({s['provider']})",
                f"- **This week:** ${s['this']:,.0f} | **Prior week:** ${s['prior']:,.0f} | **Change:** {change_str}",
                f"- **URL:** {explorer_url(rt)}",
                f"",
                f"---",
                f"",
            ]

    lines.append(f"*Generated {generated_date}*")
    return "\n".join(lines)


def build_overview(
    week_display: str,
    client_results: list,
    generated_date: str,
) -> str:
    lines = [
        f"# Weekly Spend Trend Overview",
        f"**Week:** {week_display}",
        f"",
        f"---",
        f"",
        f"## Totals",
        f"",
        f"| Client | This Week | Prior Week | Change |",
        f"|--------|-----------|------------|--------|",
    ]

    for r in client_results:
        change = trend_symbol(r["this_total"], r["prior_total"])
        bold = "**" if r["this_total"] > r["prior_total"] else ""
        lines.append(
            f"| {r['name']} | {bold}${r['this_total']:,.0f}{bold} | ${r['prior_total']:,.0f} | {bold}{change}{bold} |"
        )

    # Summary sentence
    increasing = [r["name"] for r in client_results if r["this_total"] > r["prior_total"]]
    if increasing:
        lines += ["", f"{len(client_results) - len(increasing)} of {len(client_results)} clients decreased. "
                  f"Increasing: {', '.join(increasing)}."]
    else:
        lines += ["", f"All {len(client_results)} clients decreased this week."]

    lines += ["", "---", "", "## Top Spikes by Client", ""]

    for r in client_results:
        change = trend_line(r["this_total"], r["prior_total"])
        lines.append(f"**{r['name']}** — {change} overall")
        if r["spikes"]:
            for s in r["spikes"][:3]:
                if s["is_new"]:
                    detail = f"NEW (+${s['diff']:,.0f})"
                else:
                    detail = f"+{s['pct']:.1f}% (+${s['diff']:,.0f})"
                lines.append(f"- {s['rt']}: {detail}")
        else:
            lines.append("- No significant spikes")
        lines.append("")

    lines += ["---", "", f"*Generated {generated_date}*"]
    return "\n".join(lines)


def build_slack_message(week_display: str, client_results: list) -> str:
    lines = [f"*Weekly Spend Trend — {week_display}*", ""]

    for r in client_results:
        change = trend_line(r["this_total"], r["prior_total"])
        arrow = ":arrow_up:" if r["this_total"] > r["prior_total"] else ":arrow_down:"
        lines.append(f"{arrow} *{r['name']}* — ${r['this_total']:,.0f} ({change})")
        for s in r["spikes"][:2]:
            if s["is_new"]:
                detail = f"NEW (+${s['diff']:,.0f})"
            else:
                detail = f"+{s['pct']:.1f}% (+${s['diff']:,.0f})"
            lines.append(f"   • {s['rt']}: {detail}")

    return "\n".join(lines)

# ── Slack ─────────────────────────────────────────────────────────────────────

def send_slack(webhook_url: str, text: str):
    body = json.dumps({"text": text}).encode()
    req = urllib.request.Request(webhook_url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            pass
        print("[OK] Slack message sent")
    except Exception as e:
        print(f"[WARN] Slack failed: {e}")

# ── Email ─────────────────────────────────────────────────────────────────────

def send_email(gmail_user: str, app_password: str, recipient: str, subject: str, body: str):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = recipient
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(gmail_user, app_password)
            server.sendmail(gmail_user, recipient, msg.as_string())
        print(f"[OK] Email sent to {recipient}")
    except Exception as e:
        print(f"[WARN] Email failed: {e}")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    env = read_env(ENV_FILE)
    last_start, last_end, prior_start, prior_end = get_week_ranges()

    week_folder = folder_label(last_start, last_end)
    week_display = display_label(last_start, last_end)
    prior_display = display_label(prior_start, prior_end)
    generated_date = date.today().strftime("%Y-%m-%d")

    overview_dir = OVERVIEW_DIR / week_folder
    overview_dir.mkdir(parents=True, exist_ok=True)

    client_results = []
    errors = []

    for client in CLIENTS:
        name = client["name"]
        api_key = env.get(client["env_key"], "")

        if not api_key or api_key.startswith("paste_your"):
            print(f"[SKIP] {name} — no API key set")
            continue

        try:
            print(f"[...] {name}")

            # Total spend (no group_by — source of truth for totals)
            this_records  = fetch_costs(api_key, last_start, last_end)
            prior_records = fetch_costs(api_key, prior_start, prior_end)
            this_total  = sum(float(r.get("cost", 0)) for r in this_records)
            prior_total = sum(float(r.get("cost", 0)) for r in prior_records)

            # Provider breakdown
            this_by_provider  = sum_by_dim(
                fetch_costs(api_key, last_start, last_end, group_by="CloudProvider"),
                "CloudProvider"
            )
            prior_by_provider = sum_by_dim(
                fetch_costs(api_key, prior_start, prior_end, group_by="CloudProvider"),
                "CloudProvider"
            )

            # Resource type breakdown for spike detection
            this_by_rt  = sum_by_dim(
                fetch_costs(api_key, last_start, last_end, group_by="CZ:Defined:ResourceType"),
                "CZ:Defined:ResourceType"
            )
            prior_by_rt = sum_by_dim(
                fetch_costs(api_key, prior_start, prior_end, group_by="CZ:Defined:ResourceType"),
                "CZ:Defined:ResourceType"
            )

            spikes = find_spikes(this_by_rt, prior_by_rt, min_dollar=500, top_n=5)

            # Save client report
            client_dir = CLIENTS_DIR / client["folder"] / "spend-trend"
            client_dir.mkdir(parents=True, exist_ok=True)
            report = build_client_report(
                name, week_display, prior_display,
                this_total, prior_total,
                this_by_provider, prior_by_provider,
                spikes, generated_date,
            )
            (client_dir / f"{week_folder}.md").write_text(report)

            change = trend_symbol(this_total, prior_total)
            print(f"[OK]  {name}: ${this_total:,.0f}  {change}  ({len(spikes)} spikes)")

            client_results.append({
                "name": name,
                "this_total": this_total,
                "prior_total": prior_total,
                "spikes": spikes,
            })

        except Exception as e:
            msg = f"[ERROR] {name}: {e}"
            print(msg, file=sys.stderr)
            errors.append(name)
            client_results.append({
                "name": name,
                "this_total": 0,
                "prior_total": 0,
                "spikes": [],
                "error": True,
            })

    # Build and save overview
    overview_text = build_overview(week_display, client_results, generated_date)
    overview_file = overview_dir / "overview.md"
    overview_file.write_text(overview_text)
    print(f"\n[OK] Overview saved: {overview_file}")

    # Slack
    slack_webhook = env.get("SLACK_WEBHOOK_URL", "")
    if slack_webhook and slack_webhook.startswith("https://"):
        slack_text = build_slack_message(week_display, client_results)
        send_slack(slack_webhook, slack_text)

    # Email
    gmail_user   = env.get("GMAIL_USER", "")
    app_password = env.get("GMAIL_APP_PASSWORD", "")
    recipient    = env.get("EMAIL_RECIPIENT", "")
    if gmail_user and app_password and not app_password.startswith("paste_your") and recipient:
        subject = f"Weekly Spend Trend Overview — {week_display}"
        send_email(gmail_user, app_password, recipient, subject, overview_text)

    if errors:
        print(f"\nErrors on: {', '.join(errors)}")
        sys.exit(1)


if __name__ == "__main__":
    main()

