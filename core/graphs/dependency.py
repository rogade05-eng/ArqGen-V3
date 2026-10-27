"""Dependency graph (spec section 74).

Wall → Space → Electrical → CCTV → QTO → Budget → Documentation.
When Wall changes: affected descendants → incremental recalculation.
Never recalculate the whole project.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from core.errors import DomainError


@dataclass
class DependencyEdge:
    source_id: str      # the object that changed
    target_id: str      # the object that depends on it
    relation: str       # semantic label, e.g. "wall→opening"


class DependencyGraph:
    """Directed acyclic dependency graph of model objects."""

    def __init__(self) -> None:
        self._edges: Dict[str, List[DependencyEdge]] = {}
        self._reverse: Dict[str, List[DependencyEdge]] = {}

    def add_edge(self, source_id: str, target_id: str, relation: str = "depends") -> None:
        if source_id == target_id:
            raise DomainError(
                message="Un objeto no puede depender de sí mismo",
                code="ARQ-DOM-030",
                context={"object_id": source_id},
            )
        edge = DependencyEdge(source_id, target_id, relation)
        self._edges.setdefault(source_id, []).append(edge)
        self._reverse.setdefault(target_id, []).append(edge)

    def remove_object(self, object_id: str) -> None:
        for lst in (self._edges.get(object_id, []), self._reverse.get(object_id, [])):
            for edge in list(lst):
                self._discard(edge)
        self._edges.pop(object_id, None)
        self._reverse.pop(object_id, None)

    def _discard(self, edge: DependencyEdge) -> None:
        source_list = self._edges.get(edge.source_id, [])
        if edge in source_list:
            source_list.remove(edge)
        target_list = self._reverse.get(edge.target_id, [])
        if edge in target_list:
            target_list.remove(edge)

    def direct_dependents(self, object_id: str) -> List[str]:
        return [e.target_id for e in self._edges.get(object_id, [])]

    def dependencies_of(self, object_id: str) -> List[str]:
        return [e.source_id for e in self._reverse.get(object_id, [])]

    def affected_descendants(self, object_id: str, max_depth: int = 64) -> List[str]:
        """All transitive dependents of an object, BFS order, deduplicated."""
        visited: Set[str] = set()
        queue: deque[Tuple[str, int]] = deque([(object_id, 0)])
        result: List[str] = []
        while queue:
            current, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for target in self.direct_dependents(current):
                if target not in visited and target != object_id:
                    visited.add(target)
                    result.append(target)
                    queue.append((target, depth + 1))
        return result

    def topological_order(self, ids: Optional[List[str]] = None) -> List[str]:
        """Kahn topological order over the given ids (or all known)."""
        nodes = set(ids) if ids is not None else set(self._edges) | set(self._reverse)
        indegree: Dict[str, int] = {n: 0 for n in nodes}
        for source in nodes:
            for target in self.direct_dependents(source):
                if target in indegree:
                    indegree[target] += 1
        queue = deque(sorted(n for n, d in indegree.items() if d == 0))
        order: List[str] = []
        while queue:
            node = queue.popleft()
            order.append(node)
            for target in self.direct_dependents(node):
                if target in indegree:
                    indegree[target] -= 1
                    if indegree[target] == 0:
                        queue.append(target)
        if len(order) != len(nodes):
            raise DomainError(
                message="El grafo de dependencias contiene ciclos",
                code="ARQ-DOM-031",
            )
        return order

    def edge_count(self) -> int:
        return sum(len(v) for v in self._edges.values())

    def clear(self) -> None:
        self._edges.clear()
        self._reverse.clear()


__all__ = ["DependencyGraph", "DependencyEdge"]
