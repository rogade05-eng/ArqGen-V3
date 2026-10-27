"""Network Engine (spec section 25).

Modelo Network → Node / Segment / Equipment / Terminal sobre un grafo
dirigido en dirección de flujo. Funciones del spec:

    connect / disconnect   (servicio de instalaciones)
    trace()                camino upstream/downstream de un nodo
    find_path()            camino más corto (BFS, saltos)
    calculate_path()       camino de coste mínimo (Dijkstra por longitud/coste)
    validate_network()     árbol radial / convergencia a sumidero, huérfanos, bucles
    detect_dead_end()      nodos grado-1 olvidados (no terminales ni origen)

El resultado de validación usa el contrato de validación del spec 82
(VALID / VALID_WITH_WARNINGS / INVALID / BLOCKED).
"""

from __future__ import annotations

import heapq
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from core.validation.results import Finding, ValidationResult, ValidationStatus
from domain.installations import (
    SINK_KINDS, SOURCE_KINDS, InstallNode, InstallSegment, topology_of,
)

FindingFactory = Callable[[str, str, str, str], Finding]


def _finding(severity: str, code: str, message: str, object_id: str = "",
             object_type: str = "") -> Finding:
    return Finding(severity=severity, code=code, message=message,
                   object_id=object_id, object_type=object_type, source="NETWORK")


@dataclass
class NetworkGraph:
    """Directed graph in flow direction, built from nodes + segments."""

    nodes: Dict[str, InstallNode] = field(default_factory=dict)
    segments: Dict[str, InstallSegment] = field(default_factory=dict)
    adjacency: Dict[str, List[str]] = field(default_factory=dict)   # from -> [(segment_id, to)]
    reverse: Dict[str, List[str]] = field(default_factory=dict)     # to -> [(segment_id, from)]

    @classmethod
    def build(cls, nodes: List[InstallNode], segments: List[InstallSegment]) -> "NetworkGraph":
        graph = cls(nodes={n.id: n for n in nodes})
        for segment in segments:
            if segment.from_node_id not in graph.nodes or segment.to_node_id not in graph.nodes:
                continue  # dangling segment: reported by validate_network
            graph.segments[segment.id] = segment
            graph.adjacency.setdefault(segment.from_node_id, []).append(segment.to_node_id)
            graph.reverse.setdefault(segment.to_node_id, []).append(segment.from_node_id)
        return graph

    def neighbors(self, node_id: str) -> List[str]:
        return list(self.adjacency.get(node_id, []))

    def incoming(self, node_id: str) -> List[str]:
        return list(self.reverse.get(node_id, []))

    def degree(self, node_id: str) -> int:
        return len(self.adjacency.get(node_id, [])) + len(self.reverse.get(node_id, []))

    # -- spec 25: trace ---------------------------------------------------------
    def trace(self, node_id: str, topology: str = "radial_from_source") -> List[str]:
        """Path from the node towards the flow origin/sink (inclusive).

        radial_from_source : follows incoming edges upstream to the source.
        converge_to_sink   : follows outgoing edges downstream to the sink.
        """
        if node_id not in self.nodes:
            return []
        if topology == "radial_from_source":
            step = self.incoming
        else:
            step = self.neighbors
        path = [node_id]
        seen = {node_id}
        current = node_id
        while True:
            candidates = [c for c in step(current) if c not in seen]
            if not candidates:
                break
            current = candidates[0]
            path.append(current)
            seen.add(current)
        return path

    # -- spec 25: find_path -------------------------------------------------------
    def find_path(self, start_id: str, goal_id: str) -> List[str]:
        """Shortest path by number of hops (BFS). Empty if unreachable."""
        if start_id not in self.nodes or goal_id not in self.nodes:
            return []
        if start_id == goal_id:
            return [start_id]
        # Undirected traversal: real installation paths may go either way.
        queue: deque[str] = deque([start_id])
        came: Dict[str, Optional[str]] = {start_id: None}
        while queue:
            current = queue.popleft()
            for neighbor in self.neighbors(current) + self.incoming(current):
                if neighbor in came:
                    continue
                came[neighbor] = current
                if neighbor == goal_id:
                    path = [goal_id]
                    while came[path[-1]] is not None:
                        path.append(came[path[-1]])  # type: ignore[arg-type]
                    return list(reversed(path))
                queue.append(neighbor)
        return []

    # -- spec 25: calculate_path ----------------------------------------------------
    def calculate_path(self, start_id: str, goal_id: str,
                       weight: str = "length",
                       cost_fn: Optional[Callable[[InstallSegment], float]] = None
                       ) -> Tuple[List[str], float]:
        """Minimum-cost path (Dijkstra over segment weights). Undirected.

        weight: 'length' (segment length in m), 'hops' (each segment = 1) or
        'cost' (segment attrs.get('cost')). Returns (node_ids, total_cost);
        total is -1.0 when unreachable.
        """
        if start_id not in self.nodes or goal_id not in self.nodes:
            return [], -1.0
        if weight == "length":
            def default_cost(segment: InstallSegment) -> float:
                return max(segment.length_m, 1e-9)
        elif weight == "hops":
            def default_cost(segment: InstallSegment) -> float:
                return 1.0
        else:
            def default_cost(segment: InstallSegment) -> float:
                try:
                    return max(float(segment.attrs.get("cost", 1.0)), 1e-9)
                except (TypeError, ValueError):
                    return 1.0

        cost = cost_fn or default_cost
        best: Dict[str, float] = {start_id: 0.0}
        came: Dict[str, Optional[str]] = {start_id: None}
        heap: List[Tuple[float, str]] = [(0.0, start_id)]
        while heap:
            current_cost, current = heapq.heappop(heap)
            if current_cost > best.get(current, float("inf")):
                continue
            if current == goal_id:
                break
            for segment_id, neighbor in self._undirected_edges(current):
                segment = self.segments[segment_id]
                next_cost = current_cost + cost(segment)
                if next_cost < best.get(neighbor, float("inf")):
                    best[neighbor] = next_cost
                    came[neighbor] = current
                    heapq.heappush(heap, (next_cost, neighbor))
        if goal_id not in best:
            return [], -1.0
        path = [goal_id]
        while came[path[-1]] is not None:
            path.append(came[path[-1]])  # type: ignore[arg-type]
        return list(reversed(path)), round(best[goal_id], 3)

    def _undirected_edges(self, node_id: str) -> List[Tuple[str, str]]:
        edges: List[Tuple[str, str]] = []
        for other in self.adjacency.get(node_id, []):
            edges.append((self._segment_between(node_id, other), other))
        for other in self.reverse.get(node_id, []):
            edges.append((self._segment_between(other, node_id), other))
        return edges

    def _segment_between(self, from_id: str, to_id: str) -> str:
        for segment_id, segment in self.segments.items():
            if segment.from_node_id == from_id and segment.to_node_id == to_id:
                return segment_id
        return ""

    # -- spec 25: validate_network ----------------------------------------------------
    def validate_network(self, system: str, topology: str = "") -> ValidationResult:
        """Connectivity validation per spec 25 + 82."""
        result = ValidationResult()
        topo = topology or topology_of(system)
        if not self.nodes:
            result.add(_finding("WARNING", "ARQ-NET-010",
                                "La red no tiene nodos definidos todavía"))
            result.finalize()
            return result

        for segment in self.segments.values():
            if segment.from_node_id not in self.nodes or segment.to_node_id not in self.nodes:
                result.add(_finding(
                    "ERROR", "ARQ-NET-011",
                    "Tramo con nodos inexistentes en la red", segment.id, "SEGMENT"))

        sources = [n for n in self.nodes.values()
                   if n.kind in SOURCE_KINDS or (n.kind in SINK_KINDS and topo == "converge_to_sink")]
        sinks = [n for n in self.nodes.values() if n.kind in SINK_KINDS]

        if topo == "radial_from_source":
            if len(sources) == 0:
                result.add(_finding("ERROR", "ARQ-NET-012",
                                    "La red no tiene ningún nodo de origen (SOURCE/PANEL/METER/TANK)"))
            elif len(sources) > 1:
                result.add(_finding(
                    "WARNING", "ARQ-NET-013",
                    f"La red tiene {len(sources)} orígenes; se asume alimentación única por árbol",
                ))
            start = sources[0].id if sources else ""
            reach = self._reachable(start, follow=self.adjacency)
        else:
            if len(sinks) == 0:
                result.add(_finding("ERROR", "ARQ-NET-014",
                                    "La red de gravedad no tiene sumidero (OUTFALL)"))
                sinks = []
            start = sinks[0].id if sinks else ""
            reach = self._reachable(start, follow=self.reverse)

        for node in self.nodes.values():
            if node.id not in reach and node.id != start:
                label = "no alcanza el origen desde" if topo == "radial_from_source" \
                    else "no drena hacia el sumidero desde"
                result.add(_finding(
                    "ERROR", "ARQ-NET-015",
                    f"Nodo desconectado: {label} la topología de la red",
                    node.id, "NODE"))

        cycles = self._find_cycle()
        for cycle in cycles:
            result.add(_finding(
                "WARNING", "ARQ-NET-016",
                f"Bucle detectado en la red entre {len(cycle)} nodos "
                "(se esperaba topología radial en árbol)"))

        result.finalize()
        return result

    def _reachable(self, start: str, follow) -> set[str]:
        if not start:
            return set()
        seen = {start}
        queue: deque[str] = deque([start])
        while queue:
            for neighbor in follow.get(queue.popleft(), []):
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        return seen

    def _find_cycle(self) -> List[str]:
        """Detect one cycle via DFS (undirected); empty list if none."""
        color: Dict[str, int] = {}
        parent: Dict[str, Optional[Tuple[str, str]]] = {}

        def dfs(node_id: str, from_segment: str) -> Optional[List[str]]:
            color[node_id] = 1
            for segment_id, neighbor in self._undirected_edges(node_id):
                if segment_id == from_segment:
                    continue
                if color.get(neighbor, 0) == 0:
                    parent[neighbor] = (node_id, segment_id)
                    cycle = dfs(neighbor, segment_id)
                    if cycle:
                        return cycle
                elif color.get(neighbor) == 1:
                    path = [node_id]
                    cursor = node_id
                    while cursor != neighbor:
                        prev, _seg = parent[cursor]
                        cursor = prev
                        path.append(cursor)
                    return path
            color[node_id] = 2
            return None

        for node_id in self.nodes:
            if color.get(node_id, 0) == 0:
                cycle = dfs(node_id, "")
                if cycle:
                    return cycle
        return []

    # -- spec 25: detect_dead_end ---------------------------------------------------------
    def detect_dead_end(self, topology: str = "radial_from_source") -> List[InstallNode]:
        """Degree-1 nodes with no continuation: neither terminals, nor
        equipment endpoints, nor origin/sink. Only loose junctions are
        reported (a forgotten stub)."""
        dead_ends: List[InstallNode] = []
        for node in self.nodes.values():
            if self.degree(node.id) != 1:
                continue
            if node.role in ("TERMINAL", "EQUIPMENT"):
                continue
            if node.kind in SOURCE_KINDS and topology == "radial_from_source":
                continue
            if node.kind in SINK_KINDS and topology == "converge_to_sink":
                continue
            dead_ends.append(node)
        return dead_ends


__all__ = ["NetworkGraph"]
