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
  reference; the page on structured outputs does not name them.) To cache the fixed start of a
  prompt, ``cache_control: {"type": "ephemeral"}`` goes on the last block of ``system``; it is kept
  for five minutes. ``usage.input_tokens`` then counts only what comes after the cached part, so
  the whole is that plus ``usage.cache_read_input_tokens`` (read from the cache) plus
  ``usage.cache_creation_input_tokens`` (written to it). From the prompt caching page.
- OpenAI: POST /v1/responses with a bearer key, ``instructions``, ``input``,
  ``max_output_tokens`` and ``text.format`` for a JSON schema; the text is in ``output[]``
  ``message`` items' ``content[]``, a ``refusal`` part says no, and the tokens are
  ``usage.input_tokens`` and ``usage.output_tokens``. ``store: false`` asks not to keep the
  conversation, and ``usage.input_tokens_details.cached_tokens`` is the part that was cached;
  both are from the API reference, not the guide this was read from. The GPT-6 models think
  first, ``reasoning.effort`` says how much, and the thinking counts against
  ``max_output_tokens`` (an answer that runs out before it says anything has ``status:
  incomplete``) and is counted in ``usage.output_tokens_details.reasoning_tokens``, which is part
  of ``usage.output_tokens``. From the reasoning guide.
- OpenAI caching, from the prompt caching guide. The GPT-6 models take
  ``prompt_cache_options: {"mode": "explicit", "ttl": "30m"}`` and a ``prompt_cache_breakpoint:
  {"mode": "explicit"}`` on the ``input_text`` block that ends the fixed part of a prompt, which
  has to be in a ``developer`` message because top-level ``instructions`` can't carry one. What
  comes after it isn't cached and costs no write. ``usage.input_tokens_details`` counts
  ``cached_tokens`` (reads) and ``cache_write_tokens`` (writes), both part of
  ``usage.input_tokens``. The earlier models (GPT-5.4 mini and nano) only cache by themselves,
  charge nothing to write and are helped by a ``prompt_cache_key``.
- Ollama: POST /api/chat with ``model``, ``messages``, ``stream: false``, ``format`` (a JSON
  schema) and ``options``; the text is ``message.content`` and the tokens are
  ``prompt_eval_count`` and ``eval_count``. GET /api/tags lists the models, on the computer or,
  with a bearer key, in Ollama's cloud.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeIs, cast

from app.ai.catalog import Caching, ModelDef, ProviderDef, Wire
from app.integrations.client import ApiClient, Reply

ANTHROPIC_VERSION = "2023-06-01"
# OpenAI won't take fewer than this many output tokens in a request.
OPENAI_MIN_OUTPUT = 16
# A rule of thumb for how many characters a token is, to tell whether a prompt is long enough for
# a provider to cache. Neither provider says what happens to a mark on a start that is too short
# except that it isn't cached, so a start that may be too short isn't marked.
CHARS_PER_TOKEN = 4
MAX_MODELS = 500
MODEL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}$")


class AiFailed(Exception):
    """A provider that couldn't be used. The message says why, for whoever is setting it up, and
    holds nothing the provider said and no secret."""


@dataclass(frozen=True)
class Completion:
    """What a provider answered, and what it counted."""

    text: str
    # Everything sent, the cached and the written included.
    input_tokens: int
    # Everything answered, the thinking included.
    output_tokens: int
    # Of the input, how many the provider already had cached, and so charged less for.
    cached_tokens: int = 0
    # Of the input, how many it kept for next time, which costs a little more.
    cache_write_tokens: int = 0
    # Of the output, how many were thinking before the answer.
    reasoning_tokens: int = 0
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


def _marks(model: ModelDef | None, system: str) -> bool:
    """Whether to mark the end of the fixed part of the prompt for the provider to cache: for a
    model that is asked to, when that part is long enough for a provider to keep."""
    return (
        model is not None
        and model.caching is Caching.MARKED
        and len(system) // CHARS_PER_TOKEN >= model.cache_min_tokens
    )


def _openai_body(
    model: str, known: ModelDef | None, system: str, prompt: str, max_tokens: int
) -> dict[str, object]:
    """What a request to OpenAI says about the model and what is asked, without the schema."""
    allowance = known.thinking_allowance if known is not None else 0
    body: dict[str, object] = {
        "model": model,
        "max_output_tokens": max(max_tokens + allowance, OPENAI_MIN_OUTPUT),
        "store": False,
    }
    if known is not None and known.effort is not None:
        body["reasoning"] = {"effort": known.effort}
    if known is not None and _marks(known, system):
        # Top-level instructions can't carry a breakpoint, so the fixed start goes first in the
        # input, ended by one. What follows it is read at the plain rate and not written.
        body["prompt_cache_options"] = {"mode": "explicit", "ttl": f"{known.cache_minutes}m"}
        breakpoint_block = {
            "type": "input_text",
            "text": system,
            "prompt_cache_breakpoint": {"mode": "explicit"},
        }
        body["input"] = [
            {"role": "developer", "content": [breakpoint_block]},
            {"role": "user", "content": prompt},
        ]
    else:
        body["instructions"] = system
        body["input"] = prompt
    return body


def _request(
    provider: ProviderDef,
    model: str,
    key: str | None,
    system: str,
    prompt: str,
    schema: Mapping[str, object] | None,
    max_tokens: int,
    cache_key: str | None,
) -> tuple[str, dict[str, str], dict[str, object]]:
    """The path, the headers and the body of a request for an answer. ``system`` is the fixed
    start of the prompt, which is what is cached, and ``prompt`` is what changes from one request
    to the next."""
    known = provider.model(model)
    if provider.wire is Wire.ANTHROPIC:
        body: dict[str, object] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }
        if _marks(known, system):
            body["system"] = [
                {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
            ]
        if schema is not None:
            body["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
        headers = {"x-api-key": key or "", "anthropic-version": ANTHROPIC_VERSION}
        return "/v1/messages", headers, body
    if provider.wire is Wire.OPENAI:
        body = _openai_body(model, known, system, prompt, max_tokens)
        if known is not None and known.caching is Caching.AUTOMATIC and cache_key:
            body["prompt_cache_key"] = cache_key
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
    read = _count(usage.get("cache_read_input_tokens"))
    written = _count(usage.get("cache_creation_input_tokens"))
    return Completion(
        text=text,
        # Anthropic counts only what comes after the cached part as input.
        input_tokens=_count(usage.get("input_tokens")) + read + written,
        output_tokens=_count(usage.get("output_tokens")),
        cached_tokens=read,
        cache_write_tokens=written,
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
    input_details = _object(usage.get("input_tokens_details"))
    return Completion(
        text=text,
        input_tokens=_count(usage.get("input_tokens")),
        output_tokens=_count(usage.get("output_tokens")),
        cached_tokens=_count(input_details.get("cached_tokens")),
        cache_write_tokens=_count(input_details.get("cache_write_tokens")),
        reasoning_tokens=_count(
            _object(usage.get("output_tokens_details")).get("reasoning_tokens")
        ),
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
    cache_key: str | None = None,
) -> Completion:
    """Asks a model for an answer. With a JSON ``schema`` the provider is asked to keep to it.
    ``system`` is the start of the prompt that is the same every time: a model that caches is told
    where it ends, and one that does by itself (``cache_key`` helps it find the last request's)
    caches it when it is long enough. Raises ``AiFailed``, or ``CallFailed`` when nothing came
    back."""
    path, headers, body = _request(
        provider, model, key, system, prompt, schema, max_tokens, cache_key
    )
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
