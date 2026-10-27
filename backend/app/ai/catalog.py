"""The AI providers AresGate knows, the models each offers and what they cost.

Prices are in US dollars per million tokens, copied from each provider's own pricing page on the
date given in ``PRICES_AS_OF``. They are a snapshot: providers change prices, so every page that
shows a cost says where the price came from and when it was read, and the figures are for one
file to keep up to date. A provider that is not paid by the token (a model on the owner's own
computer, or Ollama's cloud, which is a subscription) has no price, and costs nothing here.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

# When the prices below were read from the providers' pages.
PRICES_AS_OF = "2026-10-27"

MILLION = Decimal(1_000_000)


class Wire(StrEnum):
    """How a provider is spoken to: the three APIs AresGate knows."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"


class Kind(StrEnum):
    """Where a provider is: the internet, the owner's own computer, or Ollama's cloud."""

    HOSTED = "hosted"
    LOCAL = "local"
    CLOUD = "cloud"


@dataclass(frozen=True)
class Price:
    """What a model costs, per million tokens."""

    input: Decimal
    output: Decimal
    # Input that was already cached by the provider costs less. None where it can't be.
    cached_input: Decimal | None = None
    # Input that is being cached costs more than input that isn't, for the lifetime AresGate asks
    # the provider to keep it. None where writing to the cache is free.
    cache_write: Decimal | None = None
    # Some models cost more for a long prompt: what it costs from ``long_over`` tokens on.
    long: Price | None = None
    long_over: int = 0

    def cost(
        self,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0,
        written_tokens: int = 0,
    ) -> Decimal:
        """What a request cost, in dollars. ``input_tokens`` is everything sent, the cached and
        the written included, and a request is priced by its own length."""
        rate = self.long if self.long is not None and input_tokens > self.long_over else self
        fresh = max(input_tokens - cached_tokens - written_tokens, 0)
        cached_rate = rate.cached_input if rate.cached_input is not None else rate.input
        write_rate = rate.cache_write if rate.cache_write is not None else rate.input
        return (
            fresh * rate.input
            + cached_tokens * cached_rate
            + written_tokens * write_rate
            + output_tokens * rate.output
        ) / MILLION


def _price(
    sent: str,
    received: str,
    cached: str | None = None,
    written: str | None = None,
    *,
    long: Price | None = None,
    long_over: int = 0,
) -> Price:
    """A price from what it costs to send a million tokens, to get a million back, to send a
    million that the provider already has cached and to send a million for it to cache."""
    return Price(
        Decimal(sent),
        Decimal(received),
        Decimal(cached) if cached is not None else None,
        Decimal(written) if written is not None else None,
        long,
        long_over,
    )


class Caching(StrEnum):
    """How a model keeps the start of a prompt it has already read, so that asking again with the
    same start costs less and is quicker."""

    # It can't, or AresGate doesn't use it.
    NONE = "none"
    # The provider does it by itself for a long enough start, and writing to the cache is free.
    AUTOMATIC = "automatic"
    # AresGate marks where the fixed part of a prompt ends, and the provider keeps that part for
    # a while. Reading it back is cheap, and writing it costs a little more than not caching.
    MARKED = "marked"


@dataclass(frozen=True)
class ModelDef:
    """A model that can be chosen, by the name the provider's API knows it by."""

    id: str
    label: str
    # What it is for, in a few words, so the choice can be made without knowing the names.
    note: str
    price: Price
    caching: Caching = Caching.NONE
    # The shortest start of a prompt that the provider will cache, in tokens.
    cache_min_tokens: int = 0
    # How long the provider keeps what AresGate asked it to cache, in minutes.
    cache_minutes: int = 0
    # How hard it thinks before it answers, for a model that does. None is the model's own choice.
    effort: str | None = None
    # A model that thinks counts it against the tokens it may answer with, so it is given this
    # many more than the answer needs.
    thinking_allowance: int = 0
    # The provider says it will retire it.
    deprecated: bool = False


@dataclass(frozen=True)
class ProviderDef:
    key: str
    label: str
    summary: str
    wire: Wire
    kind: Kind
    # Where a hosted provider is. The others are wherever the owner says (local) or ollama.com.
    origin: str | None
    # Whether it takes an API key, and where a key is made.
    needs_key: bool
    key_url: str | None
    # Where the models and their prices are published, and what AresGate sends to read the
    # list of models, for the providers that have none fixed.
    pricing_url: str | None
    models_url: str
    # The models it offers. Empty for a provider whose models are whatever is installed.
    models: tuple[ModelDef, ...]
    default_model: str | None

    def model(self, model_id: str) -> ModelDef | None:
        return next((model for model in self.models if model.id == model_id), None)

    @property
    def fixed_models(self) -> bool:
        """Whether the choice is among the models listed, rather than any it has."""
        return bool(self.models)


# OpenAI prices a prompt of more than this many tokens at the long-prompt rates.
OPENAI_LONG_OVER = 272_000


def _claude(model_id: str, label: str, note: str, price: Price) -> ModelDef:
    """A Claude model. AresGate marks the fixed part of a prompt, which Anthropic keeps for five
    minutes unless it is told longer, from 512 tokens. A shorter prompt isn't cached, and nothing
    says so but the counts in the answer."""
    return ModelDef(
        model_id,
        label,
        note,
        price,
        caching=Caching.MARKED,
        cache_min_tokens=512,
        cache_minutes=5,
    )


def _gpt6(model_id: str, label: str, note: str, price: Price) -> ModelDef:
    """A GPT-6 model. AresGate marks the fixed part of a prompt, which OpenAI keeps for 30 minutes
    from 1,024 tokens. They think before they answer, so they are asked to think a little (every
    one takes "low", and some can't be asked not to think at all) and are given room for it."""
    return ModelDef(
        model_id,
        label,
        note,
        price,
        caching=Caching.MARKED,
        cache_min_tokens=1024,
        cache_minutes=30,
        effort="low",
        thinking_allowance=4096,
    )


ANTHROPIC = ProviderDef(
    key="anthropic",
    label="Anthropic",
    summary="Claude models, asked over the internet with an API key.",
    wire=Wire.ANTHROPIC,
    kind=Kind.HOSTED,
    origin="https://api.anthropic.com",
    needs_key=True,
    key_url="https://platform.claude.com/settings/keys",
    pricing_url="https://platform.claude.com/docs/en/about-claude/pricing",
    models_url="https://platform.claude.com/docs/en/about-claude/models/overview",
    models=(
        _claude(
            "claude-haiku-5-5",
            "Claude Haiku 5.5",
            "Fast and cheap: a good fit for reading every incident",
            _price(
                "0.10",
                "0.50",
                "0.01",
                "0.125",
                long=_price("0.50", "2.50", "0.05", "0.625"),
                long_over=100_000,
            ),
        ),
        _claude(
            "claude-sonnet-5-5",
            "Claude Sonnet 5.5",
            "Better reasoning for harder incidents",
            _price("2", "10", "0.10", "2.50"),
        ),
        _claude(
            "claude-opus-5-5",
            "Claude Opus 5.5",
            "Thorough, for the incidents that matter most",
            _price("4", "20", "0.20", "5"),
        ),
        _claude(
            "claude-fable-5-1",
            "Claude Fable 5.1",
            "The most capable, and the most expensive",
            _price("10", "50", "0.25", "12.50"),
        ),
    ),
    default_model="claude-haiku-5-5",
)

OPENAI = ProviderDef(
    key="openai",
    label="OpenAI",
    summary="GPT models, asked over the internet with an API key.",
    wire=Wire.OPENAI,
    kind=Kind.HOSTED,
    origin="https://api.openai.com",
    needs_key=True,
    key_url="https://platform.openai.com/api-keys",
    pricing_url="https://developers.openai.com/api/docs/pricing",
    models_url="https://developers.openai.com/api/docs/models",
    models=(
        _gpt6(
            "gpt-6-luna",
            "GPT-6 Luna",
            "Fast and cheap: a good fit for reading every incident",
            _price(
                "0.10",
                "0.50",
                "0.01",
                "0.125",
                long=_price("0.20", "0.75", "0.02", "0.25"),
                long_over=OPENAI_LONG_OVER,
            ),
        ),
        ModelDef(
            "gpt-5.4-nano",
            "GPT-5.4 nano",
            "Small and cheap, from the previous generation. OpenAI lists it as deprecated",
            _price("0.20", "1.25", "0.02"),
            caching=Caching.AUTOMATIC,
            deprecated=True,
        ),
        ModelDef(
            "gpt-5.4-mini",
            "GPT-5.4 mini",
            "A little more capable than nano, from the previous generation",
            _price("0.75", "4.50", "0.075"),
            caching=Caching.AUTOMATIC,
        ),
        _gpt6(
            "gpt-6.1-terra",
            "GPT-6.1 Terra",
            "Better reasoning for harder incidents",
            _price(
                "1",
                "5",
                "0.05",
                "1.25",
                long=_price("2", "7.50", "0.10", "2.50"),
                long_over=OPENAI_LONG_OVER,
            ),
        ),
        _gpt6(
            "gpt-6.1-sol",
            "GPT-6.1 Sol",
            "Close to Astra for complex incidents, at a fifth of the price",
            _price(
                "2",
                "10",
                "0.10",
                "2.50",
                long=_price("4", "15", "0.20", "5"),
                long_over=OPENAI_LONG_OVER,
            ),
        ),
        _gpt6(
            "gpt-6-astra",
            "GPT-6 Astra",
            "OpenAI's most capable, and the most expensive of these",
            _price(
                "10",
                "50",
                "1.00",
                "12.50",
                long=_price("20", "75", "2", "25"),
                long_over=OPENAI_LONG_OVER,
            ),
        ),
    ),
    default_model="gpt-6-luna",
)

OLLAMA = ProviderDef(
    key="ollama",
    label="Ollama (your computer)",
    summary=(
        "Models that run on a computer of your own, so nothing leaves your network and it "
        "costs nothing to ask."
    ),
    wire=Wire.OLLAMA,
    kind=Kind.LOCAL,
    origin=None,
    needs_key=False,
    key_url=None,
    pricing_url=None,
    models_url="https://docs.ollama.com/api/tags",
    models=(),
    default_model=None,
)

OLLAMA_CLOUD = ProviderDef(
    key="ollama_cloud",
    label="Ollama Cloud",
    summary="Models that Ollama runs for you, asked over the internet with an API key.",
    wire=Wire.OLLAMA,
    kind=Kind.CLOUD,
    origin="https://ollama.com",
    needs_key=True,
    key_url="https://ollama.com/settings/keys",
    pricing_url=None,
    models_url="https://docs.ollama.com/cloud",
    models=(),
    default_model=None,
)

PROVIDERS: tuple[ProviderDef, ...] = (ANTHROPIC, OPENAI, OLLAMA, OLLAMA_CLOUD)
BY_KEY: dict[str, ProviderDef] = {provider.key: provider for provider in PROVIDERS}


def provider(key: str) -> ProviderDef | None:
    return BY_KEY.get(key)
