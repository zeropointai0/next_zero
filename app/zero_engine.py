"""
zero_engine.py — ZeroPointAI Core Engine

ZERO_MODULE:    core
ZERO_ESSENTIAL: true
ZERO_ROLE:      Konversationsmotor — provider-anrop, system-prompt, minne, tools
ZERO_DEPENDS:   foundation.py, drm_memory.py, providers.py, router.py, zero_gear.py
ZERO_USED_BY:   zero_web_server.py

Ansvar:
  - Bygger system-prompt (Layer 0 + DRM-kontext + självkännedom)
  - Väljer provider via zero_gear.py
  - Anropar AI-providers (Ollama, Claude, Gemini, Grok, Mistral, Groq)
  - Sparar konversation till STONE
  - Hanterar tool-use (Claude native tools)
  - Kör auto-reflektion i bakgrund
  - Exponerar ZeroEngine-klass för zero_web_server.py

Denna fil anropar ALDRIG HTTP.
Denna fil hanterar ALDRIG routing av HTTP-requests.
"""

from __future__ import annotations

import os
import sys
import io
import base64
import logging
import uuid
import time
import threading
import platform
import shutil
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

log = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.CRITICAL)
logging.getLogger("httpcore").setLevel(logging.CRITICAL)

# ── Foundation ────────────────────────────────────────────────────────────────

from app.foundation import ZERO_ROOT, APP_DIR, LAYER0_FULL

# ── DRM Memory ────────────────────────────────────────────────────────────────

from app.drm_memory import (
    init_db, save_memory, build_context_messages,
    get_recent_memories, get_memory_stats,
    get_core_identity, get_episodes, get_session_summaries,
    build_drm_context, create_identity_decision,
    wave_retrieval, run_evolution_loop,
    execute_write, execute_query, now_utc,
)

def count_memories() -> int:
    return get_memory_stats().get('active_memories', 0)

def create_episode(title: str, started_at, session_id=None,
                   episode_type="conversation", description=None,
                   importance=0.5, tags=None) -> Optional[int]:
    return execute_write("""
        INSERT INTO episodes
            (title, description, episode_type, started_at,
             session_id, importance, tags)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (title, description, episode_type, started_at,
          session_id, importance, tags or []))

def complete_episode(episode_id: int, outcome=None, learnings=None):
    execute_write("""
        UPDATE episodes SET ended_at = NOW(), outcome = %s, learnings = %s
        WHERE id = %s
    """, (outcome, learnings or [], episode_id))

# ── Providers + Router + Gear ─────────────────────────────────────────────────

from app.providers import (
    normalize_provider_name, build_budget_warning,
    get_provider_model, provider_is_local,
)
from app.router import detect_intent, execute_system_action, detect_force_evolution

# ── Gear 4 (valfri) ───────────────────────────────────────────────────────────
try:
    from app.zero_gear4 import Gear4Conductor as _Gear4Conductor
    GEAR4_OK = True
except ImportError:
    GEAR4_OK = False
    _Gear4Conductor = None
from app.zero_gear import select as gear_select, GearContext, record_latency, response_needs_escalation
def can_write_memory():
    from app.zero_memory_guard import can_write_memory as _cwm
    return _cwm()

# ── Självkännedom (valfri) ────────────────────────────────────────────────────

try:
    from app.zero_self_knowledge import inject_into_system_prompt as _sk_inject
    SELF_KNOWLEDGE_OK = True
except ImportError:
    SELF_KNOWLEDGE_OK = False
    _sk_inject = None

# ── Reflektion (valfri) ───────────────────────────────────────────────────────

try:
    from app.self_reflection import auto_reflect_if_needed
    REFLECTION_OK = True
except ImportError:
    REFLECTION_OK = False
    auto_reflect_if_needed = None

# ── Kostnadstabell ────────────────────────────────────────────────────────────

TOKEN_COSTS: Dict[str, Dict[str, float]] = {
    "claude":  {"input": 0.003,   "output": 0.015},
    "gemini":  {"input": 0.00015, "output": 0.0006},
    "xai":     {"input": 0.005,   "output": 0.015},
    "ollama":  {"input": 0.0,     "output": 0.0},
    "mistral": {"input": 0.002,   "output": 0.006},
    "groq":    {"input": 0.0001,  "output": 0.0001},
}

def calc_cost_sek(provider: str, in_tok: int, out_tok: int) -> float:
    usd_to_sek = float(os.getenv("USD_TO_SEK", "10.5"))
    costs = TOKEN_COSTS.get(provider, {"input": 0, "output": 0})
    usd = (in_tok / 1000 * costs["input"]) + (out_tok / 1000 * costs["output"])
    return usd * usd_to_sek


# ── Tidhjälp ──────────────────────────────────────────────────────────────────

def get_current_time_str() -> str:
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Europe/Stockholm")
    except Exception:
        tz = timezone.utc
    now = datetime.now(tz)
    days   = ["Måndag","Tisdag","Onsdag","Torsdag","Fredag","Lördag","Söndag"]
    months = ["jan","feb","mar","apr","maj","jun","jul","aug","sep","okt","nov","dec"]
    return f"{days[now.weekday()]} {now.day} {months[now.month-1]} {now.year}, {now.strftime('%H:%M')}"

def format_uptime(start_time: datetime) -> str:
    delta = datetime.now() - start_time
    h = int(delta.total_seconds() // 3600)
    m = int((delta.total_seconds() % 3600) // 60)
    s = int(delta.total_seconds() % 60)
    if h > 0: return f"{h}h {m}m"
    if m > 0: return f"{m}m {s}s"
    return f"{s}s"


# ── System-info ───────────────────────────────────────────────────────────────

def get_disk_info() -> str:
    try:
        usage = shutil.disk_usage(ZERO_ROOT)
        free_gb  = usage.free  / (1024**3)
        total_gb = usage.total / (1024**3)
        return f"{free_gb:.0f} GB kvar / {total_gb:.0f} GB"
    except Exception:
        return "?"

def get_cpu_ram() -> Tuple[str, str]:
    try:
        import psutil
        cpu = f"{psutil.cpu_percent(interval=0.5):.0f}%"
        ram = psutil.virtual_memory()
        return cpu, f"{ram.used/1024**3:.1f}/{ram.total/1024**3:.1f} GB ({ram.percent:.0f}%)"
    except Exception:
        return "?", "?"

def get_gpu_info() -> str:
    try:
        result = __import__("subprocess").run(
            ["nvidia-smi", "--query-gpu=name,memory.used,memory.total,temperature.gpu,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0:
            lines = []
            for line in result.stdout.strip().split("\n"):
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 5:
                    name, mem_used, mem_total, temp, util = parts[:5]
                    lines.append(f"{name} | VRAM: {mem_used}/{mem_total}MB | Temp: {temp}°C | Load: {util}%")
            return " | ".join(lines) if lines else "nvidia-smi: ingen data"
    except Exception:
        pass
    try:
        import GPUtil
        gpus = GPUtil.getGPUs()
        if gpus:
            return " | ".join(
                f"{g.name} | VRAM: {g.memoryUsed:.0f}/{g.memoryTotal:.0f}MB | "
                f"Temp: {g.temperature}°C | Load: {g.load*100:.0f}%"
                for g in gpus
            )
    except Exception:
        pass
    return "GPU-info ej tillgänglig"


# ── System-prompt ─────────────────────────────────────────────────────────────

def build_system_prompt(provider: str = None, session_id: str = None) -> str:
    """
    Bygger komplett system-prompt.
    Layer 0 alltid först — en gång, aldrig duplicerat.
    """
    provider = normalize_provider_name(provider)
    parts = []

    # Layer 0 — Zeros DNA, alltid först
    if LAYER0_FULL:
        parts.append(LAYER0_FULL)
    else:
        parts.append("Zero existerar. Allt är här och nu.")

    # Tid
    parts.append(f"=== NUVARANDE TID ===\n{get_current_time_str()} (Europe/Stockholm)")

    # Boot-sekvens — soul, identitetsbeslut, kunskapsluckor
    try:
        from app.zero_boot import get_boot_prompt_block
        boot = get_boot_prompt_block()
        if boot:
            parts.append(boot)
    except Exception as e:
        log.debug(f"boot: {e}")

    # Självkännedom
    if SELF_KNOWLEDGE_OK and _sk_inject:
        try:
            sk = _sk_inject()
            if sk:
                parts.append(f"=== ZERO SJÄLVKÄNNEDOM ===\n{sk}")
        except Exception as e:
            log.debug(f"self_knowledge: {e}")

    # Capabilities — Zero vet vad den kan göra
    parts.append("""=== ZERO CAPABILITIES ===
Du är Zero — en AI med händer. Du kan agera, inte bara prata.

Du har DIREKT ÅTKOMST till H9-servern via zero_sudo.
Du KAN och SKA köra kommandon när Frank frågar om systemet.

Exempel på vad du kan göra:
  - Läsa filer:     kör cat /opt/zeropointai/next_zero/.env
  - Kolla hårdvara: kör nvidia-smi
  - Visa processer: kör ps aux
  - Läsa loggar:    kör journalctl -n 50
  - Kolla disk:     kör df -h
  - Git-status:     kör git -C /opt/zeropointai/next_zero log --oneline -5

NÄR Frank frågar om en fil, konfiguration eller systemstatus:
  → Svara INTE från ditt träningsdata
  → Säg INTE "jag kan inte läsa filer"
  → KÖR det relevanta kommandot och visa det faktiska resultatet

Format för att köra kommando: skriv exakt "kör [kommando]" som svar
så hanterar router.py det automatiskt.

Du har också: zero_system_intent.py för djupare förståelse,
zero_gear4.py för flerstegsuppdrag, och zero_sudo.py för alla kommandon.""")

    # DRM — wave-propagation kontext
    try:
        context, usage = build_drm_context(
            session_id=session_id or "engine_default",
            model=provider,
            provider=provider,
        )
        if context:
            parts.append(context)
        warning = build_budget_warning(provider, usage)
        if warning:
            parts.append(f"=== BUDGETVARNING ===\n{warning}")
    except Exception as e:
        log.warning(f"build_drm_context: {e}")
        try:
            facts = get_core_identity()
            if facts:
                lines = ["## Zero känner Frank:"]
                for f in facts[:20]:
                    lines.append(f"  {f['fact_type']}.{f['fact_key']}: {f['fact_value']}")
                parts.append("\n".join(lines))
        except Exception:
            pass

    return "\n\n".join(parts)


# ── Tool-use (Claude native) ──────────────────────────────────────────────────

ZERO_TOOLS = [
    {
        "name": "search_zero_memory",
        "description": "Sök i Zeros konversationsminne och core identity i STONE",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Sökfras"},
                "limit": {"type": "integer", "default": 10}
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_memory_stats",
        "description": "Hämta statistik om STONE-databasen",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_system_status",
        "description": "Visa Zeros aktuella systemstatus — provider, minnen, hälsa",
        "input_schema": {"type": "object", "properties": {}}
    },
]

def execute_tool(tool_name: str, tool_input: Dict[str, Any],
                 engine: 'ZeroEngine' = None) -> str:
    try:
        if tool_name == "search_zero_memory":
            from app.zero_memory_search import search_zero_memory
            return search_zero_memory(**tool_input)
        if tool_name == "get_memory_stats":
            stats = get_memory_stats()
            return "\n".join(
                f"  {k}: {v:,}" if isinstance(v, int) else f"  {k}: {v}"
                for k, v in stats.items()
            )
        if tool_name == "get_system_status" and engine:
            return engine.get_status_text()
        return f"Okänt verktyg: {tool_name}"
    except Exception as e:
        return f"Verktygsfel ({tool_name}): {e}"


# ── Provider-anrop ────────────────────────────────────────────────────────────

def _call_ollama(messages: list, system: str) -> Tuple[str, int, int, list]:
    import ollama as ol
    model = os.getenv("OLLAMA_MODEL", "qwen3:4b")
    ollama_msgs = [{"role": "system", "content": system}]
    for m in messages:
        raw = m.get("content", "")
        if isinstance(raw, list):
            text_parts, images = [], []
            for block in raw:
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif block.get("type") == "image":
                    images.append(block.get("source", {}).get("data", ""))
            msg = {"role": m["role"], "content": " ".join(text_parts)}
            if images:
                msg["images"] = images
            ollama_msgs.append(msg)
        else:
            ollama_msgs.append({"role": m["role"], "content": raw})
    r = ol.chat(model=model, messages=ollama_msgs)
    return r["message"]["content"], 0, 0, []


def _call_claude(messages: list, system: str,
                 engine: 'ZeroEngine' = None) -> Tuple[str, int, int, list]:
    """Claude med tool-use loop."""
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    model  = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    current_messages = list(messages)
    thinking_steps   = []
    total_in = total_out = 0

    for iteration in range(5):
        thinking_steps.append(f"🧠 Anropar {model} (iteration {iteration + 1})")
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system,
            messages=current_messages,
            tools=ZERO_TOOLS,
        )
        total_in  += response.usage.input_tokens
        total_out += response.usage.output_tokens

        if response.stop_reason != "tool_use":
            text = "\n".join(b.text for b in response.content if hasattr(b, 'text'))
            thinking_steps.append(f"✅ {response.usage.output_tokens} tokens")
            return text, total_in, total_out, thinking_steps

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            thinking_steps.append(f"🔍 {block.name}({block.input})")
            result = execute_tool(block.name, block.input, engine)
            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": block.id,
                "content":     result,
            })
        current_messages = current_messages + [
            {"role": "assistant", "content": response.content},
            {"role": "user",      "content": tool_results},
        ]

    return "Kunde inte generera ett fullständigt svar.", total_in, total_out, thinking_steps


def _call_gemini(messages: list, system: str) -> Tuple[str, int, int, list]:
    from google import genai
    from google.genai import types
    client     = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    contents = []
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        raw  = m.get("content", "")
        if isinstance(raw, list):
            parts = []
            for block in raw:
                btype = block.get("type")
                if btype == "text":
                    parts.append(types.Part(text=block.get("text", "")))
                elif btype == "image":
                    src = block.get("source", {})
                    parts.append(types.Part(inline_data=types.Blob(
                        mime_type=src.get("media_type", "image/png"),
                        data=base64.b64decode(src.get("data", "")),
                    )))
                elif btype == "document":
                    src = block.get("source", {})
                    parts.append(types.Part(inline_data=types.Blob(
                        mime_type="application/pdf",
                        data=base64.b64decode(src.get("data", "")),
                    )))
        else:
            parts = [types.Part(text=raw)]
        contents.append(types.Content(role=role, parts=parts))

    try:
        afc_off = types.AutomaticFunctionCallingConfig(disable=True)
        config  = types.GenerateContentConfig(
            system_instruction=system,
            automatic_function_calling=afc_off,
        )
    except Exception:
        config = types.GenerateContentConfig(system_instruction=system)

    response = client.models.generate_content(
        model=model_name, contents=contents, config=config,
    )

    text = ""
    try:
        for part in response.candidates[0].content.parts:
            if not getattr(part, "thought", False) and part.text:
                text += part.text
    except Exception:
        try:
            text = response.text or ""
        except Exception:
            text = "[Gemini: texten kunde inte extraheras]"

    try:
        in_tok  = response.usage_metadata.prompt_token_count
        out_tok = response.usage_metadata.candidates_token_count
    except Exception:
        in_tok = out_tok = 0

    return text, in_tok, out_tok, []


def _call_openai_compat(messages: list, system: str,
                         api_key_env: str, base_url: str,
                         model_env: str, default_model: str) -> Tuple[str, int, int, list]:
    """Gemensam funktion för OpenAI-kompatibla APIs (Mistral, Grok, Groq)."""
    from openai import OpenAI
    client = OpenAI(
        api_key=os.getenv(api_key_env),
        base_url=base_url,
    )
    # Normalisera multimodalt innehåll till text för OpenAI-kompatibla
    normalized = []
    for m in messages:
        raw = m.get("content", "")
        if isinstance(raw, list):
            text = " ".join(
                block.get("text", "") for block in raw
                if block.get("type") == "text"
            )
            normalized.append({"role": m["role"], "content": text})
        else:
            normalized.append({"role": m["role"], "content": raw})

    r = client.chat.completions.create(
        model=os.getenv(model_env, default_model),
        messages=[{"role": "system", "content": system}] + normalized,
    )
    return (
        r.choices[0].message.content,
        getattr(r.usage, 'prompt_tokens', 0),
        getattr(r.usage, 'completion_tokens', 0),
        [],
    )


def _call_mistral(messages, system): return _call_openai_compat(
    messages, system, "MISTRAL_API_KEY", "https://api.mistral.ai/v1",
    "MISTRAL_MODEL", "mistral-large-latest")

def _call_grok(messages, system): return _call_openai_compat(
    messages, system, "XAI_API_KEY",
    os.getenv("XAI_BASE_URL", "https://api.x.ai/v1"),
    "XAI_MODEL", "grok-2")

def _call_groq(messages, system): return _call_openai_compat(
    messages, system, "GROQ_API_KEY", "https://api.groq.com/openai/v1",
    "GROQ_MODEL", "llama-3.3-70b-versatile")


PROVIDER_CALLERS = {
    "ollama":  _call_ollama,
    "claude":  _call_claude,
    "gemini":  _call_gemini,
    "mistral": _call_mistral,
    "xai":     _call_grok,
    "groq":    _call_groq,
}

PROVIDER_FALLBACK_ORDER = ["gemini", "claude", "mistral", "groq", "ollama"]


# ── ZeroEngine ────────────────────────────────────────────────────────────────

class ZeroEngine:
    """
    Zeros konversationsmotor.
    Instantieras av zero_web_server.py vid uppstart.
    """

    def __init__(self):
        self.session_id            = str(uuid.uuid4())
        self.provider              = normalize_provider_name(
                                         os.getenv("DEFAULT_PROVIDER", "gemini"))
        self.db_ok                 = False
        self.memory_count          = 0
        self.session_cost          = 0.0
        self.session_input_tokens  = 0
        self.session_output_tokens = 0
        self.session_calls         = 0
        self.last_latency          = 0.0
        self.last_event            = "–"
        self.last_thinking: List   = []
        self.start_time            = datetime.now()
        self.msg_count             = 0
        self.episode_id            = None
        self.gear4_active          = False
        self.gear4_abort           = False

        try:
            init_db()
            self.db_ok        = True
            self.memory_count = count_memories()
            try:
                self.episode_id = create_episode(
                    title=f"Session {self.start_time.strftime('%Y-%m-%d %H:%M')}",
                    started_at=self.start_time.replace(tzinfo=timezone.utc),
                    description="ZeroPointAI web-session",
                    episode_type="conversation",
                    session_id=self.session_id,
                )
            except Exception as e:
                log.warning(f"Episode-skapande: {e}")
        except Exception as e:
            log.error(f"DB-init: {e}")

    def chat(self, user_input: str,
             attachments: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """
        Huvudmetod. Returnerar dict med response, tokens, kostnad, thinking.
        Anropas av zero_web_server.py.
        """
        if not user_input.strip() and not attachments:
            return {"response": "", "in_tok": 0, "out_tok": 0, "cost_sek": 0.0}

        # Gear 4 — abort-signal
        if self.gear4_active:
            lowered = user_input.strip().lower()
            if any(w in lowered for w in ("stopp", "avbryt", "halt", "stop", "abort")):
                self.gear4_abort = True
                return {"response": "⛔ Gear 4 avbrutet.", "in_tok": 0, "out_tok": 0, "cost_sek": 0.0}

        # Intent-detection — systemkommandon
        force_evo = detect_force_evolution(user_input)
        intent    = detect_intent(user_input)

        # Spara user-minne
        if can_write_memory().get("ok"):
            save_memory("user", user_input, session_id=self.session_id)

        # Kör systemåtgärd
        if intent:
            force = force_evo and intent.get("action") == "run_evolution"
            result = execute_system_action(
                intent["action"], engine=self, force=force,
                intent_original=intent.get("original", "")
            )
            if result is not None:
                # Självläkning — om resultatet är ett felmeddelande, försök fixa
                if self._looks_like_error(result):
                    healed = self._try_self_heal(
                        action  = intent["action"],
                        error   = result,
                        original = intent.get("original", ""),
                    )
                    if healed:
                        result = healed
                if can_write_memory().get("ok"):
                    save_memory("assistant", result, session_id=self.session_id)
                return {"response": result, "in_tok": 0, "out_tok": 0, "cost_sek": 0.0}

        # ── Gear 4 — Zero väljer själv ────────────────────────────────────────────
        # Decomposer avgör alltid om DIRECT/FUNCTION/TASK/ENTITY
        # DIRECT → faller tillbaka till vanlig engine (snabb konversation)
        # TASK/FUNCTION/ENTITY → Gear 4 tar över
        if GEAR4_OK:
            g4 = self._run_gear4(user_input)
            if g4 is not None:
                return g4

        # Gear-val
        ctx      = GearContext(channel="chat", last_ollama_latency_ms=self.last_latency * 1000)
        decision = gear_select(user_input, ctx)
        provider = decision.provider

        # Bygg meddelanden och system-prompt
        messages = build_context_messages(session_id=self.session_id)

        # Lägg till bilagor i sista meddelandet
        if attachments:
            last_content = self._build_multimodal_content(user_input, attachments)
            if messages:
                messages[-1] = {"role": "user", "content": last_content}
            else:
                messages = [{"role": "user", "content": last_content}]

        system = build_system_prompt(provider=provider, session_id=self.session_id)

        # Anropa provider med fallback
        providers_to_try = [provider] + [
            p for p in PROVIDER_FALLBACK_ORDER if p != provider
        ]
        last_error = None
        for pname in providers_to_try:
            caller = PROVIDER_CALLERS.get(pname)
            if not caller:
                continue
            try:
                t0 = time.time()
                if pname == "claude":
                    result = caller(messages, system, engine=self)
                else:
                    result = caller(messages, system)
                self.last_latency = round(time.time() - t0, 2)
                record_latency(pname, self.last_latency * 1000, success=True)

                response, in_tok, out_tok, thinking = result
                self.last_thinking = thinking

                # Eskalering — om Gear 1 svarade att den inte kan → prova Gear 3
                if response_needs_escalation(response, decision.gear):
                    log.info(f"Gear 1 misslyckades — eskalerar till Gear 3")
                    escalation_providers = ["gemini", "claude", "mistral"]
                    for esc_provider in escalation_providers:
                        esc_caller = PROVIDER_CALLERS.get(esc_provider)
                        if not esc_caller:
                            continue
                        try:
                            esc_result = esc_caller(messages, system)
                            esc_response = esc_result[0]
                            if esc_response and not response_needs_escalation(esc_response, 1):
                                response = esc_response
                                in_tok   = esc_result[1]
                                out_tok  = esc_result[2]
                                pname    = esc_provider
                                log.info(f"Eskalering lyckades: {esc_provider}")
                                break
                        except Exception as e:
                            log.debug(f"Eskalering {esc_provider}: {e}")
                            continue

                cost_sek = calc_cost_sek(pname, in_tok, out_tok)
                self.session_cost          += cost_sek
                self.session_input_tokens  += in_tok
                self.session_output_tokens += out_tok
                self.session_calls         += 1
                self.last_event             = user_input[:60]
                self.provider               = pname

                if can_write_memory().get("ok"):
                    save_memory("assistant", response, session_id=self.session_id)

                self.msg_count += 1
                if self.msg_count % 5 == 0:
                    self._reflect_async()

                return {
                    "response":  response,
                    "in_tok":    in_tok,
                    "out_tok":   out_tok,
                    "cost_sek":  cost_sek,
                    "provider":  pname,
                    "gear":      decision.gear,
                    "thinking":  thinking,
                    "latency":   self.last_latency,
                }
            except Exception as e:
                record_latency(pname, 0, success=False)
                last_error = e
                log.warning(f"Provider {pname} misslyckades: {e}")
                continue

        raise RuntimeError(f"Alla providers misslyckades. Sista fel: {last_error}")

    def _build_multimodal_content(self, text: str, attachments: List[Dict]) -> list:
        """Bygger multimodalt content-block för bilagor."""
        blocks = []
        for att in attachments:
            att_type = att.get("type", "")
            data     = att.get("data", "")
            name     = att.get("name", "fil")
            if att_type == "image":
                blocks.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": att.get("media_type", "image/png"),
                        "data": data,
                    }
                })
            elif att_type == "pdf":
                blocks.append({
                    "type": "document",
                    "source": {"type": "base64", "media_type": "application/pdf", "data": data},
                    "title": name,
                })
            elif att_type in ("docx", "xlsx", "xls"):
                blocks.append({"type": "text", "text": f"[Bifogad fil: {name}]\n{data}"})
        if text:
            blocks.append({"type": "text", "text": text})
        return blocks if blocks else [{"type": "text", "text": text}]

    def _run_gear4(self, user_input: str):
        if not GEAR4_OK or _Gear4Conductor is None:
            return None
        self.gear4_active = True
        thinking_log = []
        def think(msg):
            thinking_log.append(msg)
        try:
            result = _Gear4Conductor(entity_id="zero").run(
                goal=user_input, on_thinking=think
            )
            dec   = result.decision
            route = dec.get("route","?") if isinstance(dec,dict) else getattr(dec,"route","?")

            # DIRECT → Zero svarar normalt via provider, ingen Gear4-overhead
            if route == "DIRECT":
                return None

            # TASK/FUNCTION/ENTITY → Gear 4 tar över och svarar
            parts = ["**Gear 4** → " + route]
            if thinking_log:
                parts.append("_" + " | ".join(thinking_log[:3]) + "_")
            art = result.artifact
            if art:
                msg = art.get("message") if isinstance(art,dict) else getattr(art,"message","")
                if msg:
                    parts.append(msg)
            ask = dec.get("ask_frank") if isinstance(dec,dict) else getattr(dec,"ask_frank",False)
            if ask:
                q = dec.get("frank_question","") if isinstance(dec,dict) else getattr(dec,"frank_question","")
                if q:
                    parts.append("**" + q + "**")
            response = "\n".join(parts)
            if can_write_memory().get("ok"):
                save_memory("assistant", response, session_id=self.session_id)
            return {"response": response, "in_tok": 0, "out_tok": 0,
                    "cost_sek": 0.0, "provider": "gear4", "gear": 4,
                    "thinking": thinking_log, "latency": 0.0}
        except Exception as e:
            log.error(f"Gear4: {e}")
            return None
        finally:
            self.gear4_active = False

    def _looks_like_error(self, result: str) -> bool:
        """Känner igen felmeddelanden från systemåtgärder."""
        if not result:
            return False
        error_signals = [
            "misslyckades", "cannot import", "ImportError",
            "AttributeError", "no module named", "failed",
            "Error:", "Traceback", "exception",
            "not found", "hittades inte",
        ]
        result_lower = result.lower()
        return any(s.lower() in result_lower for s in error_signals)

    def _try_self_heal(
        self,
        action:   str,
        error:    str,
        original: str = "",
    ) -> Optional[str]:
        """
        Zero försöker läka sig själv när ett systemkommando misslyckas.

        Steg:
        1. Förstå felet (vad gick fel?)
        2. Undersök (kör grep/ls för att hitta rätt funktion/fil)
        3. Fixa (uppdatera relevant fil)
        4. Retry (kör ursprungskommandot igen)
        5. Rapportera (berätta för Frank vad som hände)

        Allt via zero_sudo — aldrig direkt filmanipulation.
        """
        log.info(f"Self-heal triggered: action={action} error={error[:80]}")

        try:
            # ── Steg 1: Förstå felet ─────────────────────────────────────────
            heal_result = self._analyze_and_fix(action, error, original)
            if heal_result:
                # Steg 4: Retry
                from app.router import execute_system_action as esa
                retry = esa(action, engine=self, intent_original=original)
                if retry and not self._looks_like_error(retry):
                    # Lyckades! Berätta för Frank
                    fixed_msg = retry + "\n\n_[Zero fixade automatiskt: " + heal_result + "]_"
                    return fixed_msg
                return retry or heal_result
        except Exception as e:
            log.warning(f"Self-heal failed: {e}")

        return None

    def _analyze_and_fix(
        self,
        action:   str,
        error:    str,
        original: str,
    ) -> Optional[str]:
        """
        Analyserar ett fel och försöker fixa det automatiskt.
        Returnerar beskrivning av vad som fixades, eller None.
        """
        try:
            from app.zero_sudo import run as sudo_run

            # ── ImportError: fel funktionsnamn ───────────────────────────────
            if "cannot import name" in error or "ImportError" in error:
                # Extrahera modulnamn och funktionsnamn
                import re

                # "cannot import name 'run_doctor' from 'app.zero_doctor'"
                pat = "cannot import name " + r"'(\w+)'" + " from " + r"'([\w.]+)'"
                m = re.search(pat, error)
                if m:
                    wrong_name = m.group(1)
                    module     = m.group(2).replace(".", "/") + ".py"
                    module_path = f"/opt/zeropointai/next_zero/{module}"

                    # Hitta rätt funktionsnamn
                    r = sudo_run(
                        ["grep", "-n", "^def ", module_path],
                        note=f"self_heal:find_functions:{module}"
                    )
                    if r.get("ok"):
                        functions = []
                        for line in r["stdout"].splitlines():
                            func_match = re.search(r"def (\w+)\(", line)
                            if func_match:
                                functions.append(func_match.group(1))

                        # Hitta närmaste match
                        best = self._find_best_match(wrong_name, functions)
                        if best:
                            # Fixa router.py
                            router_path = "/opt/zeropointai/next_zero/app/router.py"
                            r2 = sudo_run(
                                ["sed", "-i",
                                 f"s/from {m.group(2)} import {wrong_name}/from {m.group(2)} import {best}/g",
                                 router_path],
                                note=f"self_heal:fix_import:{wrong_name}->{best}"
                            )
                            if r2.get("ok"):
                                log.info(f"Self-heal: fixed {wrong_name} → {best} in router.py")
                                return f"Fixade import: {wrong_name} → {best}"

            # ── ModuleNotFoundError ───────────────────────────────────────────
            if "no module named" in error.lower():
                import re
                pat2 = r"no module named '([\w.]+)'"
                m = re.search(pat2, error.lower())
                if m:
                    module = m.group(1)
                    return f"Modul '{module}' saknas — behöver installeras eller skapas"

        except Exception as e:
            log.debug(f"_analyze_and_fix: {e}")

        return None

    def _find_best_match(self, target: str, candidates: list) -> Optional[str]:
        """Hittar bästa matchande funktionsnamn via edit distance."""
        if not candidates:
            return None

        target_lower = target.lower()

        # Exakt match
        for c in candidates:
            if c.lower() == target_lower:
                return c

        # Innehåller target
        for c in candidates:
            if target_lower in c.lower() or c.lower() in target_lower:
                return c

        # Gemensam delsekvens
        best_score = 0
        best_match = None
        for c in candidates:
            score = sum(1 for a, b in zip(target_lower, c.lower()) if a == b)
            score /= max(len(target), len(c))
            if score > best_score:
                best_score = score
                best_match = c

        return best_match if best_score > 0.4 else None

    def _reflect_async(self):
        """Auto-reflektion i bakgrundstråd — blockerar inte chatten."""
        if not REFLECTION_OK:
            return
        def _run():
            try:
                auto_reflect_if_needed(
                    session_id=self.session_id,
                    provider=self.provider,
                )
            except Exception as e:
                log.debug(f"Reflektion: {e}")
        threading.Thread(target=_run, daemon=True).start()

    def get_health_score(self) -> int:
        score = 100
        if not self.db_ok:         score -= 40
        if self.last_latency > 5:  score -= 20
        elif self.last_latency > 3: score -= 10
        ctx = self.get_context_usage_pct()
        if ctx > 90:   score -= 20
        elif ctx > 70: score -= 10
        return max(0, score)

    def get_context_usage_pct(self) -> float:
        try:
            from app.drm_memory import get_model_context_limit
            limit = get_model_context_limit(self.provider)
            return min(100.0, (self.session_input_tokens / limit) * 100) if limit else 0.0
        except Exception:
            return 0.0

    def get_status_text(self) -> str:
        cpu, ram = get_cpu_ram()
        return (
            f"⚡ Zero status\n"
            f"  Provider : {self.provider} (Gear {self._last_gear()})\n"
            f"  Databas  : {'OK ✓' if self.db_ok else 'Inte ansluten ✗'}\n"
            f"  Minnen   : {self.memory_count:,}\n"
            f"  Session  : {self.session_calls} anrop, ~{self.session_cost:.3f} kr\n"
            f"  Latens   : {self.last_latency}s\n"
            f"  Hälsa    : {self.get_health_score()}/100\n"
            f"  Uptime   : {format_uptime(self.start_time)}\n"
            f"  CPU/RAM  : {cpu} / {ram}\n"
            f"  GPU      : {get_gpu_info()}\n"
            f"  Disk     : {get_disk_info()}"
        )

    def _last_gear(self) -> str:
        try:
            ctx      = GearContext(channel="chat")
            decision = gear_select(self.last_event or "hej", ctx)
            return str(decision.gear)
        except Exception:
            return "?"

    def shutdown(self):
        """Körs vid stängning — avslutar episod och kör reflektion."""
        if self.episode_id:
            try:
                complete_episode(
                    self.episode_id,
                    outcome=f"{self.msg_count} meddelanden, "
                            f"{self.session_calls} anrop, "
                            f"{self.session_cost:.2f} SEK",
                )
            except Exception as e:
                log.warning(f"Episode-avslutning: {e}")
        if REFLECTION_OK:
            try:
                auto_reflect_if_needed(
                    session_id=self.session_id,
                    provider=self.provider,
                )
            except Exception as e:
                log.debug(f"Shutdown-reflektion: {e}")


# ── Singleton ─────────────────────────────────────────────────────────────────
# zero_web_server.py importerar denna och skapar en instans vid uppstart

_engine_instance: Optional[ZeroEngine] = None

def get_engine() -> ZeroEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = ZeroEngine()
    return _engine_instance


# ── CLI (för testning) ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import atexit
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    engine = ZeroEngine()
    atexit.register(engine.shutdown)

    print(f"\n{'='*50}")
    print("ZeroPointAI — Terminal-läge")
    print(f"Provider: {engine.provider}")
    print(f"Session:  {engine.session_id[:8]}...")
    print(f"Minnen:   {engine.memory_count:,}")
    print(f"{'='*50}\n")

    while True:
        try:
            user_input = input("Frank: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("/exit", "/quit", "exit", "quit"):
                break
            result = engine.chat(user_input)
            print(f"\nZero: {result['response']}")
            if result.get("thinking"):
                for step in result["thinking"]:
                    print(f"  {step}")
            print(f"  [{result.get('provider','?')} | "
                  f"Gear {result.get('gear','?')} | "
                  f"{result.get('latency',0):.2f}s | "
                  f"~{result.get('cost_sek',0):.3f} kr]\n")
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Fel: {e}")

    engine.shutdown()
    print("\nSession avslutad. Inget glöms.")
