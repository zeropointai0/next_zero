"""
providers.py — ZeroPointAI Provider Normalization Layer

Roll:
  Beskriver, normaliserar och klassificerar AI-providers.

Regler:
  - Denna fil anropar INTE providers
  - Denna fil skriver INTE minnen
  - Denna fil äger INTE routing
  - Ren provider-metadata och hjälpfunktioner

Filosofi:
  Provider är inte identitet.
  Claude, Gemini, Ollama — de är kognitionsytor.
  Zero förblir Zero oavsett provider.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

try:
    from dotenv import load_dotenv
    from app.foundation import ZERO_ROOT
    load_dotenv(ZERO_ROOT / ".env")
except ImportError:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


# ── Provider-spec ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ProviderSpec:
    canonical_name: str
    display_name: str
    is_local: bool
    provider_family: str
    default_model_env: str
    context_limit: int
    budget_warning_threshold_pct: float = 75.0
    tool_capabilities: Set[str] = field(default_factory=frozenset)
    notes: str = ""


# ── Alias-tabell ──────────────────────────────────────────────────────────────

PROVIDER_ALIASES: Dict[str, str] = {
    "claude":      "claude",
    "anthropic":   "claude",
    "mistral":     "mistral",
    "ollama":      "ollama",
    "local":       "ollama",
    "qwen":        "ollama",
    "llama":       "ollama",
    "gemini":      "gemini",
    "google":      "gemini",
    "xai":         "xai",
    "grok":        "xai",
    "deepseek":    "deepseek",
    "groq":        "groq",
    "openrouter":  "openrouter",
    "cerebras":    "cerebras",
    "cohere":      "cohere",
}


# ── Provider-katalog ──────────────────────────────────────────────────────────

PROVIDER_SPECS: Dict[str, ProviderSpec] = {
    "claude": ProviderSpec(
        canonical_name="claude",
        display_name="Claude",
        is_local=False,
        provider_family="anthropic",
        default_model_env="ANTHROPIC_MODEL",
        context_limit=200_000,
        tool_capabilities=frozenset({"native_tools", "json_tools", "vision"}),
        notes="Stark reasoning och tool use. Moln.",
    ),
    "mistral": ProviderSpec(
        canonical_name="mistral",
        display_name="Mistral",
        is_local=False,
        provider_family="mistral",
        default_model_env="MISTRAL_MODEL",
        context_limit=128_000,
        tool_capabilities=frozenset({"json_tools"}),
        notes="Bra generell molnfallback.",
    ),
    "ollama": ProviderSpec(
        canonical_name="ollama",
        display_name="Ollama",
        is_local=True,
        provider_family="ollama",
        default_model_env="OLLAMA_MODEL",
        context_limit=128_000,
        budget_warning_threshold_pct=80.0,
        tool_capabilities=frozenset(),
        notes="Lokal kognitionsyta. Faktisk kontextgräns beror på modell.",
    ),
    "gemini": ProviderSpec(
        canonical_name="gemini",
        display_name="Gemini",
        is_local=False,
        provider_family="google",
        default_model_env="GEMINI_MODEL",
        context_limit=1_000_000,
        budget_warning_threshold_pct=80.0,
        tool_capabilities=frozenset({"vision", "long_context"}),
        notes="Stort kontextfönster. Bra för lång syntes.",
    ),
    "xai": ProviderSpec(
        canonical_name="xai",
        display_name="xAI/Grok",
        is_local=False,
        provider_family="xai",
        default_model_env="XAI_MODEL",
        context_limit=128_000,
        tool_capabilities=frozenset({"json_tools"}),
        notes="Molnprovider.",
    ),
    "deepseek": ProviderSpec(
        canonical_name="deepseek",
        display_name="DeepSeek",
        is_local=False,
        provider_family="deepseek",
        default_model_env="DEEPSEEK_MODEL",
        context_limit=64_000,
        tool_capabilities=frozenset({"json_tools"}),
        notes="Reasoning-fokuserad provider.",
    ),
    "groq": ProviderSpec(
        canonical_name="groq",
        display_name="Groq",
        is_local=False,
        provider_family="groq",
        default_model_env="GROQ_MODEL",
        context_limit=128_000,
        tool_capabilities=frozenset({"json_tools", "fast_inference"}),
        notes="Mycket snabb inferens.",
    ),
    "openrouter": ProviderSpec(
        canonical_name="openrouter",
        display_name="OpenRouter",
        is_local=False,
        provider_family="openrouter",
        default_model_env="OPENROUTER_MODEL",
        context_limit=128_000,
        tool_capabilities=frozenset({"model_gateway"}),
        notes="Gateway — faktiska capabilities beror på routad modell.",
    ),
    "cerebras": ProviderSpec(
        canonical_name="cerebras",
        display_name="Cerebras",
        is_local=False,
        provider_family="cerebras",
        default_model_env="CEREBRAS_MODEL",
        context_limit=128_000,
        tool_capabilities=frozenset({"fast_inference"}),
        notes="Snabb molninferens.",
    ),
    "cohere": ProviderSpec(
        canonical_name="cohere",
        display_name="Cohere",
        is_local=False,
        provider_family="cohere",
        default_model_env="COHERE_MODEL",
        context_limit=128_000,
        tool_capabilities=frozenset({"json_tools"}),
        notes="Molnprovider.",
    ),
}

# Prioritetsordning för lokal-först-strategi
LOCAL_FIRST_ORDER: List[str] = [
    "ollama", "deepseek", "groq", "cerebras",
    "mistral", "openrouter", "gemini", "claude", "cohere", "xai",
]


# ── Hjälpfunktioner ───────────────────────────────────────────────────────────

def normalize_provider_name(name: Optional[str]) -> str:
    raw = (name or os.getenv("DEFAULT_PROVIDER", "gemini")).strip().lower()
    return PROVIDER_ALIASES.get(raw, raw)


def provider_exists(name: Optional[str]) -> bool:
    return normalize_provider_name(name) in PROVIDER_SPECS


def get_provider_spec(name: Optional[str]) -> ProviderSpec:
    canonical = normalize_provider_name(name)
    return PROVIDER_SPECS.get(canonical, PROVIDER_SPECS["mistral"])


def get_provider_display_name(name: Optional[str]) -> str:
    return get_provider_spec(name).display_name


def get_provider_model(name: Optional[str]) -> str:
    spec = get_provider_spec(name)
    return os.getenv(spec.default_model_env, "").strip()


def get_context_limit_for_provider(name: Optional[str]) -> int:
    return get_provider_spec(name).context_limit


def provider_is_local(name: Optional[str]) -> bool:
    return get_provider_spec(name).is_local


def provider_supports_tool_use(name: Optional[str]) -> bool:
    spec = get_provider_spec(name)
    return bool(spec.tool_capabilities.intersection(
        {"native_tools", "json_tools", "function_calling"}
    ))


def provider_has_capability(name: Optional[str], capability: str) -> bool:
    return capability in get_provider_spec(name).tool_capabilities


def list_provider_names() -> List[str]:
    return list(PROVIDER_SPECS.keys())


def get_local_first_order() -> List[str]:
    return [p for p in LOCAL_FIRST_ORDER if p in PROVIDER_SPECS]


def choose_default_provider(local_first: bool = False) -> str:
    if local_first and os.getenv("OLLAMA_MODEL", "").strip():
        return "ollama"
    return normalize_provider_name(os.getenv("DEFAULT_PROVIDER", "gemini"))


def choose_reflection_provider() -> str:
    explicit = os.getenv("ZERO_REFLECTION_PROVIDER", "").strip()
    if explicit:
        return normalize_provider_name(explicit)
    if os.getenv("OLLAMA_MODEL", "").strip():
        return "ollama"
    return normalize_provider_name(os.getenv("DEFAULT_PROVIDER", "gemini"))


def choose_docs_provider() -> str:
    explicit = os.getenv("DOC_PROVIDER", "").strip()
    if explicit:
        return normalize_provider_name(explicit)
    if os.getenv("OLLAMA_MODEL", "").strip():
        return "ollama"
    return normalize_provider_name(os.getenv("DEFAULT_PROVIDER", "gemini"))


def build_budget_warning(provider: Optional[str], usage: Optional[dict]) -> str:
    """Returnerar human-readable budgetvarning om relevant."""
    if not usage:
        return ""
    spec   = get_provider_spec(provider)
    total  = int(usage.get("total", 0) or 0)
    budget = int(usage.get("budget", 0) or 0)
    if budget <= 0:
        return ""
    pct = (total / budget) * 100
    warnings: List[str] = []
    if pct >= spec.budget_warning_threshold_pct:
        warnings.append(
            f"Budgetläge: {spec.display_name} använder ca {pct:.1f}% av kontextbudgeten."
        )
    truncated = usage.get("truncated", []) or []
    if truncated:
        warnings.append(f"Kontext trunkerad: {', '.join(str(x) for x in truncated)}")
    if not provider_supports_tool_use(provider):
        warnings.append(
            f"{spec.display_name} kör utan tool-use i nuvarande läge."
        )
    return " ".join(warnings)


def get_provider_runtime_summary(name: Optional[str]) -> dict:
    """Strukturerad provider-metadata för diagnostik och API-endpoints."""
    spec  = get_provider_spec(name)
    model = get_provider_model(spec.canonical_name)
    return {
        "canonical_name":               spec.canonical_name,
        "display_name":                 spec.display_name,
        "provider_family":              spec.provider_family,
        "model":                        model or None,
        "is_local":                     spec.is_local,
        "context_limit":                spec.context_limit,
        "budget_warning_threshold_pct": spec.budget_warning_threshold_pct,
        "tool_capabilities":            sorted(spec.tool_capabilities),
        "supports_tool_use":            provider_supports_tool_use(spec.canonical_name),
        "notes":                        spec.notes,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== ZeroPointAI Providers ===\n")
    for name, spec in PROVIDER_SPECS.items():
        model = get_provider_model(name)
        local = "lokal" if spec.is_local else "moln"
        print(f"  {spec.display_name:12s} [{local}]  model={model or '(ej konfigurerad)'}")
    print(f"\nDefault: {choose_default_provider()}")
    print(f"Reflection: {choose_reflection_provider()}")
