"""Migration utility: convert legacy pickle vectors and facts.json to new ChromaDB format"""
import json
import logging
import pickle
from pathlib import Path

logger = logging.getLogger("JARVIS.MEMORY.MIGRATE")


def migrate_legacy_vectors(vector_file: Path, semantic_memory) -> int:
    if not vector_file.exists():
        logger.info("No legacy vector file found at %s", vector_file)
        return 0
    try:
        with open(vector_file, "rb") as f:
            vectors = pickle.load(f)
        migrated = 0
        for v in vectors:
            vid = v.get("id", "")
            text = v.get("text", "")
            metadata = v.get("metadata", {})
            if not text:
                continue
            fact_type = metadata.get("type", "observation")
            source = metadata.get("source", "legacy")
            semantic_memory.add_fact(text, fact_type=fact_type, source=source, confidence=0.8)
            migrated += 1
        logger.info("Migrated %d legacy vectors", migrated)
        return migrated
    except Exception as e:
        logger.error("Failed to migrate legacy vectors: %s", e)
        return 0


def migrate_legacy_facts(facts_file: Path, semantic_memory) -> int:
    if not facts_file.exists():
        logger.info("No legacy facts file found at %s", facts_file)
        return 0
    try:
        with open(facts_file, "r", encoding="utf-8") as f:
            raw = json.load(f)
        migrated = 0
        for k, v in raw.items():
            content = v.get("content", "")
            fact_type = v.get("fact_type", "observation")
            source = v.get("source", "legacy")
            confidence = float(v.get("confidence", 0.8))
            if not content:
                continue
            semantic_memory.add_fact(content, fact_type=fact_type, source=source, confidence=confidence)
            migrated += 1
        logger.info("Migrated %d legacy facts", migrated)
        return migrated
    except Exception as e:
        logger.error("Failed to migrate legacy facts: %s", e)
        return 0


def run_migration(data_dir: Path) -> dict:
    from jarvis_memory.semantic_memory import SemanticMemory

    vector_file = data_dir / "memory" / "vectors.pkl"
    facts_file = data_dir / "memory" / "facts.json"
    semantic = SemanticMemory()

    vectors_migrated = migrate_legacy_vectors(vector_file, semantic)
    facts_migrated = migrate_legacy_facts(facts_file, semantic)

    return {"vectors_migrated": vectors_migrated, "facts_migrated": facts_migrated}


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd() / "jarvis_data"
    result = run_migration(data_dir)
    print(f"Migration complete: {result}")


__all__ = ["migrate_legacy_vectors", "migrate_legacy_facts", "run_migration"]
