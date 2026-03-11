 # How to Build a Claude Code Skill

  A Claude Code skill is a combination of:
  1. A `SKILL.md` file — instructions Claude reads to know what to do
  2. Optionally, a Python runner script — automation that does the actual work
  3. A `.env.example` — API keys and config the skill needs

  ## The pattern

  my-skill/
  ├── SKILL.md                 ← Claude's instructions (required)
  ├── my_skill_runner.py       ← automation script (optional)
  ├── .env.example             ← env var template (if API keys needed)
  └── README.md                ← setup guide for humans

  ## Step 1: Write your SKILL.md

  This is what Claude Code reads when you invoke the skill. It should answer:
  - What does this skill do?
  - What data does it need? (API, files, user input)
  - How should Claude analyze or transform that data?
  - What format should the output take?
  - Where should output be saved?

  See `SKILL.md` in this folder for a blank template.

  ## Step 2: Decide if you need a runner script

  A runner script makes sense when:
  - You need to pull data from an API
  - You want automation (cron, batch processing)
  - The computation is too complex or slow for Claude to do inline

  If you're just having Claude read files, write summaries, or do analysis on data you provide directly, you may not need a runner at all.

  ## Step 3: Configure credentials

  If your skill calls external APIs:
  1. Copy `.env.example` to `.env`
  2. Fill in the values
  3. Make sure `.env` is in `.gitignore`

  ## Step 4: Invoke the skill in Claude Code

  Open Claude Code in your working directory and say:
  [skill-name]
  or
  run [skill-name] for [client/subject] for [date range / parameters]

  ## Tips from building the spend-trend-skill

  - **Name your env keys consistently** — `CLIENT_NAME_API_KEY` so it's obvious what each key is for
  - **Keep paths configurable** — use env vars or derive from `Path.home()` instead of hardcoding
  - **Add a `--dry-run` flag** — saves time during development by printing to stdout without writing files or posting to Slack
  - **Per-client config** — if behavior varies by client, use a `client-config.json` in each client's folder rather than branching in code
  - **One `group_by` at a time** — many APIs only support one grouping dimension per call; do multiple calls and merge in Python
  - **Establish folder naming conventions before scaffolding** — lowercase, no spaces; fixing this later is painful

