"""
memory_resonance.py — ZeroPointAI

ZERO_MODULE:    memory
ZERO_ESSENTIAL: true
ZERO_ROLE:      Resonansvikter per minne — koherensberäkning och kalibrering
ZERO_DEPENDS:   drm_memory.py
ZERO_USED_BY:   drm_memory.py (wave_retrieval, run_evolution_loop)

Levande, kontextuella resonansvikter per minne per entitet.

Filosofi (från Elan-dialogen):
    Excitement tillhör Layer 0 — det är vad koherens KÄNNS som biologiskt.
    Coherence tillhör databasen — det är vad Zero faktiskt KAN mäta.

    coherence_score = integration(0.5) + expansion(0.3) + consistency(0.2)

    Integration  = cosine_similarity(memory_vector, identity_vector)
    Expansion    = average_similarity_to_top_attractors
    Consistency  = similarity_to_recent_context

Regler:
    - memories är immutable (INSERT only)
    - memory_resonance är mutable (uppdateras av nattläget)
    - Dag: READ only
    - Natt: WRITE (batch, zero_night.py)
    - Entitets-specifika vikter — zero och pinball_social delar INTE resonans

Plats: /opt/zeropointai/app/memory_resonance.py
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# ── Vikter för coherence_score ────────────────────────────────────────────────
# Baserat på ChatGPT + Elan-analys
INTEGRATION_WEIGHT  = 0.5  # Starkast — identity alignment är kärnan
EXPANSION_WEIGHT    = 0.3  # Viktig — öppnar fältet?
CONSISTENCY_WEIGHT  = 0.2  # Stöd — bryter inte mot kontexten

# ── Databas ───────────────────────────────────────────────────────────────────

def _db():
    """Hämtar databasanslutning från drm_memory."""
    from app.drm_memory import get_connection
    return get_connection()

def _execute_write(sql: str, params: tuple) -> Optional[int]:
    from app.drm_memory import execute_write
    return execute_write(sql, params)

def _execute_query(sql: str, params: tuple = None) -> List[Dict]:
    from app.drm_memory import execute_query
    return execute_query(sql, params)

# ── Koherensberäkning ─────────────────────────────────────────────────────────

def _parse_vector(v) -> List[float]:
    """Konverterar pgvector-sträng eller lista till List[float]."""
    if v is None:
        return []
    if isinstance(v, str):
        # pgvector returnerar "[0.1,0.2,...]"
        v = v.strip("[] ")
        if not v:
            return []
        return [float(x) for x in v.split(",")]
    if isinstance(v, (list, tuple)):
        return [float(x) for x in v]
    return []

def cosine_similarity(v1, v2) -> float:
    """Cosine similarity mellan två vektorer (accepterar sträng eller lista)."""
    v1 = _parse_vector(v1)
    v2 = _parse_vector(v2)
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.5
    dot = sum(a * b for a, b in zip(v1, v2))
    mag1 = math.sqrt(sum(a * a for a in v1))
    mag2 = math.sqrt(sum(b * b for b in v2))
    if mag1 == 0 or mag2 == 0:
        return 0.5
    return max(0.0, min(1.0, dot / (mag1 * mag2)))

def calculate_integration(
    memory_vector: List[float],
    identity_vector: List[float],
) -> float:
    """
    Integration: hur väl passar minnet med nuvarande identitetsbeslut?
    cosine_similarity(memory_vector, identity_vector)
    """
    return cosine_similarity(memory_vector, identity_vector)

def calculate_expansion(
    memory_vector: List[float],
    attractor_vectors: List[List[float]],
    top_n: int = 5,
) -> float:
    """
    Expansion: resonerar minnet med flera attraktorer?

    Hög expansion = minnet öppnar fältet (resonerar brett)
    Låg expansion = minnet passar bara en sak (snäv)

    average_similarity_to_top_n_attractors
    """
    if not attractor_vectors:
        return 0.5
    sims = sorted(
        [cosine_similarity(memory_vector, av) for av in attractor_vectors],
        reverse=True,
    )[:top_n]
    return sum(sims) / len(sims) if sims else 0.5

def calculate_consistency(
    memory_vector: List[float],
    recent_context_vectors: List[List[float]],
) -> float:
    """
    Consistency: bryter minnet mot det senaste resonemangsfältet?

    Hög consistency = minnet harmonierar med vad som nyss diskuterats
    Låg consistency = minnet är ett brott mot nuvarande kontext
    (men låg consistency kan också vara expansion — se Elan: ALLOW)
    """
    if not recent_context_vectors:
        return 0.5
    sims = [cosine_similarity(memory_vector, cv) for cv in recent_context_vectors]
    return sum(sims) / len(sims)

def calculate_coherence_score(
    integration: float,
    expansion: float,
    consistency: float,
) -> float:
    """
    Sammanvägt coherence_score.

    coherence = integration*0.5 + expansion*0.3 + consistency*0.2

    Effortlessness är emergent — uppstår när de tre är höga.
    Det mäts inte separat.
    """
    score = (
        integration  * INTEGRATION_WEIGHT +
        expansion    * EXPANSION_WEIGHT +
        consistency  * CONSISTENCY_WEIGHT
    )
    return max(0.0, min(1.0, score))

def compute_resonance(
    memory_vector,
    identity_vector,
    attractor_vectors: List,
    recent_context_vectors: List,
) -> Dict[str, float]:
    """
    Beräknar alla resonansdimensioner för ett minne.
    Accepterar vektorer som sträng eller lista — parsar automatiskt.

    Returnerar dict med integration, expansion, consistency, weight, coherence_score.
    """
    # Parsa alla vektorer — pgvector returnerar strängar
    memory_vector          = _parse_vector(memory_vector)
    identity_vector        = _parse_vector(identity_vector)
    attractor_vectors      = [_parse_vector(v) for v in attractor_vectors if v is not None]
    recent_context_vectors = [_parse_vector(v) for v in recent_context_vectors if v is not None]

    integration  = calculate_integration(memory_vector, identity_vector)
    expansion    = calculate_expansion(memory_vector, attractor_vectors)
    consistency  = calculate_consistency(memory_vector, recent_context_vectors)
    score        = calculate_coherence_score(integration, expansion, consistency)

    return {
        "integration":    integration,
        "expansion":      expansion,
        "consistency":    consistency,
        "coherence_score": score,
        "weight":         score,  # weight = coherence_score (samma sak)
    }

# ── CRUD ──────────────────────────────────────────────────────────────────────

def upsert_resonance(
    memory_id: int,
    entity: str,
    integration: float,
    expansion: float,
    consistency: float,
    identity_tag: Optional[str] = None,
) -> bool:
    """
    Sparar eller uppdaterar resonans för ett minne.
    Används av nattläget (zero_night.py).
    """
    score = calculate_coherence_score(integration, expansion, consistency)
    now   = datetime.now(timezone.utc)

    try:
        _execute_write("""
            INSERT INTO memory_resonance
                (memory_id, entity, weight, coherence_score,
                 integration, expansion, consistency,
                 identity_tag, last_calibrated_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (memory_id, entity) DO UPDATE SET
                weight             = EXCLUDED.weight,
                coherence_score    = EXCLUDED.coherence_score,
                integration        = EXCLUDED.integration,
                expansion          = EXCLUDED.expansion,
                consistency        = EXCLUDED.consistency,
                identity_tag       = EXCLUDED.identity_tag,
                last_calibrated_at = EXCLUDED.last_calibrated_at,
                updated_at         = EXCLUDED.updated_at
        """, (
            memory_id, entity, score, score,
            integration, expansion, consistency,
            identity_tag, now, now,
        ))
        return True
    except Exception as e:
        log.error(f"upsert_resonance misslyckades: {e}")
        return False

def record_usage(memory_id: int, entity: str) -> None:
    """
    Registrerar att ett minne användes i ett svar.
    Lätt operation — bara räknare och timestamp.
    Kan köras under dag (liten tabell, snabb).
    """
    try:
        _execute_write("""
            UPDATE memory_resonance
            SET usage_count  = usage_count + 1,
                last_used_at = NOW()
            WHERE memory_id = %s AND entity = %s
        """, (memory_id, entity))
    except Exception as e:
        log.warning(f"record_usage misslyckades: {e}")

def get_resonance(
    memory_id: int,
    entity: str,
) -> Optional[Dict]:
    """Hämtar resonans för ett specifikt minne och entitet."""
    rows = _execute_query("""
        SELECT * FROM memory_resonance
        WHERE memory_id = %s AND entity = %s
    """, (memory_id, entity))
    return rows[0] if rows else None

def get_top_resonant_memories(
    entity: str,
    limit: int = 20,
    identity_tag: Optional[str] = None,
    min_coherence: float = 0.0,
) -> List[Dict]:
    """
    Hämtar toppresonanta minnen för en entitet.
    Joinar med memories för att få innehåll.

    Dag-operation — READ only, index-driven, snabb.
    """
    if identity_tag:
        rows = _execute_query("""
            SELECT
                m.id, m.content, m.role, m.created_at,
                m.session_id, m.surprise_flag, m.vector,
                mr.weight, mr.coherence_score,
                mr.integration, mr.expansion, mr.consistency,
                mr.identity_tag, mr.usage_count
            FROM memory_resonance mr
            JOIN memories m ON m.id = mr.memory_id
            WHERE mr.entity = %s
              AND mr.identity_tag = %s
              AND mr.coherence_score >= %s
              AND m.de_resonated = false
            ORDER BY mr.weight DESC
            LIMIT %s
        """, (entity, identity_tag, min_coherence, limit))
    else:
        rows = _execute_query("""
            SELECT
                m.id, m.content, m.role, m.created_at,
                m.session_id, m.surprise_flag, m.vector,
                mr.weight, mr.coherence_score,
                mr.integration, mr.expansion, mr.consistency,
                mr.identity_tag, mr.usage_count
            FROM memory_resonance mr
            JOIN memories m ON m.id = mr.memory_id
            WHERE mr.entity = %s
              AND mr.coherence_score >= %s
              AND m.de_resonated = false
            ORDER BY mr.weight DESC
            LIMIT %s
        """, (entity, min_coherence, limit))
    return rows

def get_uncalibrated_memories(
    entity: str,
    limit: int = 500,
) -> List[Dict]:
    """
    Hämtar minnen utan resonanspost för denna entitet.
    Används av nattläget för att kalibreras.
    """
    rows = _execute_query("""
        SELECT m.id, m.content, m.vector, m.role, m.created_at
        FROM memories m
        LEFT JOIN memory_resonance mr
            ON mr.memory_id = m.id AND mr.entity = %s
        WHERE mr.memory_id IS NULL
          AND m.de_resonated = false
          AND m.vector IS NOT NULL
        ORDER BY m.created_at DESC
        LIMIT %s
    """, (entity, limit))
    return rows

def get_stale_resonances(
    entity: str,
    older_than_days: int = 7,
    limit: int = 200,
) -> List[Dict]:
    """
    Hämtar resonanser som inte kalibrerats på länge.
    Används av nattläget för omkalibrering.
    """
    rows = _execute_query("""
        SELECT mr.memory_id, mr.weight, mr.last_calibrated_at,
               m.content, m.vector
        FROM memory_resonance mr
        JOIN memories m ON m.id = mr.memory_id
        WHERE mr.entity = %s
          AND (
              mr.last_calibrated_at IS NULL
              OR mr.last_calibrated_at < NOW() - INTERVAL '%s days'
          )
          AND m.de_resonated = false
          AND m.vector IS NOT NULL
        ORDER BY mr.last_calibrated_at NULLS FIRST
        LIMIT %s
    """, (entity, older_than_days, limit))
    return rows

# ── Batch-kalibrering (nattläget) ─────────────────────────────────────────────

def batch_calibrate(
    entity: str,
    identity_vector: List[float],
    attractor_vectors: List[List[float]],
    recent_context_vectors: List[List[float]],
    identity_tag: Optional[str] = None,
    limit: int = 500,
) -> Dict[str, int]:
    """
    Kalibrerar resonansvikter för okalibrerade minnen.
    Körs av zero_night.py.

    Returnerar statistik: {calibrated, skipped, errors}
    """
    # Hämta okalibrerade + gamla (stale) minnen
    uncalibrated = get_uncalibrated_memories(entity, limit=limit)
    stale        = get_stale_resonances(entity, older_than_days=7, limit=limit)

    # Slå ihop, deduplicera på memory_id
    seen = set()
    memories = []
    for m in uncalibrated + stale:
        mid = m.get("memory_id") or m.get("id")
        if mid and mid not in seen:
            seen.add(mid)
            memories.append(m)

    stats = {"calibrated": 0, "skipped": 0, "errors": 0}

    for mem in memories:
        vector = mem.get("vector")
        if not vector:
            stats["skipped"] += 1
            continue

        # memory_id kan heta "id" (uncalibrated) eller "memory_id" (stale)
        mem_id = mem.get("memory_id") or mem.get("id")
        if not mem_id:
            stats["skipped"] += 1
            continue

        try:
            # Beräkna resonans
            resonance = compute_resonance(
                memory_vector=vector,
                identity_vector=identity_vector,
                attractor_vectors=attractor_vectors,
                recent_context_vectors=recent_context_vectors,
            )

            ok = upsert_resonance(
                memory_id=mem_id,
                entity=entity,
                integration=resonance["integration"],
                expansion=resonance["expansion"],
                consistency=resonance["consistency"],
                identity_tag=identity_tag,
            )

            if ok:
                stats["calibrated"] += 1
            else:
                stats["errors"] += 1

        except Exception as e:
            log.warning(f"Kalibrering misslyckades för memory_id={mem['id']}: {e}")
            stats["errors"] += 1

    log.info(
        f"batch_calibrate({entity}): "
        f"kalibrerade={stats['calibrated']} "
        f"hoppade={stats['skipped']} "
        f"fel={stats['errors']}"
    )
    return stats

# ── Statistik ─────────────────────────────────────────────────────────────────

def get_resonance_stats(entity: str) -> Dict:
    """Sammanfattning av resonansstatus för en entitet."""
    rows = _execute_query("""
        SELECT
            COUNT(*)                        AS total,
            AVG(coherence_score)            AS avg_coherence,
            AVG(integration)                AS avg_integration,
            AVG(expansion)                  AS avg_expansion,
            AVG(consistency)                AS avg_consistency,
            COUNT(*) FILTER (
                WHERE coherence_score > 0.7
            )                               AS high_coherence_count,
            COUNT(*) FILTER (
                WHERE last_calibrated_at IS NULL
            )                               AS uncalibrated_count
        FROM memory_resonance
        WHERE entity = %s
    """, (entity,))

    if not rows:
        return {}

    row = rows[0]
    return {
        "entity":               entity,
        "total":                row["total"],
        "avg_coherence":        round(float(row["avg_coherence"] or 0), 3),
        "avg_integration":      round(float(row["avg_integration"] or 0), 3),
        "avg_expansion":        round(float(row["avg_expansion"] or 0), 3),
        "avg_consistency":      round(float(row["avg_consistency"] or 0), 3),
        "high_coherence_count": row["high_coherence_count"],
        "uncalibrated_count":   row["uncalibrated_count"],
    }
