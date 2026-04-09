# Claude-Powered Outbound Automation

**Automated, context-rich outreach sequence generation for SDR teams using the Claude API.**

Provide a CSV of prospects and get personalized multi-step email sequences and LinkedIn messages, ready for CRM import.

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![Claude API](https://img.shields.io/badge/Claude-API-blueviolet.svg)](https://docs.anthropic.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/premiumzucchini/claude-outbound-automation.git
cd claude-outbound-automation

# 2. Install dependencies
pip install -r requirements.txt

# 3. Add your Anthropic API key
cp .env.example .env
# Edit .env and paste your key from https://console.anthropic.com/

# 4. Run (uses included sample data)
python run_pipeline.py --limit 3
```

Check the `output/` folder for generated sequences.

---

## The Problem

SDR teams at B2B SaaS companies spend a significant portion of their day on manual message prep:
- Pulling prospect data from enrichment tools
- Cross-referencing with CRM records
- Manually writing personalized emails and LinkedIn messages
- Building segmentation filters for targeted campaigns

Quality varies across reps, messaging is inconsistent, and A/B testing at scale is difficult.

## The Solution

A Python CLI pipeline that takes prospect data (CSV), enriches it with persona-specific context, and generates personalized outreach sequences via the Claude API.

### Architecture

```
+--------------+     +------------------+     +-----------------+
|  Prospect    |     |  Context Builder  |     |  Claude API     |
|  CSV Data    |---->|                  |---->|                 |
|              |     |  - Persona match |     |  - System prompt|
|  Name, Title |     |  - Enrich score  |     |    (per persona)|
|  Company     |     |  - Required refs |     |  - User prompt  |
|  Tech Stack  |     |  - Pain points   |     |    (full context|
|  CRM History |     |  - Forbidden     |     |  - JSON output  |
+--------------+     |    phrases       |     +--------+--------+
                     +------------------+              |
                                                       v
                                              +-----------------+
                                              |  Output          |
                                              |  - sequences.json|
                                              |  - CRM import CSV|
                                              |  - Console log   |
                                              +-----------------+
```

---

## How It Works

### 1. Context Building (`context_builder.py`)

Loads prospect data from CSV and builds a structured context object per prospect:

- **Persona matching**: Maps job titles to buyer personas (VP Sales, RevOps, Marketing Leader, CRO) using pattern matching
- **Enrichment scoring**: Scores 0.0-1.0 based on data completeness — prospects with richer context are processed first and produce better output
- **Required references**: Determines what the outreach must reference (tech stack, past engagement, industry, deal stage)

### 2. Prompt Engineering (`claude_client.py`)

Each persona gets a distinct system prompt, not just a tone adjustment:

| Persona | Tone | Max Words | Approach |
|---------|------|-----------|----------|
| VP Sales | Executive | 150 | Lead with insight, not a pitch |
| RevOps | Peer | 200 | Reference their tools and workflows |
| Marketing Leader | Professional | 175 | Tie to their KPIs (CAC, attribution) |
| CRO | Executive | 120 | Full-funnel visibility, board-level framing |

Prompts include required references (must mention tech stack, past engagement) and forbidden phrases (no "hope this finds you well", no "synergy").

### 3. Sequence Generation

For each prospect, the pipeline generates:
- **3-step email sequence** (intro, follow-up, breakup), each taking a different angle
- **LinkedIn message** (condensed version of Step 1)
- **Send cadence** suggestion (e.g., Day 1, Day 3, Day 7)

### 4. Output

Results export to:
- `output/sequences.json` — Full structured data
- `output/sequences_crm_import.csv` — Flat CSV ready for Outreach, Salesloft, or HubSpot import

---

## CLI Usage

The pipeline is run entirely from the command line.

```bash
# Process all prospects in the sample CSV
python run_pipeline.py

# Process the first 3 prospects (useful for testing)
python run_pipeline.py --limit 3

# Process a single prospect by name
python run_pipeline.py --prospect "Sarah Chen"

# Skip prospects with incomplete data
python run_pipeline.py --min-score 0.7

# Generate 5-step sequences instead of the default 3
python run_pipeline.py --steps 5

# Point to your own prospect CSV
python run_pipeline.py --csv path/to/your_prospects.csv
```

### All Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--csv` | `sample_data/prospects.csv` | Path to prospect CSV |
| `--limit` | None | Max number of prospects to process |
| `--prospect` | None | Process a single prospect by exact name |
| `--min-score` | 0.0 | Skip prospects below this enrichment score (0.0-1.0) |
| `--steps` | 3 | Number of emails per sequence |
| `--delay` | 1.0 | Seconds between API calls (rate limiting) |

---

## Using Your Own Data

Create a CSV with these columns:

```
full_name,email,title,company_name,industry,employee_count,technologies,hq_location,revenue_range,last_activity_date,activity_count,activity_notes,opportunity_stage,lead_source
```

Only `full_name`, `title`, and `company_name` are required. The more columns populated, the higher the enrichment score and the more specific the generated output.

---

## Project Structure

```
claude-outbound-automation/
├── run_pipeline.py          # CLI entry point
├── context_builder.py       # Data loading, persona matching, enrichment scoring
├── claude_client.py         # Claude API integration and prompt engineering
├── config/
│   └── personas.yaml        # Buyer persona definitions and constraints
├── sample_data/
│   └── prospects.csv        # 10 synthetic prospects for testing
├── output/                  # Generated sequences (gitignored)
├── requirements.txt
├── .env.example
└── README.md
```

---

## Prompt Engineering Notes

The core insight from building this: **context beats instructions**.

A rich prospect context with a minimal system prompt produces better outreach than an elaborate system prompt with thin context.

1. **Required references force specificity.** If the prompt states "must reference their use of Salesforce and Outreach," generic output becomes impossible.

2. **Forbidden phrases prevent AI-sounding copy.** Banning "hope this finds you well" and "exciting opportunity" forces more direct openers.

3. **Persona-specific prompts are not just tone changes.** A VP Sales and a RevOps lead get fundamentally different system prompts — different length limits, different angles, different reference requirements.

4. **Iteration with the end user matters.** In production, prompts were updated weekly with the SDR team. If output didn't sound right, the prompt was adjusted, not the output.

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.9+ |
| LLM | Claude API (Anthropic) |
| Config | YAML |
| Output | JSON + CSV |

---

*Built based on real GTM automation work at a B2B SaaS company. All prospect data in this repo is synthetic.*
