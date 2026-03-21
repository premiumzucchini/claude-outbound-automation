"""
run_pipeline.py
---------------
Main entry point. Runs the full outreach generation pipeline:

1. Loads prospect data from CSV
2. Builds enriched context per prospect
3. Generates personalized sequences via Claude API
4. Exports results to JSON + CSV

Usage:
    python run_pipeline.py                          # All prospects
    python run_pipeline.py --limit 3                # First 3 only
    python run_pipeline.py --prospect "Sarah Chen"  # Single prospect
    python run_pipeline.py --min-score 0.7          # Only high-context prospects
"""

import argparse
import csv
import json
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from context_builder import build_all_contexts, load_personas, load_prospects, match_persona, build_context
from claude_client import OutreachGenerator

# ─────────────────────────────────────────────
# Setup
# ─────────────────────────────────────────────

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("output")
SAMPLE_DATA = Path("sample_data/prospects.csv")
CONFIG_PATH = Path("config/personas.yaml")


def run_pipeline(
    csv_path: str = str(SAMPLE_DATA),
    limit: int = None,
    prospect_name: str = None,
    min_score: float = 0.0,
    steps: int = 3,
    delay: float = 1.0,
):
    """
    Run the full outreach generation pipeline.

    Args:
        csv_path: Path to prospect CSV
        limit: Max number of prospects to process
        prospect_name: Process only this prospect (exact name match)
        min_score: Skip prospects below this enrichment score
        steps: Number of emails per sequence
        delay: Seconds between API calls (rate limiting)
    """
    # Check for API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error(
            "ANTHROPIC_API_KEY not found. "
            "Set it in .env or as an environment variable.\n"
            "  Option 1: Create a .env file with ANTHROPIC_API_KEY=sk-ant-...\n"
            "  Option 2: export ANTHROPIC_API_KEY=sk-ant-..."
        )
        sys.exit(1)

    # Initialize
    OUTPUT_DIR.mkdir(exist_ok=True)
    generator = OutreachGenerator(api_key=api_key)

    # Build contexts
    logger.info("=" * 60)
    logger.info("BUILDING PROSPECT CONTEXTS")
    logger.info("=" * 60)
    contexts = build_all_contexts(csv_path, str(CONFIG_PATH))

    # Apply filters
    if prospect_name:
        contexts = [
            c for c in contexts
            if c["prospect"]["name"].lower() == prospect_name.lower()
        ]
        if not contexts:
            logger.error(f"No prospect found with name: {prospect_name}")
            sys.exit(1)
        logger.info(f"Filtered to single prospect: {prospect_name}")

    if min_score > 0:
        before = len(contexts)
        contexts = [c for c in contexts if c["enrichment_score"] >= min_score]
        logger.info(f"Filtered by min score {min_score}: {before} → {len(contexts)} prospects")

    if limit:
        contexts = contexts[:limit]
        logger.info(f"Limited to {limit} prospects")

    # Generate sequences
    logger.info("")
    logger.info("=" * 60)
    logger.info("GENERATING OUTREACH SEQUENCES")
    logger.info("=" * 60)

    results = []
    total = len(contexts)

    for i, context in enumerate(contexts):
        name = context["prospect"]["name"]
        company = context["prospect"]["company"]
        score = context["enrichment_score"]

        logger.info(f"")
        logger.info(f"[{i+1}/{total}] {name} @ {company} (score: {score})")
        logger.info(f"  Persona: {context['persona']['key']} | Tone: {context['persona']['tone']}")

        sequence = generator.generate_sequence(context, steps=steps)
        results.append(sequence)

        # Log preview
        emails = sequence.get("emails", [])
        if emails:
            logger.info(f"  Generated {len(emails)} emails:")
            for email in emails:
                logger.info(f"    Step {email.get('step')}: \"{email.get('subject', '')}\" ({email.get('angle', '')})")

            linkedin = sequence.get("linkedin_message", "")
            if linkedin:
                preview = linkedin[:80] + "..." if len(linkedin) > 80 else linkedin
                logger.info(f"  LinkedIn: \"{preview}\"")

            logger.info(f"  Cadence: {sequence.get('suggested_send_cadence', 'N/A')}")
        else:
            logger.warning(f"  ⚠ No emails generated")

        # Rate limiting between API calls
        if i < total - 1 and delay > 0:
            time.sleep(delay)

    # Export results
    logger.info("")
    logger.info("=" * 60)
    logger.info("EXPORTING RESULTS")
    logger.info("=" * 60)

    export_json(results)
    export_csv(results)
    print_summary(results, contexts)


def export_json(results: list[dict]):
    """Export full sequence data as JSON."""
    path = OUTPUT_DIR / "sequences.json"
    with open(path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    logger.info(f"Full sequences → {path}")


def export_csv(results: list[dict]):
    """Export flat CSV for CRM/outreach tool import."""
    path = OUTPUT_DIR / "sequences_crm_import.csv"
    rows = []

    for seq in results:
        meta = seq.get("metadata", {})
        for email in seq.get("emails", []):
            rows.append({
                "prospect_name": meta.get("prospect_name", ""),
                "company": meta.get("company", ""),
                "persona": meta.get("persona", ""),
                "step": email.get("step", ""),
                "subject": email.get("subject", ""),
                "body": email.get("body", ""),
                "angle": email.get("angle", ""),
                "send_cadence": seq.get("suggested_send_cadence", ""),
            })

        # Add LinkedIn message as a separate row
        linkedin = seq.get("linkedin_message", "")
        if linkedin:
            rows.append({
                "prospect_name": meta.get("prospect_name", ""),
                "company": meta.get("company", ""),
                "persona": meta.get("persona", ""),
                "step": "linkedin",
                "subject": "",
                "body": linkedin,
                "angle": "linkedin_inmail",
                "send_cadence": "",
            })

    if rows:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        logger.info(f"CRM import CSV → {path} ({len(rows)} rows)")


def print_summary(results: list[dict], contexts: list[dict]):
    """Print a final summary to the console."""
    total_emails = sum(len(r.get("emails", [])) for r in results)
    total_linkedin = sum(1 for r in results if r.get("linkedin_message"))
    avg_score = sum(c["enrichment_score"] for c in contexts) / len(contexts) if contexts else 0
    errors = sum(1 for r in results if "error" in r.get("metadata", {}))

    logger.info("")
    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE")
    logger.info("=" * 60)
    logger.info(f"  Prospects processed:  {len(results)}")
    logger.info(f"  Emails generated:     {total_emails}")
    logger.info(f"  LinkedIn messages:    {total_linkedin}")
    logger.info(f"  Avg enrichment score: {avg_score:.2f}")
    logger.info(f"  Errors:               {errors}")
    logger.info(f"  Output directory:     {OUTPUT_DIR}/")
    logger.info("")
    logger.info("Files:")
    logger.info(f"  sequences.json         — Full sequence data")
    logger.info(f"  sequences_crm_import.csv — Flat CSV for CRM import")
    logger.info("=" * 60)


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate personalized outreach sequences using Claude API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_pipeline.py                          # Process all prospects
  python run_pipeline.py --limit 3                # First 3 prospects only
  python run_pipeline.py --prospect "Sarah Chen"  # Single prospect
  python run_pipeline.py --min-score 0.7          # High-context only
  python run_pipeline.py --steps 5                # 5-email sequences
        """,
    )
    parser.add_argument(
        "--csv", default=str(SAMPLE_DATA),
        help="Path to prospect CSV file (default: sample_data/prospects.csv)",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Max number of prospects to process",
    )
    parser.add_argument(
        "--prospect", type=str, default=None,
        help="Process only this prospect (exact name match)",
    )
    parser.add_argument(
        "--min-score", type=float, default=0.0,
        help="Skip prospects below this enrichment score (0.0-1.0)",
    )
    parser.add_argument(
        "--steps", type=int, default=3,
        help="Number of emails per sequence (default: 3)",
    )
    parser.add_argument(
        "--delay", type=float, default=1.0,
        help="Seconds between API calls for rate limiting (default: 1.0)",
    )

    args = parser.parse_args()

    run_pipeline(
        csv_path=args.csv,
        limit=args.limit,
        prospect_name=args.prospect,
        min_score=args.min_score,
        steps=args.steps,
        delay=args.delay,
    )


if __name__ == "__main__":
    main()
