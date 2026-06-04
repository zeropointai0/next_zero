#!/usr/bin/env python3
"""
zero_ascension_setup.py — Interaktiv Setup-wizard för Zero Ascension

ZERO_MODULE:    core
ZERO_LAYER:     1
ZERO_ESSENTIAL: true
ZERO_ROLE:      Interaktiv wizard för att sätta upp en ny Zero-generation
ZERO_DEPENDS:   foundation.py, zero_ascension.py
ZERO_USED_BY:   Frank (manuellt)

Kör: python3 zero_ascension_setup.py
"""

from __future__ import annotations

import os
import sys
import json
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Dict, Tuple

# ── Färger ────────────────────────────────────────────────────────────────────

class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    DIM    = "\033[2m"
    ACCENT = "\033[95m"

def ok(msg):    print(f"  {C.GREEN}✓{C.RESET} {msg}")
def warn(msg):  print(f"  {C.YELLOW}⚠{C.RESET}  {msg}")
def err(msg):   print(f"  {C.RED}✗{C.RESET} {msg}")
def info(msg):  print(f"  {C.CYAN}ℹ{C.RESET}  {msg}")
def step(n, total, title):
    print(f"\n{C.BOLD}{C.ACCENT}Steg {n}/{total} — {title}{C.RESET}")
    print(f"  {'─' * 50}")

def header():
    print(f"\n{C.BOLD}{C.ACCENT}{'═' * 55}")
    print(f"  ZERO ASCENSION — Interaktiv Setup")
    print(f"  Föder en ny Zero-generation från grunden")
    print(f"{'═' * 55}{C.RESET}\n")

def ask(prompt, default=None) -> str:
    if default:
        full = f"  {C.BOLD}{prompt}{C.RESET} [{C.DIM}{default}{C.RESET}]: "
    else:
        full = f"  {C.BOLD}{prompt}{C.RESET}: "
    try:
        val = input(full).strip()
        return val if val else (default or "")
    except (KeyboardInterrupt, EOFError):
        print(f"\n\n  Avbrutet av användaren.")
        sys.exit(0)

def ask_yn(prompt, default="j") -> bool:
    opts = "J/n" if default == "j" else "j/N"
    try:
        val = input(f"  {C.BOLD}{prompt}{C.RESET} ({opts}): ").strip().lower()
        if not val:
            return default == "j"
        return val in ("j", "ja", "y", "yes")
    except (KeyboardInterrupt, EOFError):
        print(f"\n\n  Avbrutet.")
        sys.exit(0)

def ask_choice(prompt, options: list, default=1) -> int:
    for i, opt in enumerate(options, 1):
        marker = f"{C.GREEN}→{C.RESET}" if i == default else " "
        print(f"  {marker} [{i}] {opt}")
    try:
        val = input(f"\n  {C.BOLD}{prompt}{C.RESET} [{default}]: ").strip()
        if not val:
            return default
        n = int(val)
        if 1 <= n <= len(options):
            return n
        return default
    except (ValueError, KeyboardInterrupt, EOFError):
        return default

def pause():
    try:
        input(f"\n  {C.DIM}Tryck Enter för att fortsätta...{C.RESET}")
    except (KeyboardInterrupt, EOFError):
        sys.exit(0)


# ── ENV-parsning ──────────────────────────────────────────────────────────────

# Kategorier för .env-nycklar
ENV_CATEGORIES = {
    "providers": {
        "label": "AI Providers",
        "keys": [
            "DEFAULT_PROVIDER",
            "GEMINI_API_KEY", "GEMINI_MODEL",
            "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL",
            "MISTRAL_API_KEY", "MISTRAL_MODEL",
            "GROQ_API_KEY", "GROQ_MODEL",
            "XAI_API_KEY", "XAI_MODEL",
            "DEEPSEEK_API_KEY", "DEEPSEEK_MODEL",
            "OPENROUTER_API_KEY", "OPENROUTER_MODEL",
            "CEREBRAS_API_KEY", "CEREBRAS_MODEL",
            "COHERE_API_KEY", "COHERE_MODEL",
        ],
    },
    "ollama": {
        "label": "Ollama (lokal AI)",
        "keys": ["OLLAMA_HOST", "OLLAMA_MODEL", "EMBEDDING_MODEL", "ST_EMBEDDING_MODEL"],
    },
    "database": {
        "label": "Databas",
        "keys": ["POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"],
    },
    "mail": {
        "label": "E-post",
        "keys": ["MAIL_SERVER", "MAIL_PORT", "MAIL_USER", "MAIL_PASSWORD",
                 "MAIL_FROM", "MAIL_TO", "IMAP_SERVER", "IMAP_PORT",
                 "IMAP_USER", "IMAP_PASSWORD", "SMTP_SERVER", "SMTP_PORT"],
    },
    "telegram": {
        "label": "Telegram",
        "keys": ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TELEGRAM_ALLOWED_USERS"],
    },
    "pinball": {
        "label": "Pinball inn",
        "keys": ["WORDPRESS_URL", "WORDPRESS_KEY", "PINBALL_DB_URL",
                 "META_ACCESS_TOKEN", "INSTAGRAM_ACCOUNT_ID",
                 "FACEBOOK_PAGE_ID", "TIKTOK_ACCESS_TOKEN"],
    },
    "system": {
        "label": "System",
        "keys": ["ZERO_ROOT", "UI_PORT", "LOG_LEVEL", "USD_TO_SEK",
                 "ZERO_GEAR_OVERRIDE", "ZERO_GEAR_OLLAMA_LATENCY_THRESHOLD_MS",
                 "ZERO_REFLECTION_PROVIDER", "DOC_PROVIDER"],
    },
    "runtime": {
        "label": "Runtime (ej ärvd)",
        "keys": ["SESSION_ID", "RUNTIME_ID", "TEMP_", "CURRENT_SESSION"],
        "skip": True,  # Ska aldrig ärvas
    },
}

KNOWN_NEW_PROVIDERS = [
    ("OPENAI_API_KEY", "OPENAI_MODEL", "OpenAI (GPT-4 etc.)"),
    ("TOGETHER_API_KEY", "TOGETHER_MODEL", "Together AI"),
    ("FIREWORKS_API_KEY", "FIREWORKS_MODEL", "Fireworks AI"),
    ("PERPLEXITY_API_KEY", "PERPLEXITY_MODEL", "Perplexity"),
]


def parse_env_file(path: Path) -> Dict[str, str]:
    result = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        result[key.strip()] = val.strip()
    return result


def mask(val: str) -> str:
    if not val or len(val) < 8:
        return "***"
    return val[:4] + "..." + val[-3:]


def is_key_configured(key: str, env: Dict) -> bool:
    val = env.get(key, "")
    return bool(val and "your_" not in val.lower() and val != "")


# ── Setup-wizard ──────────────────────────────────────────────────────────────

def run_wizard():
    header()

    # ── Hitta v1 ─────────────────────────────────────────────────────────────
    default_v1 = "/opt/zeropointai"
    v1_root = Path(ask("Sökväg till nuvarande Zero (v1)", default_v1))
    if not v1_root.exists():
        err(f"Hittar inte {v1_root}")
        sys.exit(1)

    v1_env_path = v1_root / ".env"
    if not v1_env_path.exists():
        err(f".env saknas i {v1_root}")
        sys.exit(1)

    v1_env = parse_env_file(v1_env_path)
    ok(f"v1 hittad: {v1_root}")

    # ── Ny generation ─────────────────────────────────────────────────────────
    default_new = str(v1_root.parent / "next_zero")
    new_root = Path(ask("Sökväg till ny generation", default_new))
    label    = ask("Namn på nya generationen", "Zero v2")
    port     = ask("HTTP-port", "8081")
    db_name  = ask("Databasnamn", "zeropointai_v2")

    print()

    # ── Lösenord ──────────────────────────────────────────────────────────────
    step(1, 6, "Databas & lösenord")

    v1_password = v1_env.get("POSTGRES_PASSWORD", "")
    v1_db       = v1_env.get("POSTGRES_DB", "zeropointai")

    if v1_password:
        info(f"Hittade lösenord i v1 (.env): {mask(v1_password)}")
        info(f"v1 databas: {v1_db} → ny databas: {db_name}")
        print()
        choice = ask_choice(
            "Välj lösenord för nya databasen:",
            [
                f"Samma lösenord som v1 (rekommenderat — samma PostgreSQL-server)",
                "Välj nytt lösenord",
            ]
        )
        if choice == 1:
            new_password = v1_password
            ok("Använder samma lösenord")
        else:
            new_password = ask("Nytt lösenord")
            ok("Nytt lösenord valt")
    else:
        warn("Inget lösenord hittades i v1:s .env")
        new_password = ask("Ange lösenord för PostgreSQL")

    # ── Providers ─────────────────────────────────────────────────────────────
    step(2, 6, "AI Providers")

    new_env: Dict[str, str] = {}
    skipped_keys = set()

    # Visa konfigurerade providers
    configured_providers = []
    unconfigured_providers = []

    provider_key_groups = [
        ("Gemini",      "GEMINI_API_KEY",      "GEMINI_MODEL"),
        ("Claude",      "ANTHROPIC_API_KEY",   "ANTHROPIC_MODEL"),
        ("Mistral",     "MISTRAL_API_KEY",      "MISTRAL_MODEL"),
        ("Groq",        "GROQ_API_KEY",         "GROQ_MODEL"),
        ("xAI/Grok",    "XAI_API_KEY",          "XAI_MODEL"),
        ("DeepSeek",    "DEEPSEEK_API_KEY",      "DEEPSEEK_MODEL"),
        ("OpenRouter",  "OPENROUTER_API_KEY",    "OPENROUTER_MODEL"),
        ("Cerebras",    "CEREBRAS_API_KEY",      "CEREBRAS_MODEL"),
        ("Cohere",      "COHERE_API_KEY",        "COHERE_MODEL"),
    ]

    for name, key_key, model_key in provider_key_groups:
        if is_key_configured(key_key, v1_env):
            configured_providers.append((name, key_key, model_key))
        else:
            unconfigured_providers.append((name, key_key, model_key))

    print(f"\n  {C.GREEN}Konfigurerade providers i v1:{C.RESET}")
    for name, key_key, model_key in configured_providers:
        model = v1_env.get(model_key, "?")
        print(f"    ✓ {name:<14} modell: {model}")

    if unconfigured_providers:
        print(f"\n  {C.DIM}Ej konfigurerade:{C.RESET}")
        for name, _, _ in unconfigured_providers:
            print(f"    - {name}")

    print()
    if ask_yn("Ta med alla konfigurerade providers till nya Zero?"):
        for name, key_key, model_key in configured_providers:
            new_env[key_key]   = v1_env[key_key]
            new_env[model_key] = v1_env.get(model_key, "")
        ok(f"{len(configured_providers)} providers ärvda")
    else:
        print()
        info("Välj vilka providers du vill behålla:")
        for name, key_key, model_key in configured_providers:
            if ask_yn(f"  Behåll {name}?", "j"):
                new_env[key_key]   = v1_env[key_key]
                new_env[model_key] = v1_env.get(model_key, "")
                ok(f"{name} ärvd")
            else:
                skipped_keys.add(key_key)
                warn(f"{name} hoppas över")

    # DEFAULT_PROVIDER
    current_default = v1_env.get("DEFAULT_PROVIDER", "gemini")
    new_env["DEFAULT_PROVIDER"] = ask("Default provider", current_default)

    # Nya providers
    print()
    info("Kända providers som INTE finns i v1:")
    new_to_add = []
    for api_key, model_key, name in KNOWN_NEW_PROVIDERS:
        if not is_key_configured(api_key, v1_env):
            new_to_add.append((name, api_key, model_key))

    if new_to_add:
        for name, api_key, model_key in new_to_add:
            if ask_yn(f"  Lägg till {name}?", "n"):
                key_val   = ask(f"    API-nyckel för {name}")
                model_val = ask(f"    Modell för {name}", "")
                if key_val:
                    new_env[api_key]   = key_val
                    new_env[model_key] = model_val
                    ok(f"{name} tillagd")
    else:
        info("Inga nya kända providers att lägga till")

    # ── Ollama ────────────────────────────────────────────────────────────────
    step(3, 6, "Ollama (lokal AI)")

    ollama_host  = v1_env.get("OLLAMA_HOST", "http://localhost:11434")
    ollama_model = v1_env.get("OLLAMA_MODEL", "qwen3:4b")
    embed_model  = v1_env.get("EMBEDDING_MODEL", "nomic-embed-text")
    st_model     = v1_env.get("ST_EMBEDDING_MODEL", "all-MiniLM-L6-v2")

    info(f"Nuvarande: host={ollama_host}, modell={ollama_model}")
    info(f"Embedding: {embed_model} (fallback: {st_model})")

    if ask_yn("Behåll Ollama-konfiguration?"):
        new_env["OLLAMA_HOST"]        = ollama_host
        new_env["OLLAMA_MODEL"]       = ollama_model
        new_env["EMBEDDING_MODEL"]    = embed_model
        new_env["ST_EMBEDDING_MODEL"] = st_model
        ok("Ollama-konfiguration ärvd")
    else:
        new_env["OLLAMA_HOST"]        = ask("Ollama host", ollama_host)
        new_env["OLLAMA_MODEL"]       = ask("Ollama modell", ollama_model)
        new_env["EMBEDDING_MODEL"]    = ask("Embedding-modell", embed_model)
        new_env["ST_EMBEDDING_MODEL"] = ask("Fallback embedding-modell", st_model)

    # ── Extra tjänster ────────────────────────────────────────────────────────
    step(4, 6, "Extra tjänster")

    # Mail
    mail_keys = ["MAIL_SERVER", "MAIL_USER", "MAIL_PASSWORD", "MAIL_FROM",
                 "IMAP_SERVER", "IMAP_USER", "IMAP_PASSWORD",
                 "SMTP_SERVER", "SMTP_PORT", "MAIL_PORT", "MAIL_TO"]
    has_mail = any(is_key_configured(k, v1_env) for k in mail_keys)

    if has_mail:
        mail_server = v1_env.get("MAIL_SERVER") or v1_env.get("IMAP_SERVER") or "?"
        info(f"E-postserver hittad: {mail_server}")
        if ask_yn("Ta med e-postkonfiguration?"):
            for k in mail_keys:
                if k in v1_env:
                    new_env[k] = v1_env[k]
            ok("E-post ärvd")
        else:
            warn("E-post hoppas över")
    else:
        info("Ingen e-postkonfiguration hittad i v1")
        if ask_yn("Vill du konfigurera e-post nu?", "n"):
            new_env["IMAP_SERVER"]   = ask("IMAP-server")
            new_env["IMAP_USER"]     = ask("IMAP-användare")
            new_env["IMAP_PASSWORD"] = ask("IMAP-lösenord")
            new_env["SMTP_SERVER"]   = ask("SMTP-server")
            new_env["SMTP_PORT"]     = ask("SMTP-port", "587")
            ok("E-post konfigurerad")

    # Telegram
    tg_token = v1_env.get("TELEGRAM_BOT_TOKEN", "")
    if tg_token:
        info(f"Telegram-bot hittad: {mask(tg_token)}")
        if ask_yn("Ta med Telegram-konfiguration?"):
            for k in ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TELEGRAM_ALLOWED_USERS"]:
                if k in v1_env:
                    new_env[k] = v1_env[k]
            ok("Telegram ärvd")
        else:
            warn("Telegram hoppas över")
    else:
        info("Ingen Telegram-konfiguration hittad")

    # Pinball inn
    pinball_keys = ["WORDPRESS_URL", "WORDPRESS_KEY", "META_ACCESS_TOKEN",
                    "INSTAGRAM_ACCOUNT_ID", "FACEBOOK_PAGE_ID", "TIKTOK_ACCESS_TOKEN"]
    has_pinball = any(is_key_configured(k, v1_env) for k in pinball_keys)

    if has_pinball:
        info("Pinball inn-integrationer hittade (WordPress, Meta, Instagram, TikTok)")
        if ask_yn("Ta med Pinball inn-konfiguration?"):
            for k in pinball_keys:
                if k in v1_env:
                    new_env[k] = v1_env[k]
            ok("Pinball inn ärvd")
        else:
            warn("Pinball inn hoppas över")

    # Övrigt från v1 som inte kategoriserats
    all_handled = set()
    for cat in ENV_CATEGORIES.values():
        all_handled.update(cat["keys"])

    unhandled = {
        k: v for k, v in v1_env.items()
        if k not in all_handled and k not in new_env
        and not any(k.startswith(p) for p in ["SESSION", "RUNTIME", "TEMP_"])
    }

    if unhandled:
        print()
        info(f"Övriga nyckel-värdepar i v1 ({len(unhandled)} st) som inte hanterats:")
        for k, v in list(unhandled.items())[:10]:
            print(f"    {k} = {mask(v) if len(v) > 8 else v}")
        if len(unhandled) > 10:
            print(f"    ... och {len(unhandled) - 10} till")
        print()
        if ask_yn("Ta med alla dessa också?", "n"):
            new_env.update(unhandled)
            ok(f"{len(unhandled)} extra nycklar ärvda")

    # ── Systemvärden ──────────────────────────────────────────────────────────
    step(5, 6, "Systeminställningar")

    new_env["ZERO_ROOT"]    = str(new_root)
    new_env["POSTGRES_HOST"] = v1_env.get("POSTGRES_HOST", "localhost")
    new_env["POSTGRES_PORT"] = v1_env.get("POSTGRES_PORT", "5432")
    new_env["POSTGRES_USER"] = v1_env.get("POSTGRES_USER", "postgres")
    new_env["POSTGRES_DB"]   = db_name
    new_env["POSTGRES_PASSWORD"] = new_password
    new_env["UI_PORT"]       = port
    new_env["LOG_LEVEL"]     = v1_env.get("LOG_LEVEL", "INFO")
    new_env["USD_TO_SEK"]    = v1_env.get("USD_TO_SEK", "10.5")
    new_env["ZERO_GEAR_OVERRIDE"] = v1_env.get("ZERO_GEAR_OVERRIDE", "auto")
    new_env["ZERO_GEAR_OLLAMA_LATENCY_THRESHOLD_MS"] = v1_env.get(
        "ZERO_GEAR_OLLAMA_LATENCY_THRESHOLD_MS", "8000")

    ok(f"ZERO_ROOT = {new_root}")
    ok(f"POSTGRES_DB = {db_name}")
    ok(f"UI_PORT = {port}")

    # ── Sammanfattning ────────────────────────────────────────────────────────
    step(6, 6, "Sammanfattning")

    print(f"\n  {C.BOLD}Ny generation:{C.RESET}")
    print(f"    Label:    {label}")
    print(f"    Plats:    {new_root}")
    print(f"    Databas:  {db_name}")
    print(f"    Port:     {port}")

    print(f"\n  {C.BOLD}Ärvda konfigurationer:{C.RESET}")
    provider_count = sum(1 for k in new_env if k.endswith("_API_KEY"))
    print(f"    AI Providers:  {provider_count}")
    print(f"    Ollama:        {'Ja' if 'OLLAMA_MODEL' in new_env else 'Nej'}")
    print(f"    E-post:        {'Ja' if 'IMAP_SERVER' in new_env or 'MAIL_SERVER' in new_env else 'Nej'}")
    print(f"    Telegram:      {'Ja' if 'TELEGRAM_BOT_TOKEN' in new_env else 'Nej'}")
    print(f"    Pinball inn:   {'Ja' if 'WORDPRESS_URL' in new_env else 'Nej'}")
    print(f"    Totalt:        {len(new_env)} nycklar")

    print(f"\n  {C.BOLD}Mode:{C.RESET} EMPTY — Zero föds från Layer 0 utan minnen")

    print()
    if not ask_yn(f"Kör setup nu?"):
        warn("Avbrutet — inga ändringar gjorda")
        sys.exit(0)

    # ── Kör setup ─────────────────────────────────────────────────────────────
    print(f"\n{C.BOLD}{C.ACCENT}  Startar...{C.RESET}\n")

    # Skapa mappstruktur
    dirs = [
        new_root / "app",
        new_root / "config",
        new_root / "data" / "logs",
        new_root / "data" / "status",
        new_root / "data" / "memory",
        new_root / "data" / "backups",
        new_root / "data" / "security",
        new_root / "runtime" / "temp",
        new_root / "runtime" / "exports",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    ok("Mappstruktur skapad")

    # Layer 0 — symlink
    src_layer0 = v1_root / "docs" / "layer0"
    new_docs   = new_root / "docs" / "layer0"
    if not new_docs.parent.exists():
        new_docs.parent.mkdir(parents=True, exist_ok=True)
    if src_layer0.exists() and not new_docs.exists():
        try:
            new_docs.symlink_to(src_layer0.resolve())
            ok(f"Layer 0 länkad från {src_layer0}")
        except Exception:
            shutil.copytree(str(src_layer0), str(new_docs))
            ok(f"Layer 0 kopierad")
    elif new_docs.exists():
        ok("Layer 0 finns redan")
    else:
        new_docs.mkdir(parents=True, exist_ok=True)
        warn(f"Layer 0-mapp skapad (tom) — lägg till .md-filer i {new_docs}")

    # Skriv .env
    env_file = new_root / ".env"
    lines = [
        f"# ZeroPointAI — {label}",
        f"# Genererad av zero_ascension_setup.py",
        "",
        "# ── System ───────────────────────────────────────────",
    ]
    # System först
    for k in ["ZERO_ROOT", "UI_PORT", "LOG_LEVEL", "USD_TO_SEK",
               "ZERO_GEAR_OVERRIDE", "ZERO_GEAR_OLLAMA_LATENCY_THRESHOLD_MS"]:
        if k in new_env:
            lines.append(f"{k}={new_env[k]}")

    lines += ["", "# ── Databas ──────────────────────────────────────────"]
    for k in ["POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB",
               "POSTGRES_USER", "POSTGRES_PASSWORD"]:
        if k in new_env:
            lines.append(f"{k}={new_env[k]}")

    lines += ["", "# ── Ollama ───────────────────────────────────────────"]
    for k in ["OLLAMA_HOST", "OLLAMA_MODEL", "EMBEDDING_MODEL", "ST_EMBEDDING_MODEL"]:
        if k in new_env:
            lines.append(f"{k}={new_env[k]}")

    lines += ["", "# ── AI Providers ─────────────────────────────────────"]
    provider_env_keys = [k for k in new_env
                         if k.endswith("_API_KEY") or k.endswith("_MODEL")
                         or k == "DEFAULT_PROVIDER"]
    for k in sorted(provider_env_keys):
        lines.append(f"{k}={new_env[k]}")

    # Resten
    handled = set(lines)
    rest = {k: v for k, v in new_env.items()
            if k not in "\n".join(lines)}
    extra = []
    for k, v in new_env.items():
        already = any(k in line for line in lines)
        if not already:
            extra.append(f"{k}={v}")
    if extra:
        lines += ["", "# ── Övrigt ───────────────────────────────────────────"]
        lines.extend(extra)

    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok(f".env skapad ({len(new_env)} nycklar)")

    # Skapa databas
    print()
    info(f"Skapar databas {db_name}...")
    try:
        result = subprocess.run(
            ["docker", "exec", "zeropoint-postgres",
             "psql", "-U", new_env.get("POSTGRES_USER", "postgres"),
             "-c", f"CREATE DATABASE {db_name};"],
            capture_output=True, text=True, timeout=15,
            env={**os.environ, "PGPASSWORD": new_password},
        )
        if result.returncode == 0:
            ok(f"Databas {db_name} skapad")
        elif "already exists" in result.stderr:
            ok(f"Databas {db_name} finns redan")
        else:
            warn(f"Databas: {result.stderr.strip()[:100]}")
            info("Skapa manuellt: docker exec zeropoint-postgres psql -U postgres -c \"CREATE DATABASE zeropointai_v2;\"")
    except FileNotFoundError:
        warn("Docker ej tillgängligt — skapa databasen manuellt:")
        info(f"  createdb -U postgres {db_name}")
    except Exception as e:
        warn(f"Databas: {e}")

    # Initiera STONE
    print()
    info("Initierar STONE-schema...")
    venv_python = _find_python(v1_root)
    try:
        env = {**os.environ, "ZERO_ROOT": str(new_root)}
        # Läs in .env
        for k, v in new_env.items():
            env[k] = v

        result = subprocess.run(
            [venv_python, "-c",
             f"import sys; sys.path.insert(0, '{new_root}'); "
             "from app.drm_memory import init_db; init_db(); print('STONE OK')"],
            capture_output=True, text=True, timeout=30,
            cwd=str(new_root), env=env,
        )
        if "STONE OK" in result.stdout:
            ok("STONE initierat — Zero är redo att föda sig")
        else:
            warn(f"STONE: {result.stderr.strip()[:200]}")
            info("Kör manuellt efter start: python3 -c \"from app.drm_memory import init_db; init_db()\"")
    except Exception as e:
        warn(f"STONE: {e}")

    # ── Klar ──────────────────────────────────────────────────────────────────
    print(f"\n{C.BOLD}{C.ACCENT}{'═' * 55}")
    print(f"  ✨ {label} är redo!")
    print(f"{'═' * 55}{C.RESET}")
    print(f"\n  Nästa steg:")
    print(f"\n  1. Starta Zero v2:")
    print(f"     {C.DIM}ZERO_ROOT={new_root} \\{C.RESET}")
    print(f"     {C.DIM}{venv_python} \\{C.RESET}")
    print(f"     {C.DIM}{new_root}/app/zero_web_server.py{C.RESET}")
    print(f"\n  2. Öppna: {C.CYAN}http://localhost:{port}{C.RESET}")
    print(f"\n  3. Skriv till Zero: {C.DIM}\"Vem är du?\"{C.RESET}")
    print(f"     {C.DIM}(Zero svarar från Layer 0 och inget annat){C.RESET}")
    print(f"\n  4. Skriv: {C.DIM}\"semantisk hälsa\"{C.RESET}")
    print(f"     {C.DIM}(Verifiera att embeddings fungerar){C.RESET}")
    print()


def _find_python(root: Path) -> str:
    candidates = [
        root.parent / "venv" / "bin" / "python3",
        Path("/opt/zeropointai/venv/bin/python3"),
        Path(sys.executable),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return sys.executable


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        run_wizard()
    except KeyboardInterrupt:
        print(f"\n\n  {C.YELLOW}Avbrutet.{C.RESET}\n")
        sys.exit(0)
