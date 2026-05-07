"""Provider registry — maps the `provider:` key in models.yaml to a class.

To add a new provider: implement LLMProvider in a new module and add it here.
"""

from .anthropic import AnthropicProvider
from .null import NullProvider
from .ollama import OllamaProvider
from .openai_compat import OpenAICompatProvider

# `openai_compat` is the canonical name. The aliases let models.yaml use intuitive
# `provider: openai` / `provider: xai` keys without needing separate classes — the
# class is identical; only the api_key_env / base_url in each model entry differ.
PROVIDERS = {
    "anthropic": AnthropicProvider,
    "ollama": OllamaProvider,
    "null": NullProvider,
    "openai_compat": OpenAICompatProvider,
    "openai": OpenAICompatProvider,
    "xai": OpenAICompatProvider,
}
