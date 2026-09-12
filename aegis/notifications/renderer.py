"""
Aegis — Notification Content Renderer (AC-4.5)

Renders notifications containing all required fields:
- title
- category
- match score
- eligibility state
- deadline
- explanation
- source URL

Produces HTML, plain text, and markdown representations.
"""

from __future__ import annotations

from typing import Any


def render_immediate_notification(
    opportunity: Any,
    match_score: Any,
    eligibility_decision: Any,
) -> dict[str, Any]:
    """
    Renders an immediate match notification containing all AC-4.5 mandatory fields.
    """
    title = getattr(opportunity, "title", "Untitled Opportunity")
    category = getattr(opportunity, "category", "opportunity")
    if hasattr(category, "value"):
        category_str = category.value
    else:
        category_str = str(category)

    final_score = getattr(match_score, "final_score", 0.0)
    score_pct = f"{final_score * 100:.0f}%"

    state = getattr(eligibility_decision, "state", "UNKNOWN")
    if hasattr(state, "value"):
        state_str = state.value
    else:
        state_str = str(state)

    deadline = getattr(opportunity, "registration_deadline", None)
    if deadline is not None and hasattr(deadline, "strftime"):
        deadline_str = deadline.strftime("%B %d, %Y")
    elif deadline:
        deadline_str = str(deadline)
    else:
        deadline_str = "Open / Rolling"

    explanation = getattr(
        match_score,
        "explanation",
        "Evaluated against your profile.",
    )
    url = getattr(opportunity, "url", "#")
    organizer = getattr(opportunity, "organizer", None)
    location = getattr(opportunity, "location", None)
    mode = getattr(opportunity, "mode", None)
    if mode is not None and hasattr(mode, "value"):
        mode_str = mode.value
    else:
        mode_str = str(mode) if mode else "unspecified"

    subject = f"[Aegis Match: {score_pct}] {title}"

    # Plain text representation
    organizer_line = f"Organizer: {organizer}\n" if organizer else ""
    location_line = f"Location: {location}\n" if location else ""

    text_body = (
        f"AEGIS OPPORTUNITY ALERT\n"
        f"=======================\n\n"
        f"Title: {title}\n"
        f"Category: {category_str.capitalize()}\n"
        f"Match Score: {score_pct} ({final_score:.2f})\n"
        f"Eligibility State: {state_str}\n"
        f"Registration Deadline: {deadline_str}\n"
        f"Work Mode: {mode_str}\n"
        f"{organizer_line}"
        f"{location_line}"
        f"\nWhy this matches you:\n{explanation}\n\n"
        f"Apply / View details: {url}\n\n"
        f"--\nAegis Autonomous Intelligence"
    )

    # HTML representation
    html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.5; color: #1e293b; max-width: 600px; margin: 0 auto; padding: 20px; }}
    .badge {{ display: inline-block; padding: 4px 8px; border-radius: 4px; font-weight: 600; font-size: 12px; }}
    .badge-eligible {{ background-color: #dcfce7; color: #166534; }}
    .badge-unknown {{ background-color: #fef9c3; color: #854d0e; }}
    .badge-ineligible {{ background-color: #fee2e2; color: #991b1b; }}
    .score-badge {{ font-size: 18px; font-weight: bold; color: #4f46e5; }}
    .card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; }}
    .btn {{ display: inline-block; background-color: #4f46e5; color: #ffffff !important; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-weight: 500; margin-top: 12px; }}
  </style>
</head>
<body>
  <h2>New Opportunity Match</h2>
  <div class="card">
    <div style="display: flex; justify-content: space-between; align-items: baseline;">
      <h3 style="margin: 0;">{title}</h3>
      <span class="score-badge">{score_pct} Match</span>
    </div>
    <p style="margin: 8px 0; color: #64748b; font-size: 14px;">
      <strong>Category:</strong> {category_str.capitalize()} |
      <strong>Mode:</strong> {mode_str} |
      <strong>Deadline:</strong> {deadline_str}
    </p>
    <p>
      <strong>Eligibility:</strong>
      <span class="badge badge-{state_str.lower()}">{state_str}</span>
    </p>
    <div style="margin-top: 12px; padding: 12px; background: #ffffff; border-radius: 6px; border-left: 3px solid #4f46e5;">
      <strong>Why this matches:</strong>
      <p style="margin: 4px 0 0 0; font-size: 14px; color: #334155;">{explanation}</p>
    </div>
    <div style="margin-top: 16px;">
      <a href="{url}" class="btn" target="_blank" rel="noopener noreferrer">View Opportunity</a>
    </div>
  </div>
  <p style="font-size: 12px; color: #94a3b8; margin-top: 24px;">
    Sent autonomously by Aegis. Grounded only in verified facts and your active profile.
  </p>
</body>
</html>"""

    # Markdown representation (for in-app display)
    markdown_body = (
        f"### [{title}]({url})\n"
        f"**Category:** {category_str.capitalize()} | **Score:** {score_pct} | **Eligibility:** `{state_str}`\n"
        f"**Deadline:** {deadline_str}\n\n"
        f"> {explanation}\n"
    )

    return {
        "subject": subject,
        "title": title,
        "category": category_str,
        "match_score": final_score,
        "eligibility_state": state_str,
        "deadline": deadline_str,
        "explanation": explanation,
        "source_url": url,
        "text_body": text_body,
        "html_body": html_body,
        "markdown_body": markdown_body,
    }


def render_daily_digest(
    items: list[dict[str, Any]],
    user_name: str | None = None,
) -> dict[str, Any]:
    """
    Renders a consolidated daily digest of multiple opportunities (AC-4.1, AC-4.5).
    """
    count = len(items)
    greeting = f"Hello {user_name}," if user_name else "Hello,"
    subject = f"[Aegis Daily Digest] {count} New Opportunity Matches"

    text_lines = [
        f"{greeting}\n",
        f"Here are your top {count} opportunity matches curated by Aegis today:\n",
        "=" * 40,
    ]

    html_cards = []
    markdown_lines = [
        f"## Daily Opportunity Digest ({count} matches)\n",
    ]

    for idx, item in enumerate(items, 1):
        title = item.get("title", "Untitled")
        score = item.get("match_score", 0.0)
        score_pct = f"{score * 100:.0f}%"
        state = item.get("eligibility_state", "UNKNOWN")
        category = item.get("category", "opportunity")
        deadline = item.get("deadline", "Rolling")
        explanation = item.get("explanation", "")
        url = item.get("source_url", "#")

        text_lines.append(
            f"\n{idx}. {title} ({score_pct} Match | {state})\n"
            f"   Category: {category} | Deadline: {deadline}\n"
            f"   Reason: {explanation}\n"
            f"   Link: {url}\n"
        )

        html_cards.append(f"""
        <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; margin-bottom: 12px;">
          <div style="display: flex; justify-content: space-between;">
            <a href="{url}" style="font-weight: 600; color: #4f46e5; text-decoration: none; font-size: 16px;">{title}</a>
            <span style="font-weight: bold; color: #16a34a;">{score_pct}</span>
          </div>
          <p style="margin: 6px 0; font-size: 13px; color: #64748b;">
            Category: {category} | Status: <strong>{state}</strong> | Deadline: {deadline}
          </p>
          <p style="margin: 6px 0 0 0; font-size: 13px; color: #334155;">{explanation}</p>
        </div>""")

        markdown_lines.append(
            f"{idx}. **[{title}]({url})** — `{score_pct}` | `{state}`\n"
            f"   - Deadline: {deadline}\n"
            f"   - {explanation}\n"
        )

    text_lines.append("\n--\nAegis Autonomous Intelligence")
    text_body = "\n".join(text_lines)

    html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.5; color: #1e293b; max-width: 600px; margin: 0 auto; padding: 20px; }}
  </style>
</head>
<body>
  <h2>Your Daily Aegis Digest</h2>
  <p>{greeting} Here are today's top matches based on your profile:</p>
  {"".join(html_cards)}
  <p style="font-size: 12px; color: #94a3b8; margin-top: 24px;">
    Sent autonomously by Aegis. Grounded in verified facts.
  </p>
</body>
</html>"""

    return {
        "subject": subject,
        "item_count": count,
        "items": items,
        "text_body": text_body,
        "html_body": html_body,
        "markdown_body": "\n".join(markdown_lines),
    }
