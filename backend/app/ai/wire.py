"""Asking an AI provider, in the language each one speaks.

Every request goes through ``ApiClient`` (see app/integrations/client.py), so it is kept to the
addresses its provider may be at, checks the certificate, never follows a redirect, limits what it
reads and is written to the API log without any secret. This module only knows what to send and
how to read what came back.

What each provider's API takes and answers is from its own documentation:

- Anthropic: POST /v1/messages with ``x-api-key``, ``anthropic-version``, ``model``,
  ``max_tokens``, ``system``, ``messages`` and ``output_config.format`` for a JSON schema; the
  text is in the ``text`` content block and the tokens are ``usage.input_tokens`` and
  ``usage.output_tokens``. (The version header and the usage fields are from the Messages API
  reference; the page on structured outputs does not name them.)
- OpenAI: POST /v1/responses with a bearer key, ``instructions``, ``input``,
  ``max_output_tokens`` and ``text.format`` for a JSON schema; the text is in ``output[]``
  ``message`` items' ``content[]``, a ``refusal`` part says no, and the tokens are
  ``usage.input_tokens`` and ``usage.output_tokens``. ``store: false`` asks not to keep the
  conversation, and ``usage.input_tokens_details.cached_tokens`` is the part that was cached;
  both are from the API reference, not the guide this was read from.
- Ollama: POST /api/chat with ``model``, ``messages``, ``stream: false``, ``format`` (a JSON
  schema) and ``options``; the text is ``message.content`` and the tokens are
  ``prompt_eval_count`` and ``eval_count``. GET /api/tags lists the models, on the computer or,
  with a bearer key, in Ollama's cloud.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeIs, cast

from app.ai.catalog import ProviderDef, Wire
from app.integrations.client import ApiClient, Reply

ANTHROPIC_VERSION = "2023-06-01"
# OpenAI won't take fewer than this many output tokens in a request.
OPENAI_MIN_OUTPUT = 16
MAX_MODELS = 500
MODEL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}$")


class AiFailed(Exception):
    """A provider that couldn't be used. The message says why, for whoever is setting it up, and
    holds nothing the provider said and no secret."""


@dataclass(frozen=True)
class Completion:
    """What a provider answered, and what it counted."""

    text: str
    input_tokens: int
    output_tokens: int
    # Of the input, how many the provider already had cached, and so charged less for.
    cached_tokens: int = 0
    # The answer was cut short because it hit the limit, so it may be incomplete.
    truncated: bool = False


@dataclass(frozen=True)
class FoundModel:
    """A model a provider says it has."""

    name: str
    size: int | None
    family: str | None
    parameters: str | None
    quantization: str | None


def _is_object(value: object) -> TypeIs[dict[str, object]]:
    return isinstance(value, dict)


def _object(value: object) -> dict[str, object]:
    return value if _is_object(value) else {}


def _list(value: object) -> list[object]:
    return cast("list[object]", value) if isinstance(value, list) else []


def _count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def explain(status: int, provider: ProviderDef) -> str:
    """What an answer that isn't a success means, in words for whoever is setting it up."""
    name = provider.label
    if status in (401, 403):
        return (
            f"{name} didn't accept the API key (HTTP {status}). Check that it is the whole key, "
            "that it is switched on and that it may use this model."
        )
    if status == 404:
        if provider.wire is Wire.OLLAMA:
            return "It doesn't have that model. Fetch the models and choose one it has."
        return f"{name} doesn't know that model, or this address. Choose another model."
    if status == 429:
        return f"{name} is limiting requests, or the account is out of credit (HTTP 429)."
    if status in (400, 413, 422):
        return f"{name} didn't accept the request (HTTP {status}). Choose another model."
    if status >= 500:
        return f"{name} had a problem of its own (HTTP {status}). Try again in a moment."
    return f"{name} answered with HTTP {status}, which AresGate didn't expect."


def _request(
    provider: ProviderDef,
    model: str,
    key: str | None,
    system: str,
    prompt: str,
    schema: Mapping[str, object] | None,
    max_tokens: int,
) -> tuple[str, dict[str, str], dict[str, object]]:
    """The path, the headers and the body of a request for an answer."""
    if provider.wire is Wire.ANTHROPIC:
        body: dict[str, object] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }
        if schema is not None:
            body["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
        headers = {"x-api-key": key or "", "anthropic-version": ANTHROPIC_VERSION}
        return "/v1/messages", headers, body
    if provider.wire is Wire.OPENAI:
        body = {
            "model": model,
            "instructions": system,
            "input": prompt,
            "max_output_tokens": max(max_tokens, OPENAI_MIN_OUTPUT),
            "store": False,
        }
        if schema is not None:
            body["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "answer",
                    "strict": True,
                    "schema": schema,
                }
            }
        return "/v1/responses", {"Authorization": f"Bearer {key or ''}"}, body
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0, "num_predict": max_tokens},
    }
    if schema is not None:
        body["format"] = schema
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    return "/api/chat", headers, body


def _anthropic(data: dict[str, object]) -> Completion:
    usage = _object(data.get("usage"))
    blocks = [_object(block) for block in _list(data.get("content"))]
    text = "".join(
        _text(block.get("text")) or "" for block in blocks if block.get("type") == "text"
    )
    stop = data.get("stop_reason")
    if stop == "refusal":
        raise AiFailed("The model declined to answer.")
    return Completion(
        text=text,
        input_tokens=_count(usage.get("input_tokens")),
        output_tokens=_count(usage.get("output_tokens")),
        cached_tokens=_count(usage.get("cache_read_input_tokens")),
        truncated=stop == "max_tokens",
    )


def _openai(data: dict[str, object]) -> Completion:
    if data.get("error"):
        raise AiFailed("The model couldn't answer.")
    usage = _object(data.get("usage"))
    parts = [
        _object(part)
        for item in _list(data.get("output"))
        if _object(item).get("type") == "message"
        for part in _list(_object(item).get("content"))
    ]
    if any(part.get("type") == "refusal" for part in parts):
        raise AiFailed("The model declined to answer.")
    text = "".join(
        _text(part.get("text")) or "" for part in parts if part.get("type") == "output_text"
    )
    incomplete = _object(data.get("incomplete_details")).get("reason") == "max_output_tokens"
    return Completion(
        text=text,
        input_tokens=_count(usage.get("input_tokens")),
        output_tokens=_count(usage.get("output_tokens")),
        cached_tokens=_count(_object(usage.get("input_tokens_details")).get("cached_tokens")),
        truncated=incomplete,
    )


def _ollama(data: dict[str, object]) -> Completion:
    return Completion(
        text=_text(_object(data.get("message")).get("content")) or "",
        input_tokens=_count(data.get("prompt_eval_count")),
        output_tokens=_count(data.get("eval_count")),
        truncated=data.get("done_reason") == "length",
    )


_READERS = {Wire.ANTHROPIC: _anthropic, Wire.OPENAI: _openai, Wire.OLLAMA: _ollama}


def read_completion(provider: ProviderDef, reply: Reply) -> Completion:
    """What came back, or ``AiFailed`` saying why there is no answer."""
    if not reply.ok:
        raise AiFailed(explain(reply.status, provider))
    data = reply.json()
    if not _is_object(data):
        raise AiFailed(f"{provider.label} answered, but not in a form AresGate understands.")
    return _READERS[provider.wire](data)


async def complete(
    client: ApiClient,
    provider: ProviderDef,
    model: str,
    key: str | None,
    *,
    system: str,
    prompt: str,
    schema: Mapping[str, object] | None = None,
    max_tokens: int = 1024,
) -> Completion:
    """Asks a model for an answer. With a JSON ``schema`` the provider is asked to keep to it.
    Raises ``AiFailed``, or ``CallFailed`` when nothing came back."""
    path, headers, body = _request(provider, model, key, system, prompt, schema, max_tokens)
    reply = await client.request("POST", path, json_body=body, headers=headers)
    return read_completion(provider, reply)


def _found(entry: object) -> FoundModel | None:
    item = _object(entry)
    name = _text(item.get("name")) or _text(item.get("model"))
    if name is None or not MODEL_NAME.fullmatch(name):
        return None
    details = _object(item.get("details"))
    size = item.get("size")
    return FoundModel(
        name=name,
        size=size if isinstance(size, int) and not isinstance(size, bool) and size >= 0 else None,
        family=(_text(details.get("family")) or "")[:64] or None,
        parameters=(_text(details.get("parameter_size")) or "")[:32] or None,
        quantization=(_text(details.get("quantization_level")) or "")[:32] or None,
    )


async def list_models(
    client: ApiClient, provider: ProviderDef, key: str | None
) -> list[FoundModel]:
    """The models an Ollama has, installed or in its cloud, by name. Raises ``AiFailed``, or
    ``CallFailed`` when nothing came back."""
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    reply = await client.request("GET", "/api/tags", headers=headers)
    if not reply.ok:
        raise AiFailed(explain(reply.status, provider))
    data = reply.json()
    if not _is_object(data):
        raise AiFailed(f"{provider.label} answered, but not in a form AresGate understands.")
    unique: dict[str, FoundModel] = {}
    for entry in _list(data.get("models"))[:MAX_MODELS]:
        model = _found(entry)
        if model is not None:
            unique.setdefault(model.name, model)
    return sorted(unique.values(), key=lambda model: model.name)
