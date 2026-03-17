"""
LLM abstraction layer.
Routes prompts to Gemini or OpenAI based on provider config.
"""

import os


def run_prompt(
    provider: str,
    model: str,
    prompt: str,
    search_context: str | None = None,
) -> str:
    """
    Run a prompt against the specified LLM provider.

    Args:
        provider: "anthropic" or "openai"
        model: Model name (e.g. "claude-sonnet-4-20250514", "gpt-4o")
        prompt: The user prompt
        search_context: Optional web search results to prepend

    Returns:
        The LLM's text response
    """
    full_prompt = prompt
    if search_context:
        full_prompt = (
            "Here is some relevant context from web search:\n\n"
            f"{search_context}\n\n"
            "---\n\n"
            f"{prompt}"
        )

    if provider == "gemini":
        return _call_gemini(model, full_prompt)
    elif provider == "openai":
        return _call_openai(model, full_prompt)
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


def _call_gemini(model: str, prompt: str) -> str:
    """Call the Google Gemini API."""
    from google import genai

    api_key = os.environ.get("GEMINI_API_KEY", "")
    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=model,
        contents=prompt,
    )

    return response.text or ""


def _call_openai(model: str, prompt: str) -> str:
    """Call the OpenAI API."""
    import openai

    api_key = os.environ.get("OPENAI_API_KEY", "")
    client = openai.OpenAI(api_key=api_key)

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4096,
    )

    return response.choices[0].message.content or ""
