"""Node -> provider resolution.

Nodes call ``router.for_node("planner")``.  They never construct a chat model
themselves, which is what makes "Normalizer on Qwen, Planner on OpenAI"
a configuration change rather than a code change.
"""

from __future__ import annotations

from triptailor_ai.config.settings import NODE_KEYS, ProviderName, Settings, get_settings
from triptailor_ai.exceptions import ConfigurationError
from triptailor_ai.providers.base import ModelProvider
from triptailor_ai.providers.fake_provider import FakeModelProvider


class ModelRouter:
    """Builds and caches one provider instance per ``(provider, model)`` pair."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        overrides: dict[str, ModelProvider] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        #: Explicit per-node instances; bypass settings entirely (used in tests).
        self._overrides: dict[str, ModelProvider] = dict(overrides or {})
        self._cache: dict[tuple[str, str | None], ModelProvider] = {}

    # ---- construction helpers -------------------------------------------
    @classmethod
    def fake(
        cls, provider: FakeModelProvider | None = None, settings: Settings | None = None
    ) -> "ModelRouter":
        """A router whose every node resolves to one shared fake provider."""

        shared = provider or FakeModelProvider()
        return cls(
            settings=settings or Settings(default_llm_provider=ProviderName.FAKE),
            overrides={key: shared for key in NODE_KEYS},
        )

    def override(self, node_key: str, provider: ModelProvider) -> "ModelRouter":
        Settings._assert_known_node(node_key)
        self._overrides[node_key] = provider
        return self

    # ---- resolution ------------------------------------------------------
    def for_node(self, node_key: str) -> ModelProvider:
        if node_key in self._overrides:
            return self._overrides[node_key]

        provider_name = self.settings.provider_for(node_key)
        model = self.settings.model_for(node_key)
        cache_key = (provider_name.value, model)
        if cache_key not in self._cache:
            self._cache[cache_key] = self._build(provider_name, model)
        return self._cache[cache_key]

    def _build(self, provider_name: ProviderName, model: str | None) -> ModelProvider:
        if provider_name is ProviderName.FAKE:
            return FakeModelProvider(
                model=model or "fake-1", max_retries=self.settings.max_llm_retries
            )
        if provider_name is ProviderName.OPENAI:
            from triptailor_ai.providers.openai_provider import OpenAIProvider

            return OpenAIProvider(settings=self.settings, model=model)
        if provider_name is ProviderName.QWEN:
            from triptailor_ai.providers.qwen_provider import QwenProvider

            return QwenProvider(settings=self.settings, model=model)
        raise ConfigurationError(f"unsupported provider: {provider_name}")

    # ---- introspection ---------------------------------------------------
    def provider_map(self) -> dict[str, str]:
        """``{node: "provider:model"}`` for generation metadata and evaluation."""

        mapping: dict[str, str] = {}
        for key in NODE_KEYS:
            provider = self.for_node(key)
            mapping[key] = f"{provider.name}:{provider.model}"
        return mapping

    async def aclose(self) -> None:
        for provider in {id(p): p for p in self._cache.values()}.values():
            await provider.aclose()
