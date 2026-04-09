"""
claude_client.py
----------------
Claude API integration for generating personalized outreach sequences.

Handles prompt construction, API calls, response parsing, and retry logic.
The prompt engineering here is the core IP of the project.
"""

import json
import logging
import time
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)


class OutreachGenerator:
    """
    Generates personalized outreach sequences using the Claude API.

    Design philosophy:
    - Context-heavy prompts > instruction-heavy prompts
    - Persona-specific system prompts (not just tone adjustments)
    - Constraint-driven output (max length, required refs, forbidden phrases)
    - Structured JSON output for reliable parsing
    """

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_retries = 3

    def generate_sequence(self, context: dict, steps: int = 3) -> dict:
        """
        Generate a multi-step outreach sequence for a single prospect.

        Args:
            context: Full context object from context_builder.build_context()
            steps: Number of emails in the sequence (default: 3)

        Returns:
            dict with: emails (list), linkedin_message (str), metadata (dict)
        """
        system_prompt = self._build_system_prompt(context)
        user_prompt = self._build_user_prompt(context, steps)

        logger.info(
            f"Generating {steps}-step sequence for "
            f"{context['prospect']['name']} ({context['persona']['key']})"
        )

        response = self._call_api(system_prompt, user_prompt)

        if response:
            parsed = self._parse_response(response)
            parsed["metadata"] = {
                "prospect_name": context["prospect"]["name"],
                "company": context["prospect"]["company"],
                "persona": context["persona"]["key"],
                "tone": context["persona"]["tone"],
                "enrichment_score": context["enrichment_score"],
                "model": self.model,
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            return parsed

        return {
            "emails": [],
            "linkedin_message": "",
            "suggested_send_cadence": "",
            "metadata": {"error": "Generation failed"},
        }

    def generate_segmentation_sql(
        self, segment_description: str, table_schema: str
    ) -> str:
        """
        Generate a SQL WHERE clause from natural language.

        Example:
            "Mid-market SaaS in fintech, 50-200 employees"
            → WHERE industry = 'SaaS' AND sub_industry = 'Fintech'
              AND employee_count BETWEEN 50 AND 200
        """
        system = (
            "You are a SQL expert. Generate a clean SQL WHERE clause "
            "from the user's segment description. Use the provided schema. "
            "Output ONLY the WHERE clause. Standard SQL syntax."
        )
        user = (
            f"Table schema:\n{table_schema}\n\n"
            f"Segment: {segment_description}\n\n"
            "Generate the WHERE clause:"
        )

        response = self._call_api(system, user)
        return response.strip() if response else ""

    # ─────────────────────────────────────────────
    # Prompt Engineering — the core of the project
    # ─────────────────────────────────────────────

    def _build_system_prompt(self, context: dict) -> str:
        """
        Build a persona-specific system prompt.

        The system prompt defines WHO Claude is writing as and
        WHAT constraints apply. The user prompt provides prospect context.
        """
        persona = context["persona"]
        tone = persona["tone"]

        tone_instructions = {
            "executive": (
                "You are writing to a VP or C-level executive. Be brief, strategic, "
                "and results-focused. Lead with a relevant insight, not a pitch. "
                "Max 3-4 sentences per email. Their time is scarce — respect it."
            ),
            "peer": (
                "You are a peer reaching out to another operator. Keep it conversational, "
                "direct, and specific. Write like you'd message a sharp colleague — "
                "no fluff, just substance. Reference their tools and workflows."
            ),
            "professional": (
                "You are a senior SDR writing personalized outreach. Be concise, "
                "value-driven, and specific. Every sentence must earn its place. "
                "Reference something concrete about the prospect's company or role."
            ),
        }

        system = tone_instructions.get(tone, tone_instructions["professional"])

        # Add constraints
        max_length = persona.get("max_length", 200)
        system += f"\n\nConstraints:\n- Max {max_length} words per email"

        required_refs = persona.get("required_references", [])
        if required_refs:
            system += f"\n- MUST reference: {'; '.join(required_refs)}"

        forbidden = persona.get("forbidden_phrases", [])
        if forbidden:
            system += f"\n- NEVER use these phrases: {', '.join(forbidden)}"

        system += (
            "\n- Never claim a mutual connection unless provided"
            "\n- Never fabricate statistics or case studies"
            "\n- Never use generic openers or closers"
            "\n- Each email in the sequence must take a DIFFERENT angle"
        )

        return system

    def _build_user_prompt(self, context: dict, steps: int) -> str:
        """
        Build the user prompt with full prospect context.

        Philosophy: Rich context > elaborate instructions.
        Give Claude everything about the prospect and let the
        system prompt handle the writing style.
        """
        p = context["prospect"]
        crm = context["crm_history"]
        persona = context["persona"]

        prompt = f"""Generate a {steps}-step outreach sequence for this prospect.

PROSPECT:
- Name: {p['name']}
- Title: {p['title']}
- Company: {p['company']}
- Industry: {p['industry']}
- Company Size: {p['employee_count']} employees
- Revenue Range: {p.get('revenue_range', 'Unknown')}
- Tech Stack: {', '.join(p.get('technologies', [])) or 'Unknown'}
- Location: {p.get('location', 'Unknown')}

CRM HISTORY:
- Last Contact: {crm.get('last_touch') or 'Never contacted'}
- Previous Touches: {crm.get('touch_count', 0)}
- Days Since Contact: {crm.get('days_since_contact') or 'N/A'}
- Deal Stage: {crm.get('deal_stage') or 'No active opportunity'}
- Lead Source: {crm.get('lead_source') or 'Unknown'}
- Notes: {'; '.join(crm.get('notes', [])) or 'None'}

PERSONA CONTEXT:
- Buyer persona: {persona['key']}
- Their likely pain points: {', '.join(persona.get('pain_points', []))}

OUTPUT FORMAT (respond ONLY with valid JSON, no markdown fences):
{{
  "emails": [
    {{
      "step": 1,
      "subject": "subject line here",
      "body": "email body here",
      "angle": "2-3 word description of the approach used"
    }}
  ],
  "linkedin_message": "a short LinkedIn connection/InMail message",
  "suggested_send_cadence": "e.g. Day 1, Day 3, Day 7"
}}

SEQUENCE STRATEGY:
- Step 1: Value-first introduction — lead with insight, not a pitch
- Step 2: Follow-up with different angle — social proof, data point, or question
- Step 3: Breakup / last chance — short, direct, create mild urgency
- LinkedIn: Condensed, conversational version of Step 1"""

        return prompt

    # ─────────────────────────────────────────────
    # API + Parsing
    # ─────────────────────────────────────────────

    def _call_api(
        self, system_prompt: str, user_prompt: str, retries: int = 0
    ) -> Optional[str]:
        """Call Claude API with retry + rate limit handling."""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return response.content[0].text

        except anthropic.RateLimitError:
            if retries < self.max_retries:
                wait = 2 ** (retries + 1)
                logger.warning(f"Rate limited. Retrying in {wait}s...")
                time.sleep(wait)
                return self._call_api(system_prompt, user_prompt, retries + 1)
            logger.error("Rate limit exceeded after retries")
            return None

        except anthropic.APIError as e:
            logger.error(f"Claude API error: {e}")
            return None

    def _parse_response(self, raw: str) -> dict:
        """Parse Claude's JSON response into structured data."""
        cleaned = raw.strip()

        # Strip markdown code fences if present
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON, returning raw text as single email")
            return {
                "emails": [
                    {"step": 1, "subject": "", "body": cleaned, "angle": "raw_output"}
                ],
                "linkedin_message": "",
                "suggested_send_cadence": "",
            }
