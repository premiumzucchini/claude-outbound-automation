# 🤖 Claude-Powered Outbound Automation

**Automated, context-rich outreach sequence generation for SDR teams using the Claude API.**

Paste a CSV of prospects → get personalized multi-step email sequences + LinkedIn messages, ready for CRM import.

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

That's it. Check the `output/` folder for your generated sequences.

---

## The Problem

SDR teams at B2B SaaS companies spend **30-40% of their day** on manual message prep:
- Pulling prospect data from enrichment tools
- Cross-referencing with CRM records
- Manually writing personalized emails and LinkedIn messages
- Building segmentation filters for targeted campaigns

Quality varies across reps, messaging is inconsistent, and A/B testing at scale is nearly impossible.

## The Solution

A Python pipeline that takes prospect data (CSV), enriches it with persona-specific context, and generates personalized outreach sequences via the Claude API.

### Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Prospect    │     │  Context Builder  │     │  Claude API     │
│  CSV Data    │────▶│                  │────▶│                 │
│              │     │  - Persona match │     │  - System prompt│
│  Name, Title │     │  - Enrich score  │     │    (per persona)│
│  Company     │     │  - Required refs │     │  - User prompt  │
│  Tech Stack  │     │  - Pain points   │     │    (full context│
│  CRM History │     │  - Forbidden     │     │  - JSON output  │
└─────────────┘     │    phrases       │     └────────┬────────┘
                    └──────────────────┘              │
                                                      ▼
                                             ┌─────────────────┐
                                             │  Output          │
                                             │  - sequences.json│
                                             │  - CRM import CSV│
                                             │  - Console log   │
                                             └─────────────────┘
```

## Key Results (from production use)

| Metric | Before | After |
|--------|--------|-------|
| Message prep time per rep | ~2.5 hrs/day | ~1.5 hrs/day |
| Outreach consistency | Variable by rep | Standardized |
| A/B test velocity | 1-2 variants/week | 5-10 variants/week |
| Team size supported | 6-8 SDRs | 6-8 SDRs |

---

## How It Works

### 1. Context Building (`context_builder.py`)

The most important module. Loads prospect data from CSV and builds a rich context object per prospect:

- **Persona matching**: Maps job titles to buyer personas (VP Sales, RevOps, Marketing Leader, CRO) using pattern matching
- **Enrichment scoring**: Scores 0.0–1.0 based on data completeness — prospects with richer context produce better output
- **Required references**: Auto-determines what the outreach MUST reference (tech stack, past engagement, industry)

```
$ python run_pipeline.py --limit 3

08:15:01 | INFO    | BUILDING PROSPECT CONTEXTS
08:15:01 | INFO    |   David Okafor              | persona=cro                  | score=1.00
08:15:01 | INFO    |   Kevin Wu                  | persona=revops               | score=0.95
08:15:01 | INFO    |   Raj Patel                 | persona=cro                  | score=0.95
```

### 2. Prompt Engineering (`claude_client.py`)

Each persona gets a fundamentally different system prompt — not just a tone adjustment:

| Persona | Tone | Max Words | Approach |
|---------|------|-----------|----------|
| VP Sales | Executive | 150 | Lead with insight, not a pitch |
| RevOps | Peer | 200 | Reference their tools and workflows |
| Marketing Leader | Professional | 175 | Tie to their KPIs (CAC, attribution) |
| CRO | Executive | 120 | Full-funnel visibility, board-level |

Prompts include **required references** (must mention their tech stack, past engagement) and **forbidden phrases** (no "hope this finds you well", no "synergy").

### 3. Sequence Generation

For each prospect, Claude generates:
- **3-step email sequence** (intro → follow-up → breakup), each with a different angle
- **LinkedIn message** (condensed version of Step 1)
- **Send cadence** suggestion (e.g., Day 1, Day 3, Day 7)

### 4. Output

Results export to:
- `output/sequences.json` — Full structured data
- `output/sequences_crm_import.csv` — Flat CSV ready for Outreach/Salesloft/HubSpot import

---

## Usage

```bash
# Process all 10 sample prospects
python run_pipeline.py

# Process just 3 (faster, cheaper for testing)
python run_pipeline.py --limit 3

# Process a single prospect
python run_pipeline.py --prospect "Sarah Chen"

# Only process prospects with rich context
python run_pipeline.py --min-score 0.7

# Generate 5-step sequences instead of 3
python run_pipeline.py --steps 5

# Use your own prospect data
python run_pipeline.py --csv my_prospects.csv
```

### Using Your Own Data

Create a CSV with these columns:

```
full_name,email,title,company_name,industry,employee_count,technologies,hq_location,revenue_range,last_activity_date,activity_count,activity_notes,opportunity_stage,lead_source
```

Only `full_name`, `title`, and `company_name` are required. The more columns you fill, the higher the enrichment score and the better the generated output.

---

## Project Structure

```
claude-outbound-automation/
├── run_pipeline.py          # Entry point — run this
├── context_builder.py       # Data loading, persona matching, enrichment scoring
├── claude_client.py         # Claude API integration + prompt engineering
├── config/
│   └── personas.yaml        # Buyer persona definitions + constraints
├── sample_data/
│   └── prospects.csv        # 10 synthetic prospects (ready to use)
├── output/                  # Generated sequences land here
├── requirements.txt
├── .env.example
└── README.md
```

## Prompt Engineering Philosophy

The most important insight from building this: **context beats instructions**.

A rich prospect context with minimal system instructions produces better outreach than an elaborate system prompt with thin context. Specifically:

1. **Required references force specificity.** If the prompt says "MUST reference their use of Salesforce and Outreach," Claude can't write a generic email.

2. **Forbidden phrases prevent AI-sounding copy.** Banning "hope this finds you well" and "exciting opportunity" forces Claude to find better openers.

3. **Persona-specific prompts aren't just tone changes.** A VP Sales gets a completely different system prompt than a RevOps lead — different length, different angles, different references.

4. **The rep feedback loop matters.** In production, prompts were iterated weekly with the SDR team. If a message didn't sound right, the prompt got adjusted, not the output.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.9+ |
| LLM | Claude API (Anthropic) |
| Config | YAML (personas, constraints) |
| Output | JSON + CSV |

---

*Built based on real GTM automation work at a B2B SaaS company. All prospect data in this repo is synthetic — no real company or person data is included.*
