"""
narrative.py

Turns the computed capacity/demand/variance summary into the written monthly
capability report a Program & Project Planning specialist currently drafts by
hand. If ANTHROPIC_API_KEY is set, drafts it with Claude. If not, falls back to
a deterministic template so the whole demo still runs with zero API keys
configured -- useful for anyone cloning this repo just to see it work.
"""

import os


def _template_narrative(summary_rows: list[dict], month_label: str) -> str:
    """Rule-based fallback: no API key required."""
    lines = [f"# Monthly Capability Report -- {month_label}\n"]
    lines.append(
        "_Auto-generated from crew-capacity and work-order-backlog data. "
        "No LLM configured for this run -- set ANTHROPIC_API_KEY for a "
        "narrative draft instead of this templated summary._\n"
    )

    critical = [r for r in summary_rows if r["status"] == "critical"]
    warning = [r for r in summary_rows if r["status"] == "warning"]
    good = [r for r in summary_rows if r["status"] == "good"]

    if critical:
        lines.append("## Regions over capacity (critical)\n")
        for r in critical:
            lines.append(
                f"- **{r['region']}**: demand exceeds available crew-hours by "
                f"{r['variance_pct']:.1f}% ({r['required_hours']:,.0f} required vs. "
                f"{r['available_hours']:,.0f} available). Recommend reviewing contractor "
                f"augmentation or re-sequencing lower-priority work orders.\n"
            )

    if warning:
        lines.append("## Regions approaching capacity constraints (warning)\n")
        for r in warning:
            lines.append(
                f"- **{r['region']}**: demand is {r['variance_pct']:.1f}% above available "
                f"crew-hours ({r['required_hours']:,.0f} vs. {r['available_hours']:,.0f}). "
                f"Monitor for the next 1-2 cycles.\n"
            )

    if good:
        lines.append("## Regions within capacity (on track)\n")
        for r in good:
            sign = "surplus" if r["variance_pct"] < 0 else "within tolerance"
            lines.append(
                f"- **{r['region']}**: {abs(r['variance_pct']):.1f}% {sign} "
                f"({r['required_hours']:,.0f} required vs. {r['available_hours']:,.0f} available).\n"
            )

    return "\n".join(lines)


def _llm_narrative(summary_rows: list[dict], month_label: str) -> str | None:
    """Try Claude via the anthropic SDK. Returns None on any failure so the
    caller can fall back to the template rather than crash the demo."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    try:
        import anthropic
    except ImportError:
        return None

    try:
        client = anthropic.Anthropic(api_key=api_key)
        data_block = "\n".join(
            f"- {r['region']}: required={r['required_hours']:.0f}h, "
            f"available={r['available_hours']:.0f}h, variance={r['variance_pct']:.1f}%, "
            f"status={r['status']}"
            for r in summary_rows
        )
        prompt = (
            "You are a Project & Program Planning specialist at an electric utility, "
            f"writing the monthly capability report for {month_label}. Below is the "
            "region-level capacity-vs-demand data for this month. Write a concise, "
            "professional narrative (250-350 words) for regional General Managers and "
            "Electric Operations leadership: call out which regions are over capacity and "
            "why that matters operationally, which are approaching constraints, and which "
            "are healthy. End with 2-3 concrete recommended actions. Use plain business "
            "prose, not bullet-only shorthand, though a short bullet list of actions at "
            "the end is fine.\n\nData:\n" + data_block
        )
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=900,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in message.content if block.type == "text")
        return f"# Monthly Capability Report -- {month_label}\n\n{text}"
    except Exception:
        return None


def generate_narrative(summary_rows: list[dict], month_label: str) -> str:
    llm_result = _llm_narrative(summary_rows, month_label)
    if llm_result:
        return llm_result
    return _template_narrative(summary_rows, month_label)
