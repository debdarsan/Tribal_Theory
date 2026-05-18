from __future__ import annotations

import time
from typing import Any, Iterable, Iterator, Mapping

from openai import OpenAI


def _is_gpt5(model: str) -> bool:
    return model.startswith("gpt-5")


def call_llm(
    client: OpenAI,
    messages: Iterable[Mapping[str, str]],
    model: str,
    *,
    max_tokens: int = 4000,
    temperature: float = 0.0,
    top_p: float = 1.0,
    frequency_penalty: float = 0.0,
    presence_penalty: float = 0.0,
    stop: Any = None,
    n: int = 1,
    seed: int | None = 42,
    stream: bool = False,
    max_retries: int = 3,
    backoff_seconds: float = 1.0,
) -> str | Iterator[str]:
    # gpt-5.x rejects `max_tokens`; only `max_completion_tokens` is accepted.
    token_kw = (
        {"max_completion_tokens": max_tokens}
        if _is_gpt5(model)
        else {"max_tokens": max_tokens}
    )

    last_err: Exception | None = None
    backoff = backoff_seconds
    response = None
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=list(messages),
                n=n,
                stop=stop,
                temperature=temperature,
                top_p=top_p,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
                seed=seed,
                stream=stream,
                **token_kw,
            )
            break
        except Exception as e:
            last_err = e
            if attempt < max_retries - 1:
                time.sleep(backoff)
                backoff *= 2

    if response is None:
        raise RuntimeError(
            f"call_llm: exhausted {max_retries} retries for model={model}"
        ) from last_err

    if not stream:
        return response.choices[0].message.content or ""

    return _iter_text_chunks(response)


def _iter_text_chunks(response) -> Iterator[str]:
    for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
