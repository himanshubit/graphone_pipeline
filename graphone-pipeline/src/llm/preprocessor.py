import re

TAGS_TO_REMOVE = {"script", "style", "svg", "nav", "footer", "header", "noscript", "iframe"}


def prepare_llm_context(raw_text: str, max_tokens: int = 6000) -> str:
    """Dual-zone windowing: keeps intro and trailing sections to fit LLM context budgets (~4 chars/token)."""
    dense_text = re.sub(r'\s+', ' ', raw_text).strip()

    char_limit = max_tokens * 4
    if len(dense_text) <= char_limit:
        return dense_text

    half_limit = char_limit // 2
    head = dense_text[:half_limit]
    tail = dense_text[-half_limit:]

    return f"{head}\n\n...[TRUNCATED TO PREVENT 413]...\n\n{tail}"
