"""LLM-based session summarization for long-term memory."""

from strands import Agent

from amxx_agent.core.model import get_summary_model


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

    agent = Agent(
        model=get_summary_model(),
        system_prompt="You are a concise summarizer.",
        tools=[],
    )
    result = await agent.invoke_async(prompt)
    text = ""
    result_msg = getattr(result, "message", None)
    if result_msg:
        content = (
            result_msg.get("content", [])
            if isinstance(result_msg, dict)
            else getattr(result_msg, "content", [])
        )
        for block in content:
            block_text = (
                block.get("text", "") if isinstance(block, dict) else getattr(block, "text", "")
            )
            if block_text:
                text += block_text
    return text.strip()
