"""
accounts/ai_utils.py
--------------------
Lightweight wrapper around the Google Gemini API for RHMS AI features.
Uses the new `google-genai` SDK (replaces deprecated `google-generativeai`).
"""
import json
import re

from django.conf import settings

# ---------------------------------------------------------------------------
# SDK import — guarded so the app still boots if google-genai is not installed
# ---------------------------------------------------------------------------
try:
    from google import genai
    from google.genai import types as genai_types
    _GENAI_AVAILABLE = True
except ImportError:
    genai = None
    genai_types = None
    _GENAI_AVAILABLE = False

# Module-level client cache — created once on first use, reused on every call
_client = None


def _get_client():
    """
    Returns a cached Gemini client. Creates it on the first call.
    Raises clear errors if the SDK is missing or the API key is not set.
    """
    global _client

    if not _GENAI_AVAILABLE:
        raise ImportError(
            "google-genai is not installed. Run: pip install google-genai"
        )

    api_key = getattr(settings, 'GEMINI_API_KEY', '')
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is not set. "
            "Add it to your .env file: GEMINI_API_KEY=your-key"
        )

    if _client is None:
        _client = genai.Client(api_key=api_key)

    return _client


# ---------------------------------------------------------------------------

def friendly_ai_error(exc: Exception) -> str:
    """
    Converts a raw Gemini API exception into a short, user-friendly message.
    Keeps internal error details out of the UI.
    """
    msg = str(exc)
    if '429' in msg or 'RESOURCE_EXHAUSTED' in msg or 'quota' in msg.lower():
        return 'AI feature is temporarily unavailable — daily limit reached. Please try again later.'
    if '503' in msg or 'unavailable' in msg.lower():
        return 'AI service is temporarily unavailable. Please try again in a moment.'
    if '401' in msg or '403' in msg or 'API_KEY' in msg:
        return 'AI feature is not configured. Please contact the administrator.'
    return 'AI feature is temporarily unavailable. Please try again later.'


def draft_announcement(topic: str) -> dict:
    """
    Uses Gemini to write a professional property management announcement.

    Args:
        topic: A short phrase describing what the announcement is about.

    Returns:
        dict with keys: 'title' (str) and 'content' (str)
    """
    client = _get_client()

    prompt = f"""You are a professional property manager writing a formal announcement
for tenants in a residential rental building.

Topic / keywords the landlord provided: "{topic}"

Write a short, polite, and clear announcement. Return ONLY a valid JSON object
with exactly two keys:
  "title"   - A concise subject line (max 10 words)
  "content" - The full announcement body (2-4 sentences, professional tone)

Example output format:
{{"title": "Scheduled Water Interruption - Saturday 9 AM", "content": "Dear residents, please be advised that water supply to the building will be interrupted on Saturday from 9:00 AM to 1:00 PM due to routine maintenance work. We apologise for any inconvenience. Kindly store sufficient water before then. Thank you for your understanding."}}

Now write the announcement for the given topic. Return ONLY the JSON, no markdown fences."""

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
            max_output_tokens=500,
            temperature=0.3,
        ),
    )

    raw = response.text.strip()
    raw = re.sub(r'^```json\s*', '', raw)
    raw = re.sub(r'^```\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"title": topic.title(), "content": raw}

    return {
        "title": str(data.get("title", topic.title())).strip(),
        "content": str(data.get("content", "")).strip(),
    }


def classify_maintenance(issue: str, description: str) -> dict:
    """
    Uses Gemini to suggest a category and priority for a maintenance request.

    Args:
        issue:       Short title of the issue e.g. "Leaking bathroom tap"
        description: Detailed description from the tenant

    Returns:
        dict with keys: 'category', 'priority', 'reason'
    """
    client = _get_client()

    prompt = f"""You are an expert property maintenance coordinator.
A tenant has submitted the following maintenance request:

Issue title: "{issue}"
Description: "{description}"

Your job is to classify this request. Return ONLY a valid JSON object with exactly three keys:

  "category" - must be exactly one of: plumbing, electrical, carpentry, appliances, painting, other
  "priority"  - must be exactly one of: low, medium, high
                Use "high" for safety risks (electrical sparks, flooding, gas) or things that make the unit unusable.
                Use "medium" for issues that are inconvenient but not dangerous.
                Use "low" for cosmetic or minor issues.
  "reason"    - one short sentence (max 15 words) explaining your classification

Example output:
{{"category": "plumbing", "priority": "high", "reason": "Active water leak can cause structural damage and mold growth."}}

Return ONLY the JSON object, no markdown fences, no extra text."""

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
            max_output_tokens=300,
            temperature=0.2,
        ),
    )

    raw = response.text.strip()
    raw = re.sub(r'^```json\s*', '', raw)
    raw = re.sub(r'^```\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)

    VALID_CATEGORIES = {'plumbing', 'electrical', 'carpentry', 'appliances', 'painting', 'other'}
    VALID_PRIORITIES  = {'low', 'medium', 'high'}

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {'category': 'other', 'priority': 'low', 'reason': 'Could not classify automatically.'}

    category = str(data.get('category', 'other')).lower().strip()
    priority = str(data.get('priority', 'low')).lower().strip()

    return {
        'category': category if category in VALID_CATEGORIES else 'other',
        'priority': priority if priority in VALID_PRIORITIES else 'low',
        'reason':   str(data.get('reason', '')).strip(),
    }


def tenant_chat(message: str, tenant_context: dict, history: list) -> str:
    """
    Handles a single tenant chat turn using Gemini.

    Args:
        message:         The tenant's latest message.
        tenant_context:  Dict with tenant-specific data injected into the system prompt.
        history:         List of previous turns: [{"role": "user"|"model", "text": "..."}]

    Returns:
        str — the assistant's reply
    """
    client = _get_client()

    t = tenant_context
    system_prompt = f"""You are a friendly, professional virtual assistant for PropertyHub,
a residential property management system. You are speaking directly with a tenant.

--- TENANT PROFILE (use this to answer questions accurately) ---
Name:             {t.get('name', 'Tenant')}
Unit:             {t.get('unit_number', 'N/A')}
Property:         {t.get('property_name', 'N/A')}
Rent Amount:      KES {t.get('rent_amount', 'N/A')} per month
Current Balance:  KES {t.get('balance', '0')}  (positive = owes money, negative = in credit)
Move-in Date:     {t.get('move_in_date', 'N/A')}
Lease End:        {t.get('lease_end', 'Not specified')}
Active Requests:  {t.get('active_requests', 0)} open maintenance request(s)
--- END OF PROFILE ---

Rules:
- Answer ONLY questions related to this tenancy, property, payments, maintenance, and lease.
- Be concise (2-3 sentences max unless the tenant asks for detail).
- If you don't know something, say so honestly and suggest they contact management.
- NEVER make up numbers. Only use the figures from the profile above.
- If asked how to report a fault, tell them to go to the "Maintenance" section in the sidebar.
- If asked about their balance: positive balance means they OWE money, negative means they are ahead.
- Today's date: {t.get('today', 'unknown')}.
- Respond in a warm, professional tone. Keep it short."""

    contents = []
    for turn in history[-6:]:  # Keep last 6 turns (3 exchanges) to stay within token limits
        role = 'user' if turn.get('role') == 'user' else 'model'
        contents.append(genai_types.Content(
            role=role,
            parts=[genai_types.Part(text=turn.get('text', ''))]
        ))

    contents.append(genai_types.Content(
        role='user',
        parts=[genai_types.Part(text=message)]
    ))

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=contents,
        config=genai_types.GenerateContentConfig(
            system_instruction=system_prompt,
            thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
            max_output_tokens=600,
            temperature=0.4,
        ),
    )

    return response.text.strip()


def generate_dashboard_insights(data: dict) -> str:
    """
    Generates a short natural-language briefing for the landlord dashboard.

    Args:
        data: A dict of aggregated metrics pulled from the DB.

    Returns:
        str — 2-4 sentence briefing
    """
    client = _get_client()

    prompt = f"""You are a concise property management analyst writing a daily briefing for a landlord.

Here is today's portfolio data:
- Total properties: {data.get('total_properties', 0)}
- Active tenants: {data.get('active_tenants', 0)}
- Tenants with outstanding balance (owe money): {data.get('tenants_with_balance', 0)}
- Total outstanding rent owed: KES {data.get('total_outstanding', 0):,}
- Rent collected this month (confirmed): KES {data.get('monthly_collection', 0):,}
- Pending maintenance requests: {data.get('pending_maintenance', 0)}
- Maintenance requests in progress: {data.get('in_progress_maintenance', 0)}
- Requests pending for more than 7 days: {data.get('stale_maintenance', 0)}
- Move-out notices given: {data.get('move_out_notices', 0)}
- Today's date: {data.get('today', 'unknown')}

Write a professional, concise daily briefing in 2-4 sentences.
- Lead with the most urgent item (overdue payments, stale maintenance, or move-out notices if any).
- Be factual, direct, and use KES for currency.
- If everything looks good, say so briefly and positively.
- Do NOT use bullet points. Write in flowing prose only.
- Do NOT start with "Here is" or "Based on the data". Start directly with the insight."""

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
            max_output_tokens=600,
            temperature=0.3,
        ),
    )

    return response.text.strip()
