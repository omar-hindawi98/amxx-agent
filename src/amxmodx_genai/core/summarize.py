"""LLM-based session summarization for long-term memory."""

from strands import Agent

from amxmodx_genai.core.model import make_model


async def summarize_session(history: list[dict], prior_summary: str) -> str:
    """Summarize or update a session's conversation history using the model.

    Returns an empty string when history contains no text turns.
    """
    lines = []
    for msg in history:
        role = msg["role"]
        for block in msg.get("content", []):
            if isinstance(block, dict) and block.get("text"):
                lines.append(f"{role}: {block['text']}")

    if not lines:
        return ""

    conversation = "\n".join(lines)
    if prior_summary:
        prompt = (
            f"Prior summary:\n{prior_summary}\n\n"
            f"New session:\n{conversation}\n\n"
            "Merge into one updated summary. 3-5 bullet points, under 200 words."
        )
    else:
        prompt = (
            f"Conversation:\n{conversation}\n\n"
            "Summarize key facts, preferences, and outcomes. 3-5 bullet points, under 200 words."
        )

    agent = Agent(model=make_model(), system_prompt="You are a concise summarizer.")
    result = await agent.invoke_async(prompt)
    text = ""
    if hasattr(result, "message") and result.message:
        for block in result.message.content:
            if hasattr(block, "text") and block.text:
                text += block.text
    return text.strip()
