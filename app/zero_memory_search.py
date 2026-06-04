"""
zero_memory_search — ZeroPointAI

ZERO_MODULE:    memory
ZERO_LAYER:     1
ZERO_ESSENTIAL: true
ZERO_ROLE:      Sökverktyg för Zero — söker i STONE via naturligt språk
ZERO_DEPENDS:   drm_memory.py
ZERO_USED_BY:   zero_engine.py (tool-use)
"""
# Canonical blocks injected by inject_foundation_laws.py.
# Do not edit manually. ZERO_SYSTEM.md is the source of truth.




import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta
try:
    from app.drm_memory import (
        search_memories,
        get_core_identity,
        get_knowledge,
        get_recent_memories,
        get_episodes,
        get_memory_stats,
    )
    def get_relationships(subject_name=None, limit=100):
        from app.drm_memory import execute_query
        if subject_name:
            return execute_query("""
                SELECT * FROM relationships
                WHERE is_current = TRUE
                  AND (subject_name ILIKE %s OR object_name ILIKE %s)
                ORDER BY relation_strength DESC LIMIT %s
            """, (f"%{subject_name}%", f"%{subject_name}%", limit))
        return execute_query("""
            SELECT * FROM relationships
            WHERE is_current = TRUE
            ORDER BY relation_strength DESC LIMIT %s
        """, (limit,))
except ImportError:
    from app.memory import (
        search_memories,
        get_core_identity,
        get_knowledge,
        get_relationships,
        get_recent_memories,
        get_episodes,
        get_memory_stats,
    )

log = logging.getLogger(__name__)


def search_zero_memory(
    query: str,
    memory_types: str = "all",
    limit: int = 10,
    timeframe_days: Optional[int] = None
) -> str:
    """
    Sök i Zero's kompletta minne.

    Args:
        query: Sökfras
        memory_types: "all", "raw", "core", "knowledge", "episodes"
        limit: Max antal resultat
        timeframe_days: Begränsa till senaste X dagar

    Returns:
        Formaterad sträng med resultat
    """
    results = []

    types = memory_types.lower().split(",")

    # RAW MEMORIES (konversationer)
    if "all" in types or "raw" in types:
        raw = search_memories(query, limit=limit)
        if timeframe_days:
            cutoff = datetime.now() - timedelta(days=timeframe_days)
            raw = [r for r in raw if r.get('created_at', datetime.min) >= cutoff]

        if raw:
            results.append(f"## 💬 Konversationer ({len(raw)} träffar):")
            for m in raw[:limit]:
                date = m.get('created_at', '').strftime('%Y-%m-%d %H:%M') if m.get('created_at') else '?'
                role = "Frank" if m['role'] == 'user' else "Zero"
                content = m['content'][:150] + "..." if len(m['content']) > 150 else m['content']
                results.append(f"  [{date}] {role}: {content}")

    # CORE IDENTITY
    if "all" in types or "core" in types:
        core = get_core_identity()
        matched = [c for c in core if query.lower() in c['fact_value'].lower()
                   or query.lower() in c['fact_key'].lower()]

        if matched:
            results.append(f"\n## 🎯 Core Identity ({len(matched)} träffar):")
            for c in matched[:limit]:
                results.append(f"  {c['fact_type']}.{c['fact_key']}: {c['fact_value']}")

    # KNOWLEDGE
    if "all" in types or "knowledge" in types:
        knowledge = get_knowledge()
        matched = [k for k in knowledge if query.lower() in str(k).lower()]

        if matched:
            results.append(f"\n## 📚 Kunskap ({len(matched)} träffar):")
            for k in matched[:limit]:
                results.append(f"  {k['subject']} {k['predicate']} {k['object_value']}")

    # EPISODES
    if "all" in types or "episodes" in types:
        episodes = get_episodes(limit=50)
        matched = [e for e in episodes if query.lower() in (e.get('title', '') + e.get('description', '')).lower()]

        if matched:
            results.append(f"\n## 📖 Episoder ({len(matched)} träffar):")
            for e in matched[:limit]:
                date = e['started_at'].strftime('%Y-%m-%d') if e.get('started_at') else '?'
                results.append(f"  [{date}] {e['title']}")

    if not results:
        return f"❌ Inga resultat för '{query}'"

    return "\n".join(results)


def get_zero_stats() -> str:
    """Hämtar statistik om Zero's minne."""
    stats = get_memory_stats()
    lines = ["## 📊 Zero's Minnesstatistik:"]
    for key, value in stats.items():
        lines.append(f"  {key}: {value:,}" if isinstance(value, int) else f"  {key}: {value}")
    return "\n".join(lines)
