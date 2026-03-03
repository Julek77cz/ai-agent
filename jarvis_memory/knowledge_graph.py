"""Knowledge Graph using NetworkX for entity/relationship storage"""
import json
import logging
import threading
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from jarvis_config import KG_FILE

logger = logging.getLogger("JARVIS.MEMORY.KG")

ENTITY_TYPES = {"person", "place", "thing", "concept", "event"}
RELATION_TYPES = {"knows", "prefers", "owns", "mentioned", "related_to", "is_a", "has", "located_in"}


@dataclass
class Entity:
    id: str
    name: str
    entity_type: str
    aliases: List[str] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Relation:
    source_id: str
    target_id: str
    relation_type: str
    weight: float = 1.0
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class KnowledgeGraph:
    def __init__(self):
        self._lock = threading.RLock()
        self._entities: Dict[str, Entity] = {}
        self._relations: List[Relation] = []
        self._graph = None
        self._init_graph()
        self._load()

    def _init_graph(self) -> None:
        try:
            import networkx as nx
            self._graph = nx.DiGraph()
        except ImportError:
            logger.warning("networkx not available - KG operating without graph traversal")
            self._graph = None

    def _load(self) -> None:
        try:
            if Path(KG_FILE).exists():
                with open(KG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                with self._lock:
                    for e in data.get("entities", []):
                        entity = Entity(**e)
                        self._entities[entity.id] = entity
                        if self._graph is not None:
                            self._graph.add_node(entity.id, **asdict(entity))
                    for r in data.get("relations", []):
                        relation = Relation(**r)
                        self._relations.append(relation)
                        if self._graph is not None:
                            self._graph.add_edge(
                                relation.source_id,
                                relation.target_id,
                                relation_type=relation.relation_type,
                                weight=relation.weight,
                            )
                logger.info("Loaded KG: %d entities, %d relations", len(self._entities), len(self._relations))
        except Exception as e:
            logger.warning("Failed to load knowledge graph: %s", e)

    def _save(self) -> None:
        try:
            Path(KG_FILE).parent.mkdir(parents=True, exist_ok=True)
            with open(KG_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "entities": [asdict(e) for e in self._entities.values()],
                        "relations": [asdict(r) for r in self._relations],
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as e:
            logger.warning("Failed to save knowledge graph: %s", e)

    def add_entity(
        self,
        name: str,
        entity_type: str = "concept",
        aliases: Optional[List[str]] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Entity:
        entity_type = entity_type if entity_type in ENTITY_TYPES else "concept"
        import hashlib
        eid = hashlib.md5(name.lower().encode()).hexdigest()[:12]
        with self._lock:
            if eid in self._entities:
                existing = self._entities[eid]
                if aliases:
                    existing.aliases = list(set(existing.aliases + aliases))
                if attributes:
                    existing.attributes.update(attributes)
                self._save()
                return existing
            entity = Entity(
                id=eid,
                name=name,
                entity_type=entity_type,
                aliases=aliases or [],
                attributes=attributes or {},
            )
            self._entities[eid] = entity
            if self._graph is not None:
                self._graph.add_node(eid, **asdict(entity))
        self._save()
        return entity

    def add_relation(
        self,
        source_name: str,
        relation_type: str,
        target_name: str,
        weight: float = 1.0,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Optional[Relation]:
        relation_type = relation_type if relation_type in RELATION_TYPES else "related_to"
        source = self.find_entity(source_name)
        target = self.find_entity(target_name)
        if source is None or target is None:
            return None
        with self._lock:
            for r in self._relations:
                if r.source_id == source.id and r.target_id == target.id and r.relation_type == relation_type:
                    r.weight = max(r.weight, weight)
                    self._save()
                    return r
            relation = Relation(
                source_id=source.id,
                target_id=target.id,
                relation_type=relation_type,
                weight=weight,
                attributes=attributes or {},
            )
            self._relations.append(relation)
            if self._graph is not None:
                self._graph.add_edge(source.id, target.id, relation_type=relation_type, weight=weight)
        self._save()
        return relation

    def find_entity(self, name: str) -> Optional[Entity]:
        name_lower = name.lower()
        with self._lock:
            for entity in self._entities.values():
                if entity.name.lower() == name_lower:
                    return entity
                if any(a.lower() == name_lower for a in entity.aliases):
                    return entity
        return None

    def get_entity_by_id(self, eid: str) -> Optional[Entity]:
        with self._lock:
            return self._entities.get(eid)

    def get_relations_for(self, entity_name: str) -> List[Tuple[str, str, str]]:
        entity = self.find_entity(entity_name)
        if entity is None:
            return []
        results = []
        with self._lock:
            for r in self._relations:
                if r.source_id == entity.id:
                    target = self._entities.get(r.target_id)
                    if target:
                        results.append((entity.name, r.relation_type, target.name))
                elif r.target_id == entity.id:
                    source = self._entities.get(r.source_id)
                    if source:
                        results.append((source.name, r.relation_type, entity.name))
        return results

    def get_neighbors(self, entity_name: str, max_depth: int = 2) -> List[Entity]:
        if self._graph is None:
            return []
        entity = self.find_entity(entity_name)
        if entity is None:
            return []
        try:
            import networkx as nx
            reachable = set()
            for depth in range(1, max_depth + 1):
                for nid in nx.single_source_shortest_path_length(self._graph, entity.id, cutoff=depth):
                    reachable.add(nid)
            reachable.discard(entity.id)
            with self._lock:
                return [self._entities[nid] for nid in reachable if nid in self._entities]
        except Exception as e:
            logger.warning("get_neighbors failed: %s", e)
            return []

    def get_path(self, source_name: str, target_name: str) -> List[str]:
        if self._graph is None:
            return []
        source = self.find_entity(source_name)
        target = self.find_entity(target_name)
        if source is None or target is None:
            return []
        try:
            import networkx as nx
            path = nx.shortest_path(self._graph, source.id, target.id)
            with self._lock:
                return [self._entities[nid].name for nid in path if nid in self._entities]
        except Exception:
            return []

    def remove_entity(self, entity_name: str) -> bool:
        entity = self.find_entity(entity_name)
        if entity is None:
            return False
        with self._lock:
            del self._entities[entity.id]
            self._relations = [r for r in self._relations if r.source_id != entity.id and r.target_id != entity.id]
            if self._graph is not None and entity.id in self._graph:
                self._graph.remove_node(entity.id)
        self._save()
        return True

    def all_entities(self) -> List[Entity]:
        with self._lock:
            return list(self._entities.values())

    def entity_count(self) -> int:
        with self._lock:
            return len(self._entities)

    def relation_count(self) -> int:
        with self._lock:
            return len(self._relations)


__all__ = ["KnowledgeGraph", "Entity", "Relation", "ENTITY_TYPES", "RELATION_TYPES"]
