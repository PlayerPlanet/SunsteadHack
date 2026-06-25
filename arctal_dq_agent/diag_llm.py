"""One-shot LLM diagnostic: fire a single real call on the exact prompt path the
run uses, and print the TRUE error instead of swallowing it. Throwaway helper.

    cd arctal_dq_agent
    ANTHROPIC_API_KEY=sk-... /path/to/python diag_llm.py
"""

import os
import traceback

from agent.data import build_context, load_tables
from agent.reasoning import LLMReasoner, triage_category, triage_impact

key = os.environ.get("ANTHROPIC_API_KEY", "")
print("key loaded:", bool(key), "| ...{}".format(key[-6:] if key else "NONE"))

t = load_tables()
ctx = build_context(t)
rsn = LLMReasoner()

# pick one impact row that triages into Tier 1
row = next(r for r in t["impacts"] if triage_impact(r, ctx))
prompt = rsn._impact_prompt(row, ctx, triage_impact(row, ctx))
print("model:", rsn.first, "| prompt chars:", len(prompt))
print("-" * 60)

for model in (rsn.first, rsn.strong):
    try:
        msg = rsn._client.messages.create(
            model=model, max_tokens=120,
            messages=[{"role": "user", "content": prompt}],
        )
        print(f"[{model}] OK ->", repr(msg.content[0].text[:120]))
        print(f"[{model}] usage:", msg.usage)
    except Exception:
        print(f"[{model}] FAILED:")
        traceback.print_exc()
    print("-" * 60)
