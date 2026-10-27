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
    # Some models cost more for a long prompt: what it costs from ``long_over`` tokens on.
    long: Price | None = None
    long_over: int = 0

    def cost(self, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> Decimal:
        """What a request cost, in dollars. A request is priced by its own length."""
        rate = self.long if self.long is not None and input_tokens > self.long_over else self
        fresh = max(input_tokens - cached_tokens, 0)
        cached_rate = rate.cached_input if rate.cached_input is not None else rate.input
        return (
            fresh * rate.input + cached_tokens * cached_rate + output_tokens * rate.output
        ) / MILLION


def _price(
    reads: str,
    writes: str,
    cached: str | None = None,
    *,
    long: Price | None = None,
    long_over: int = 0,
) -> Price:
    """A price from what it costs to send a million tokens, to get a million back and to send a
    million that the provider already has cached."""
    return Price(
        Decimal(reads),
        Decimal(writes),
        Decimal(cached) if cached is not None else None,
        long,
        long_over,
    )


@dataclass(frozen=True)
class ModelDef:
    """A model that can be chosen, by the name the provider's API knows it by."""

    id: str
    label: str
    # What it is for, in a few words, so the choice can be made without knowing the names.
    note: str
    price: Price


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
        ModelDef(
            "claude-haiku-5-5",
            "Claude Haiku 5.5",
            "Fast and cheap: a good fit for reading every incident",
            _price(
                "0.10",
                "0.50",
                "0.01",
                long=_price("0.50", "2.50", "0.05"),
                long_over=100_000,
            ),
        ),
        ModelDef(
            "claude-sonnet-5-5",
            "Claude Sonnet 5.5",
            "Better reasoning for harder incidents",
            _price("2", "10", "0.10"),
        ),
        ModelDef(
            "claude-opus-5-5",
            "Claude Opus 5.5",
            "Thorough, for the incidents that matter most",
            _price("4", "20", "0.20"),
        ),
        ModelDef(
            "claude-fable-5-1",
            "Claude Fable 5.1",
            "The most capable, and the most expensive",
            _price("10", "50", "0.25"),
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
        ModelDef(
            "gpt-6-luna",
            "GPT-6 Luna",
            "Fast and cheap: a good fit for reading every incident",
            _price("0.10", "0.50", "0.01"),
        ),
        ModelDef(
            "gpt-5.4-nano",
            "GPT-5.4 nano",
            "Small and cheap, from the previous generation",
            _price("0.20", "1.25", "0.02"),
        ),
        ModelDef(
            "gpt-5.4-mini",
            "GPT-5.4 mini",
            "A little more capable than nano",
            _price("0.75", "4.50", "0.075"),
        ),
        ModelDef(
            "gpt-6.1-terra",
            "GPT-6.1 Terra",
            "Better reasoning for harder incidents",
            _price("1", "5", "0.05"),
        ),
        ModelDef(
            "gpt-6.1-sol",
            "GPT-6.1 Sol",
            "The most capable of these",
            _price("2", "10", "0.10"),
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
