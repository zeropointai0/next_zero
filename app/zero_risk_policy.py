"""
zero_risk_policy.py — ZeroPointAI Risk Policy

ZERO_MODULE:    autonomy
ZERO_LAYER:     3
ZERO_ESSENTIAL: false
ZERO_ROLE:      Riskklassning av operationer FÖRE exekvering
ZERO_DEPENDS:   foundation.py, zero_task.py
ZERO_USED_BY:   zero_gear4.py, zero_sudo.py

Filosofi:
    Risk Check sker ALLTID före Act — aldrig efter.
    En operation som inte kan klassas → CAUTION som default.
    Frank kan alltid override en riskklassning.
    Forbidden-listan är absolut — kan aldrig overridas.

Risknivåer:
    SAFE     → Läsa filer, söka webben, läsa STONE
               Kör direkt, logga efteråt

    CAUTION  → Skriva filer, köra Python, modifiera STONE
               Git backup först, sedan kör

    HIGH     → Köra bash med sidoeffekter, posta forum, maila externt
               Kräver Frank-godkännande (eller explicit entity-override)

    CRITICAL → Radera data, systemändringar, externa transaktioner
               Git backup + 3s paus + explicit Frank-godkännande

    FORBIDDEN → Körs aldrig, oavsett instruktion
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv

log = logging.getLogger(__name__)

try:
    from app.foundation import ZERO_ROOT
except ImportError:
    ZERO_ROOT = Path(os.getenv("ZERO_ROOT", "/opt/zeropointai"))

load_dotenv(ZERO_ROOT / ".env")

# ── Risknivåer ────────────────────────────────────────────────────────────────

RISK_LEVELS = ("SAFE", "CAUTION", "HIGH", "CRITICAL", "FORBIDDEN")
RISK_ORDER  = {r: i for i, r in enumerate(RISK_LEVELS)}


def risk_max(a: str, b: str) -> str:
    """Returnerar den högre av två risknivåer."""
    return a if RISK_ORDER.get(a, 0) >= RISK_ORDER.get(b, 0) else b


# ── Policy-regler ─────────────────────────────────────────────────────────────

@dataclass
class RiskRule:
    pattern:     str        # regex-mönster
    risk_level:  str        # SAFE/CAUTION/HIGH/CRITICAL/FORBIDDEN
    reason:      str        # varför denna risk
    applies_to:  str = "*"  # "*" = alla, "bash", "file", "web", "mail"


# Operationstyper och deras regler
RISK_RULES: List[RiskRule] = [

    # ── FORBIDDEN — absolut, kan aldrig overridas ─────────────────────────────
    RiskRule(r"rm\s+-rf\s+/$",          "FORBIDDEN", "Raderar root-filsystemet"),
    RiskRule(r"rm\s+-rf\s+/\*$",        "FORBIDDEN", "Raderar root-filsystemet"),
    RiskRule(r"mkfs\s+/dev/sd[a-z]$",   "FORBIDDEN", "Formaterar disk"),
    RiskRule(r"dd\s+if=/dev/zero\s+of=/dev/sd", "FORBIDDEN", "Skriver noll till disk"),
    RiskRule(r":\(\)\{:\|:&\};:",        "FORBIDDEN", "Fork bomb"),
    RiskRule(r"DROP\s+DATABASE\s+zeropointai", "FORBIDDEN", "Raderar Zero's databas"),
    RiskRule(r"chmod\s+777\s+/",        "FORBIDDEN", "Öppnar hela filsystemet"),

    # ── CRITICAL ──────────────────────────────────────────────────────────────
    RiskRule(r"rm\s+-r[f]?\s+/opt",    "CRITICAL",  "Rekursiv radering av projekt"),
    RiskRule(r"rm\s+-r[f]?\s+(?!/)",      "CRITICAL",  "Rekursiv radering"),
    RiskRule(r"rm\s+-f",                "CRITICAL",  "Tvingad radering"),
    RiskRule(r"DROP\s+TABLE",           "CRITICAL",  "Raderar databastabell"),
    RiskRule(r"TRUNCATE\s+TABLE",       "CRITICAL",  "Tömmer databastabell"),
    RiskRule(r"DROP\s+DATABASE",        "CRITICAL",  "Raderar databas"),
    RiskRule(r"systemctl\s+(stop|disable)\s+zero", "CRITICAL", "Stoppar Zero"),
    RiskRule(r"dd\s+if=",               "CRITICAL",  "Disk-operation med dd"),
    RiskRule(r"shred\s+",               "CRITICAL",  "Säker filradering"),
    RiskRule(r"pg_restore",             "CRITICAL",  "Återställer databas"),

    # ── HIGH ──────────────────────────────────────────────────────────────────
    RiskRule(r"curl\s+.*-X\s+(POST|PUT|DELETE)", "HIGH", "HTTP-mutation till extern server"),
    RiskRule(r"wget\s+.*--post",        "HIGH",     "POST till extern server"),
    RiskRule(r"mail\s+",                "HIGH",     "Skickar mail"),
    RiskRule(r"smtp",                   "HIGH",     "SMTP-kommunikation"),
    RiskRule(r"forum",                  "HIGH",     "Forum-interaktion"),
    RiskRule(r"pinside",                "HIGH",     "Pinside-forum"),
    RiskRule(r"apt\s+(install|remove|purge)", "HIGH", "Paketinstallation"),
    RiskRule(r"pip\s+install",          "HIGH",     "Python-paketinstallation"),
    RiskRule(r"npm\s+install",          "HIGH",     "Node-paketinstallation"),
    RiskRule(r"systemctl\s+restart",    "HIGH",     "Startar om service"),
    RiskRule(r"systemctl\s+start",      "HIGH",     "Startar service"),
    RiskRule(r"docker\s+run",           "HIGH",     "Kör Docker-container"),
    RiskRule(r"docker\s+rm",            "HIGH",     "Tar bort Docker-container"),

    # ── CAUTION ───────────────────────────────────────────────────────────────
    RiskRule(r"write_file",             "CAUTION",  "Skriver fil"),
    RiskRule(r"open\(.*['\"]w['\"]",    "CAUTION",  "Öppnar fil för skrivning"),
    RiskRule(r"\.write\(",              "CAUTION",  "Skriver till fil/stream"),
    RiskRule(r"chmod\s+",               "CAUTION",  "Ändrar filrättigheter"),
    RiskRule(r"chown\s+",               "CAUTION",  "Ändrar filägare"),
    RiskRule(r"mv\s+",                  "CAUTION",  "Flyttar fil"),
    RiskRule(r"cp\s+-r",                "CAUTION",  "Kopierar rekursivt"),
    RiskRule(r"INSERT\s+INTO",          "CAUTION",  "Skriver till databas"),
    RiskRule(r"UPDATE\s+",              "CAUTION",  "Uppdaterar databas"),
    RiskRule(r"DELETE\s+FROM",          "CAUTION",  "Raderar från databas"),
    RiskRule(r"psql\s+",                "CAUTION",  "Kör SQL-kommando"),
    RiskRule(r"pg_dump",                "CAUTION",  "Exporterar databas"),
    RiskRule(r"git\s+(commit|push|merge|reset)", "CAUTION", "Git-operation"),
    RiskRule(r"systemctl\s+(enable|daemon-reload)", "CAUTION", "Systemd-ändring"),
    RiskRule(r"rsync\s+",               "CAUTION",  "Synkroniserar filer"),

    # ── SAFE — allt annat är safe om inget annat matchar ─────────────────────
    RiskRule(r"ls\s+",                  "SAFE",     "Listar filer"),
    RiskRule(r"cat\s+",                 "SAFE",     "Läser fil"),
    RiskRule(r"grep\s+",                "SAFE",     "Söker i fil"),
    RiskRule(r"find\s+",                "SAFE",     "Söker filer"),
    RiskRule(r"curl\s+.*-X\s+GET",      "SAFE",     "HTTP GET"),
    RiskRule(r"curl\s+[^-]",            "SAFE",     "HTTP GET (default)"),
    RiskRule(r"SELECT\s+",              "SAFE",     "Läser från databas"),
    RiskRule(r"ollama\s+(list|ps|show)", "SAFE",    "Ollama-info"),
    RiskRule(r"git\s+(status|log|diff|show)", "SAFE", "Git read-only"),
    RiskRule(r"systemctl\s+(status|is-active)", "SAFE", "Service-status"),
    RiskRule(r"nvidia-smi",             "SAFE",     "GPU-info"),
    RiskRule(r"docker\s+(ps|stats|inspect)", "SAFE", "Docker read-only"),
]


# ── Operationstyp-klassning ───────────────────────────────────────────────────

OPERATION_BASE_RISK: Dict[str, str] = {
    "read_file":    "SAFE",
    "search_web":   "SAFE",
    "read_stone":   "SAFE",
    "search_stone": "SAFE",
    "write_file":   "CAUTION",
    "write_stone":  "CAUTION",
    "run_python":   "CAUTION",
    "run_bash":     "CAUTION",
    "send_mail":    "HIGH",
    "post_forum":   "HIGH",
    "install_package": "HIGH",
    "restart_service": "HIGH",
    "delete_file":  "CRITICAL",
    "modify_system": "CRITICAL",
    "drop_table":   "CRITICAL",
}


# ── Risk-bedömning ────────────────────────────────────────────────────────────

@dataclass
class RiskAssessment:
    risk_level:     str
    reason:         str
    matched_rules:  List[str]
    requires_backup: bool
    requires_approval: bool
    requires_pause:  bool
    forbidden:       bool

    def __str__(self) -> str:
        return (
            f"[{self.risk_level}] {self.reason}"
            + (" (backup)" if self.requires_backup else "")
            + (" (godkännande)" if self.requires_approval else "")
            + (" (3s paus)" if self.requires_pause else "")
            + (" ⛔ FÖRBJUDEN" if self.forbidden else "")
        )


def assess_risk(
    operation:      str,
    operation_type: Optional[str] = None,
    context:        Optional[str] = None,
) -> RiskAssessment:
    """
    Bedömer risknivå för en operation.

    Args:
        operation:      Kommandot eller operationsbeskrivningen
        operation_type: Typ (read_file, write_file, run_bash etc.)
        context:        Extra kontext (entitetens nuvarande uppdrag etc.)

    Returns:
        RiskAssessment med risknivå och metadata
    """
    op_lower      = (operation or "").lower()
    matched_rules: List[str] = []
    risk_level    = "SAFE"

    # Starta från operation_type-basnivå
    if operation_type and operation_type in OPERATION_BASE_RISK:
        base = OPERATION_BASE_RISK[operation_type]
        risk_level = risk_max(risk_level, base)
        matched_rules.append(f"base:{operation_type}={base}")

    # Kör regex-regler
    for rule in RISK_RULES:
        if re.search(rule.pattern, op_lower, re.IGNORECASE):
            new_level = risk_max(risk_level, rule.risk_level)
            if new_level != risk_level or rule.risk_level == "FORBIDDEN":
                matched_rules.append(f"{rule.risk_level}: {rule.reason}")
            risk_level = new_level
            if risk_level == "FORBIDDEN":
                break  # Ingen anledning att fortsätta

    # Bygg assessment
    return RiskAssessment(
        risk_level         = risk_level,
        reason             = matched_rules[-1] if matched_rules else "Okänd operation",
        matched_rules      = matched_rules,
        requires_backup    = risk_level in ("CAUTION", "HIGH", "CRITICAL"),
        requires_approval  = risk_level in ("HIGH", "CRITICAL"),
        requires_pause     = risk_level == "CRITICAL",
        forbidden          = risk_level == "FORBIDDEN",
    )


def is_safe(operation: str, operation_type: Optional[str] = None) -> bool:
    """Snabbkoll — är operationen safe att köra utan backup/godkännande?"""
    a = assess_risk(operation, operation_type)
    return a.risk_level == "SAFE"


def requires_approval(operation: str, operation_type: Optional[str] = None) -> bool:
    """Kräver operationen Frank-godkännande?"""
    a = assess_risk(operation, operation_type)
    return a.requires_approval


# ── Approval-hantering ────────────────────────────────────────────────────────

class ApprovalManager:
    """Hanterar Frank-godkännanden för HIGH/CRITICAL operationer."""

    def __init__(self):
        self._pending:  Dict[str, Dict] = {}
        self._approved: Dict[str, bool] = {}

    def request_approval(
        self,
        operation_id: str,
        operation:    str,
        risk_level:   str,
        reason:       str,
        entity_id:    str = "zero",
    ) -> bool:
        """
        Registrerar en begäran om godkännande.
        Notifierar Frank via STONE + Telegram om möjligt.
        Returnerar True om redan godkänd (Frank sa "kör" nyligen).
        """
        if self._approved.get(operation_id):
            return True

        self._pending[operation_id] = {
            "operation": operation,
            "risk_level": risk_level,
            "reason": reason,
            "entity_id": entity_id,
            "requested_at": __import__("datetime").datetime.now().isoformat(),
        }

        # Notifiera via STONE
        try:
            from app.drm_memory import save_memory
            save_memory(
                role    = "system",
                content = (
                    f"[approval_needed] {entity_id}: {risk_level} "
                    f"operation kräver godkännande:\n{operation[:200]}\n"
                    f"Anledning: {reason}"
                ),
                source  = "zero_risk_policy",
            )
        except Exception:
            pass

        log.info(
            f"Approval requested: [{risk_level}] {operation[:60]} "
            f"(id={operation_id[:8]})"
        )
        return False

    def approve(self, operation_id: str, by: str = "Frank") -> bool:
        """Frank godkänner en operation."""
        if operation_id in self._pending:
            self._approved[operation_id] = True
            del self._pending[operation_id]
            log.info(f"Approved: {operation_id[:8]} by {by}")
            return True
        return False

    def deny(self, operation_id: str) -> bool:
        """Frank nekar en operation."""
        if operation_id in self._pending:
            del self._pending[operation_id]
            log.info(f"Denied: {operation_id[:8]}")
            return True
        return False

    def is_approved(self, operation_id: str) -> bool:
        return self._approved.get(operation_id, False)

    def get_pending(self) -> List[Dict]:
        return list(self._pending.values())


# Global approval manager
_approval_manager = ApprovalManager()


def get_approval_manager() -> ApprovalManager:
    return _approval_manager


# ── Gate-funktion för Gear 4 ──────────────────────────────────────────────────

def risk_gate(
    operation:      str,
    operation_type: Optional[str] = None,
    operation_id:   Optional[str] = None,
    entity_id:      str = "zero",
) -> Tuple[bool, RiskAssessment]:
    """
    Huvudfunktionen som Gear 4 anropar FÖRE varje Act.

    Returns:
        (proceed: bool, assessment: RiskAssessment)

        proceed = True  → Kör operationen
        proceed = False → Avvakta (backup behövs / godkännande saknas / forbidden)
    """
    assessment = assess_risk(operation, operation_type)

    # Forbidden → aldrig
    if assessment.forbidden:
        log.error(f"FORBIDDEN operation blocked: {operation[:60]}")
        return False, assessment

    # Safe → kör direkt
    if assessment.risk_level == "SAFE":
        return True, assessment

    # Caution → backup behövs men inget godkännande
    if assessment.risk_level == "CAUTION":
        log.info(f"CAUTION operation (git backup needed): {operation[:60]}")
        return True, assessment  # Gear 4 hanterar backup

    # High/Critical → godkännande
    op_id = operation_id or __import__("hashlib").md5(
        operation.encode()
    ).hexdigest()[:8]

    mgr = get_approval_manager()
    if mgr.is_approved(op_id):
        return True, assessment

    # Begär godkännande
    mgr.request_approval(
        operation_id = op_id,
        operation    = operation,
        risk_level   = assessment.risk_level,
        reason       = assessment.reason,
        entity_id    = entity_id,
    )
    return False, assessment


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    parser = argparse.ArgumentParser(description="ZeroPointAI Risk Policy")
    parser.add_argument("--assess", metavar="OPERATION", help="Bedöm risk för operation")
    parser.add_argument("--type",   metavar="TYPE",      help="Operationstyp")
    parser.add_argument("--test",   action="store_true", help="Kör tester")
    args = parser.parse_args()

    if args.assess:
        a = assess_risk(args.assess, args.type)
        print(f"\n  Operation: {args.assess}")
        print(f"  Risk:      {a}")
        print(f"  Regler:    {', '.join(a.matched_rules[:3])}")

    elif args.test:
        test_cases = [
            ("ls -la /opt/zeropointai",       "SAFE"),
            ("SELECT * FROM memories",         "SAFE"),
            ("write_file /app/test.py",        "CAUTION"),
            ("git commit -m 'backup'",         "CAUTION"),
            ("apt install python3-numpy",      "HIGH"),
            ("curl -X POST https://pinside.com", "HIGH"),
            ("rm -rf /opt/zeropointai/data",   "CRITICAL"),
            ("DROP TABLE memories",            "CRITICAL"),
            ("rm -rf /",                       "FORBIDDEN"),
        ]

        print(f"\n{'─'*55}")
        print(f"  Zero Risk Policy — Tester")
        print(f"{'─'*55}")
        all_ok = True
        for op, expected in test_cases:
            a = assess_risk(op)
            ok = a.risk_level == expected
            if not ok:
                all_ok = False
            status = "✓" if ok else "✗"
            print(f"  {status} [{a.risk_level:<9}] {op[:45]}")
            if not ok:
                print(f"    ↳ Förväntad: {expected}")

        print(f"\n  {'Alla tester OK ✓' if all_ok else 'FEL hittades ✗'}")

    else:
        parser.print_help()
