"""Looping CLI copilot: multi-turn REPL with tool calling
(get_case_summary, create_case_note). See README.md for setup."""


import json
import os

from openai import OpenAI

BASE_URL = os.environ.get("AZURE_OPENAI_BASE_URL", "")
API_KEY = os.environ.get("AZURE_OPENAI_API_KEY", "")
if not BASE_URL or not API_KEY:
    raise SystemExit(
        "Set AZURE_OPENAI_BASE_URL and AZURE_OPENAI_API_KEY in your environment first."
    )

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
MODEL = "gpt-5-mini"  # instant-access model name — no deployment needed

SYSTEM_PROMPT = (
    "You are a CRM copilot for a healthcare payer support team. "
    "Use the available tools to look up cases and record notes. Be concise."
)

# In-memory case store. Weeks 3-4: swap for a real RAG lookup.
CASES = {
    "1042": {"status": "open", "summary": "Billing dispute, awaiting review", "notes": []},
    "1043": {"status": "pending", "summary": "Eligibility verification", "notes": []},
}


def get_case_summary(case_id: str) -> str:
    case = CASES.get(case_id)
    if not case:
        return json.dumps({"case_id": case_id, "error": "case not found"})
    return json.dumps({"case_id": case_id, **case})


def create_case_note(case_id: str, note: str) -> str:
    case = CASES.setdefault(case_id, {"status": "open", "summary": "", "notes": []})
    case["notes"].append(note)
    return json.dumps({"case_id": case_id, "note_added": note, "all_notes": case["notes"]})


TOOLS = [
    {
        "type": "function",
        "name": "get_case_summary",
        "description": "Get the status, summary, and notes of a customer support case by ID.",
        "parameters": {
            "type": "object",
            "properties": {"case_id": {"type": "string"}},
            "required": ["case_id"],
        },
    },
    {
        "type": "function",
        "name": "create_case_note",
        "description": "Attach a note to a customer support case.",
        "parameters": {
            "type": "object",
            "properties": {
                "case_id": {"type": "string"},
                "note": {"type": "string"},
            },
            "required": ["case_id", "note"],
        },
    },
]

FUNCTIONS = {
    "get_case_summary": get_case_summary,
    "create_case_note": create_case_note,
}


def run_turn(user_text: str, prev_id: str | None) -> str | None:
    """Run one user turn to completion (possibly multiple tool rounds).

    Returns the latest response id so the next turn chains the conversation.
    """
    turn_input = user_text
    kwargs: dict = {}
    if prev_id:
        kwargs["previous_response_id"] = prev_id
    while True:
        resp = client.responses.create(
            model=MODEL,
            instructions=SYSTEM_PROMPT,
            tools=TOOLS,
            input=turn_input,
            **kwargs,
        )
        kwargs["previous_response_id"] = resp.id  # chain follow-ups within this turn
        tool_outputs = []
        for item in resp.output:
            if item.type == "function_call":
                print(f"  [tool] {item.name}({item.arguments})")
                result = FUNCTIONS[item.name](**json.loads(item.arguments))
                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": item.call_id,
                        "output": result,
                    }
                )
        if resp.output_text:
            print(f"copilot> {resp.output_text}\n")
        if not tool_outputs:
            return resp.id
        turn_input = tool_outputs


def main() -> None:
    print("CRM copilot — type 'quit' to exit.\n")
    prev_id = None
    while True:
        try:
            user_text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if user_text.lower() in {"quit", "exit"}:
            break
        if not user_text:
            continue
        prev_id = run_turn(user_text, prev_id)


if __name__ == "__main__":
    main()
