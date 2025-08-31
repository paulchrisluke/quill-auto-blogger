from __future__ import annotations
import os, hashlib
from typing import Dict, Any, List

AI_ENABLED = os.getenv("AI_ENABLED", "false").lower() == "true"

def _local_outline(title: str, why: str, highlights: List[str]) -> str:
    lines = [
        f"# Hook: {title}",
        f"- Why it matters: {why or 'Context: recently shipped improvement.'}",
        "- Demo plan:",
    ]
    for h in highlights[:3]:
        lines.append(f"  - {h}")
    lines += [
        "- Show PR → briefly explain tradeoffs",
        "- Show result → what users/devs get now",
        "- CTA: follow the repo & leave feedback"
    ]
    return "\n".join(lines)

def generate_outline(packet: Dict[str, Any]) -> str:
    title = packet.get("title_human") or packet.get("title_raw", "Story")
    why = packet.get("why", "")
    highlights = packet.get("highlights", [])
    # For M2, stay local; wire CF AI later behind flag.
    return _local_outline(title, why, highlights)
