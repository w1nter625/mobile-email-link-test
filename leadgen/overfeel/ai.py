"""Claude calls: research (with web search), outreach email, landing page."""
from __future__ import annotations

import json
import re

import anthropic

client = anthropic.Anthropic()
BETAS = ["server-side-fallback-2026-07-01"]
WEB_TOOLS = [
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 6},
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 4},
]

OPENERS = {
    "maps": "Open by saying, truthfully, that you came across their business on Google Maps while looking at local spots in their area, and something specific you noticed (from their reviews/photos description) caught your eye.",
    "walked_by": "Open by saying you walked past their place recently and it stuck with you. Only mention details that appear in the research — do not invent what you saw.",
    "visited": "Open by saying you stopped in recently as a customer. Use ONLY the visit note provided by the sender for any specifics; if there is no note, keep it general.",
}


def _run(model: str, messages: list, max_tokens: int, tools=None, effort: str = "medium", system: str | None = None):
    """Stream a request, resuming server-tool pause_turn, and return final text."""
    kwargs = dict(
        model=model, max_tokens=max_tokens, betas=BETAS, fallbacks="default",
        thinking={"type": "adaptive"}, output_config={"effort": effort},
    )
    if tools:
        kwargs["tools"] = tools
    if system:
        kwargs["system"] = system
    msgs = list(messages)
    for _ in range(6):
        with client.beta.messages.stream(messages=msgs, **kwargs) as stream:
            resp = stream.get_final_message()
        if resp.stop_reason == "pause_turn":
            msgs.append({"role": "assistant", "content": resp.content})
            continue
        break
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"model declined: {getattr(resp, 'stop_details', None)}")
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def _json(text: str) -> dict:
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    raw = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    return json.loads(raw)


def _lead_brief(lead: dict) -> str:
    keep = {k: lead.get(k) for k in (
        "name", "category", "address", "phone", "website", "rating", "review_count",
        "summary", "hours", "reviews", "maps_url", "lead_type", "site_reasons", "emails",
    )}
    if lead.get("site_text"):
        keep["website_text_excerpt"] = lead["site_text"][:2500]
    return json.dumps(keep, ensure_ascii=False, indent=2)


def research(lead: dict, model: str) -> dict:
    prompt = f"""You are a researcher for Overfeel, a small web design studio, preparing a thoughtful, personalised pitch to a local business.

Business data from Google Maps (and their website if they have one):
{_lead_brief(lead)}

Use web search / fetch to:
1. Understand the business: what they sell, signature items/services, who their customers are, their personality, what reviewers love, anything distinctive (history, owner story, neighbourhood).
2. Note their online-presence gaps (no website, outdated site, not mobile-friendly, no online booking/ordering, menu only as a photo, etc.).
3. If the data above has no email, look for a PUBLIC business email (their Facebook/Instagram bio, Yelp, Chamber of Commerce, local directories). Only report an email you actually saw on a page, with that page's URL. Never guess or construct one.
4. Propose ONE small, concrete, genuinely useful idea for a landing page tailored to them (e.g. a "today's bake" board, a booking-first page for a barber, a story page for a 30-year-old family diner). Not generic.

Reply with only a JSON object in a ```json block, keys:
{{"overview": str, "offerings": [str], "audience": str, "personality": str,
  "review_highlights": [str], "presence_gaps": [str],
  "email": {{"address": str|null, "source_url": str|null}},
  "other_contacts": {{"instagram": str|null, "facebook": str|null, "contact_form": str|null}},
  "idea": {{"title": str, "one_liner": str, "why_it_helps": str, "sections": [str]}},
  "design": {{"mood": str, "palette": [str], "typography": str, "imagery": str}}}}"""
    return _json(_run(model, [{"role": "user", "content": prompt}], 32000, tools=WEB_TOOLS, effort="high"))


def write_email(lead: dict, info: dict, sender: dict, opener: str, model: str, visit_note: str = "") -> dict:
    prompt = f"""Write a cold outreach email in English from {sender['name']} at {sender['company']} to the owner of {lead['name']}.

Business research:
{json.dumps(info, ensure_ascii=False, indent=2)}
Lead type: {lead['lead_type']} ({'; '.join(lead.get('site_reasons') or []) or 'no website'})
Sender visit note (may be empty): {visit_note!r}

Opening: {OPENERS.get(opener, OPENERS['maps'])}

Story arc: we noticed them -> we genuinely liked something specific about them -> it gave us a small idea ({info['idea']['title']}: {info['idea']['one_liner']}) -> we went ahead and sketched a quick landing page concept for them, free, link: {{{{PREVIEW_LINK}}}} -> no pressure; if they like it we'd be happy to chat, if not, they can keep the idea.

Rules:
- Sincere, warm, humble, specific. Sound like a real person, not marketing. No hype words ("revolutionize", "skyrocket"), no fake urgency, no flattery overload.
- Never claim anything not supported by the research or visit note. Do not invent numbers or results.
- Mention their online gap gently, without criticising their current site.
- 120-180 words body. Short paragraphs. Plain text.
- Sign off with: {sender['name']} / {sender['title']} / {sender['website']}
- End with a one-line P.S. or footer: "If you'd rather not hear from us, just reply 'no thanks' and we won't email again." then the postal address: {sender['postal_address']}
- Subject line: short, lowercase-friendly, personal, mentions their business name, no clickbait.

Reply with only a ```json block: {{"subject": str, "body": str}}"""
    return _json(_run(model, [{"role": "user", "content": prompt}], 8000, effort="medium"))


def landing_page(lead: dict, info: dict, sender: dict, model: str) -> str:
    prompt = f"""Design and build a creative, production-quality single-file landing page concept for this local business. It is a free pitch from {sender['company']}, so it must feel made *for them*, not a template.

Business:
{_lead_brief({k: v for k, v in lead.items() if k != 'site_text'})}
Research:
{json.dumps(info, ensure_ascii=False, indent=2)}

Requirements:
- Build around the idea "{info['idea']['title']}" — {info['idea']['one_liner']}. Sections guide: {info['idea']['sections']}.
- Use real facts only (name, address, phone, hours, offerings, review quotes paraphrased or quoted from the data). Where content is unknown, use tasteful obvious placeholders like "[Your signature item]".
- Distinctive art direction based on: {json.dumps(info.get('design', {}), ensure_ascii=False)}. Avoid generic SaaS look, purple gradients, stock "hero + 3 cards". Use bold typography (Google Fonts allowed), one memorable interaction or micro-animation, CSS-drawn or SVG illustration instead of external images.
- Mobile-first, responsive, accessible (contrast, alt text, semantic HTML), fast. Click-to-call, map link ({lead.get('maps_url')}), clear primary CTA.
- Only external resources allowed: Google Fonts. All CSS/JS inline.
- Small unobtrusive corner tag: "Concept by {sender['company']}" linking to {sender['website']}.

Output ONLY the complete HTML document, starting with <!doctype html>. No commentary."""
    html = _run(model, [{"role": "user", "content": prompt}], 64000, effort="high")
    m = re.search(r"(<!doctype html.*</html>)", html, re.S | re.I)
    return m.group(1) if m else html
