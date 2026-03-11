Automates weekly enterprise clientele account spend analysis. Replicates my decision-tree for identifying the 3 most meaningful client cost spikes. Insights dont duplicate ML bot spike/anomalies and have client business context Generates a curated digest and reduces manual analysis 
 while improving team cost insight.

# Claude Code Skill Share

  A collection of reusable Claude Code skills and automation scripts for cloud cost management and customer success workflows.

  ## What's in here

  Each skill is a self-contained folder with:
  - `SKILL.md` — Instructions Claude Code reads to execute the skill
  - A Python runner script — Automation that does the actual work
  - `.env.example` — API keys and config you need to set up
  - `README.md` — Setup guide

  ## Skills

  | Skill | What it does |
  |-------|-------------|
  | [spend-trend-skill](./spend-trend-skill/) | Weekly cloud cost spike analysis across clients — runs via cron, outputs to files, Slack, and email |

  ## How to use a skill

  1. Clone this repo
  2. Copy `.env.example` to `.env` and fill in your API keys
  3. Open Claude Code in your working directory
  4. Invoke the skill by name (e.g. `cost-analyst:cost-trend-analysis`)
  5. Tell Claude what you want: client, date range, etc.

  ## How to build a new skill

  See [skill-template](./skill-template/) for a blank starter with instructions.

  ## Structure

  github-skill-share/
  ├── README.md                    ← you are here
  ├── skill-template/              ← blank template for building new skills
  │   ├── README.md
  │   └── SKILL.md
  └── spend-trend-skill/           ← weekly cost spike analysis
      ├── README.md
      ├── SKILL.md
      ├── spend_trend_runner.py
      ├── .env.example
    
