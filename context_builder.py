"""
context_builder.py
------------------
Loads prospect CSV data and builds structured context objects
for each prospect. The context object is what gets injected into
the Claude prompt — its richness determines output quality.

This is the most important module in the pipeline. Better context
= better outreach. Period.
"""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


def load_personas(config_path: str = "config/personas.yaml") -> dict:
    """Load persona definitions from YAML config."""
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    return config.get("personas", {})


def load_prospects(csv_path: str) -> list[dict]:
    """
    Load prospect records from CSV.
    
    Each row becomes a dict. Technologies are parsed from
    comma-separated string into a list.
    """
    prospects = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Parse technologies from comma-separated string
            tech_raw = row.get("technologies", "")
            tech_list = [t.strip() for t in tech_raw.split(",") if t.strip()]

            # Parse activity notes
            notes_raw = row.get("activity_notes", "")
            notes_list = [n.strip() for n in notes_raw.split(";") if n.strip()]

            prospect = {
                "full_name": row.get("full_name", "").strip(),
                "email": row.get("email", "").strip(),
                "title": row.get("title", "").strip(),
                "company_name": row.get("company_name", "").strip(),
                "industry": row.get("industry", "").strip(),
                "employee_count": int(row.get("employee_count", 0) or 0),
                "technologies": tech_list,
                "hq_location": row.get("hq_location", "").strip(),
                "revenue_range": row.get("revenue_range", "").strip(),
                "last_activity_date": row.get("last_activity_date", "").strip() or None,
                "activity_count": int(row.get("activity_count", 0) or 0),
                "activity_notes": notes_list,
                "opportunity_stage": row.get("opportunity_stage", "").strip() or None,
                "lead_source": row.get("lead_source", "").strip(),
            }
            prospects.append(prospect)

    logger.info(f"Loaded {len(prospects)} prospects from {csv_path}")
    return prospects


def match_persona(title: str, personas: dict) -> tuple[str, dict]:
    """
    Match a prospect's title to the best buyer persona.
    
    Returns (persona_key, persona_config).
    Falls back to 'default' if no pattern matches.
    """
    title_lower = title.lower()
    for persona_key, config in personas.items():
        if persona_key == "default":
            continue
        patterns = config.get("title_patterns", [])
        for pattern in patterns:
            if pattern.lower() in title_lower:
                return persona_key, config
    return "default", personas.get("default", {})


def score_completeness(prospect: dict) -> float:
    """
    Score 0.0–1.0 based on how much context we have.
    
    Higher scores = richer prompts = better generated outreach.
    The weights reflect what actually matters for personalization:
    - Tech stack and CRM history matter most
    - Name and company are table stakes
    """
    weights = {
        "has_name": 0.05,
        "has_title": 0.10,
        "has_company": 0.05,
        "has_industry": 0.10,
        "has_tech_stack": 0.15,
        "has_crm_history": 0.20,
        "has_recent_notes": 0.15,
        "has_employee_count": 0.05,
        "has_deal_stage": 0.10,
        "has_location": 0.05,
    }

    score = 0.0
    if prospect.get("full_name"):
        score += weights["has_name"]
    if prospect.get("title"):
        score += weights["has_title"]
    if prospect.get("company_name"):
        score += weights["has_company"]
    if prospect.get("industry"):
        score += weights["has_industry"]
    if prospect.get("technologies"):
        score += weights["has_tech_stack"]
    if prospect.get("activity_count", 0) > 0:
        score += weights["has_crm_history"]
    if prospect.get("activity_notes"):
        score += weights["has_recent_notes"]
    if prospect.get("employee_count", 0) > 0:
        score += weights["has_employee_count"]
    if prospect.get("opportunity_stage"):
        score += weights["has_deal_stage"]
    if prospect.get("hq_location"):
        score += weights["has_location"]

    return round(score, 2)


def days_since_contact(prospect: dict) -> Optional[int]:
    """Calculate days since last CRM activity."""
    last = prospect.get("last_activity_date")
    if last:
        try:
            last_dt = datetime.strptime(last, "%Y-%m-%d")
            return (datetime.now() - last_dt).days
        except ValueError:
            return None
    return None


def build_required_references(prospect: dict) -> list[str]:
    """
    Determine what the outreach MUST reference based on available data.
    
    This is what makes the output specific instead of generic.
    If we know their tech stack, reference it. If they attended
    a webinar, mention it. If they churned, acknowledge it.
    """
    refs = []

    tech = prospect.get("technologies", [])
    if tech:
        refs.append(f"their use of {', '.join(tech[:3])}")

    notes = prospect.get("activity_notes", [])
    if notes:
        refs.append(f"previous engagement: {notes[0]}")

    industry = prospect.get("industry")
    if industry:
        refs.append(f"{industry}-specific challenge")

    stage = prospect.get("opportunity_stage")
    if stage:
        refs.append(f"current deal stage: {stage}")

    return refs


def build_context(prospect: dict, persona_key: str, persona_config: dict) -> dict:
    """
    Build the full context object that gets injected into the Claude prompt.
    
    This is the critical function. Everything downstream depends on the
    richness and structure of this context object.
    """
    context = {
        "prospect": {
            "name": prospect["full_name"],
            "title": prospect["title"],
            "company": prospect["company_name"],
            "industry": prospect["industry"],
            "employee_count": prospect["employee_count"],
            "technologies": prospect["technologies"],
            "location": prospect["hq_location"],
            "revenue_range": prospect["revenue_range"],
        },
        "crm_history": {
            "last_touch": prospect["last_activity_date"],
            "touch_count": prospect["activity_count"],
            "deal_stage": prospect["opportunity_stage"],
            "notes": prospect["activity_notes"],
            "days_since_contact": days_since_contact(prospect),
            "lead_source": prospect["lead_source"],
        },
        "persona": {
            "key": persona_key,
            "pain_points": persona_config.get("pain_points", []),
            "tone": persona_config.get("tone", "professional"),
            "max_length": persona_config.get("max_length", 200),
            "forbidden_phrases": persona_config.get("forbidden_phrases", []),
            "required_references": build_required_references(prospect),
        },
        "enrichment_score": score_completeness(prospect),
    }

    return context


def build_all_contexts(csv_path: str, config_path: str = "config/personas.yaml") -> list[dict]:
    """
    Load prospects + personas, build contexts for all prospects,
    sorted by enrichment score (richest context first).
    """
    personas = load_personas(config_path)
    prospects = load_prospects(csv_path)

    contexts = []
    for prospect in prospects:
        persona_key, persona_config = match_persona(prospect["title"], personas)
        context = build_context(prospect, persona_key, persona_config)
        contexts.append(context)

        logger.info(
            f"  {prospect['full_name']:25s} | persona={persona_key:20s} | "
            f"score={context['enrichment_score']:.2f}"
        )

    # Sort by enrichment score — richest context first
    contexts.sort(key=lambda c: c["enrichment_score"], reverse=True)

    avg_score = sum(c["enrichment_score"] for c in contexts) / len(contexts) if contexts else 0
    logger.info(f"Built {len(contexts)} contexts | avg enrichment score: {avg_score:.2f}")

    return contexts
