"""Graph traversal service for visualization."""

import logging
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

from pydantic import BaseModel, Field

from src.database.aerospike_client import AerospikeClient, _BIN_NAME_REVERSE

logger = logging.getLogger(__name__)


class GraphTraversalRequest(BaseModel):
    """Request model for graph traversal."""

    max_depth: int = Field(default=2, ge=1, le=5, description="Maximum traversal depth")


class GraphNode(BaseModel):
    """Graph node for visualization."""

    id: str
    type: str
    data: Dict[str, Any]


class GraphEdge(BaseModel):
    """Graph edge for visualization."""

    from_node_id: str
    to_node_id: str
    edge_type: str
    properties: Dict[str, Any] = Field(default_factory=dict)


class GraphTraversalResponse(BaseModel):
    """Response model for graph traversal."""

    nodes: List[GraphNode]
    edges: List[GraphEdge]
    total_nodes: int
    total_edges: int
    depth_reached: int
    truncated: bool


class GraphService:
    """Service for graph traversal and visualization."""

    MAX_NODES = 1000

    @staticmethod
    def _expand(record: Dict[str, Any]) -> Dict[str, Any]:
        """Restore shortened Aerospike bin names to original field names."""
        return {_BIN_NAME_REVERSE.get(k, k): v for k, v in record.items()}

    def __init__(self, db_client: AerospikeClient):
        """Initialize graph service.

        Args:
            db_client: Aerospike database client
        """
        self.db_client = db_client

    async def traverse_graph(
        self,
        start_node_id: UUID,
        max_depth: int = 2,
    ) -> GraphTraversalResponse:
        """Traverse graph from a starting node using breadth-first search.

        Args:
            start_node_id: Starting node ID
            max_depth: Maximum depth to traverse (1-5)

        Returns:
            GraphTraversalResponse with nodes and edges

        Raises:
            ValueError: If node doesn't exist or parameters invalid
        """
        start_time = datetime.utcnow()

        # Validate parameters
        if max_depth < 1 or max_depth > 5:
            raise ValueError("max_depth must be between 1 and 5")

        # Get starting node
        start_node = self._get_node(start_node_id)
        if not start_node:
            raise ValueError(f"Node {start_node_id} not found")

        # Initialize BFS
        visited_nodes: Set[str] = set()
        nodes: List[GraphNode] = []
        edges: List[GraphEdge] = []

        # Queue: (node_id, node_type, depth)
        queue = deque([(str(start_node_id), start_node["type"], 0)])
        visited_nodes.add(str(start_node_id))

        # Add start node
        nodes.append(
            GraphNode(
                id=str(start_node_id),
                type=start_node["type"],
                data=self._sanitize_node_data(start_node),
            )
        )

        depth_reached = 0
        truncated = False

        # BFS traversal
        while queue and len(nodes) < self.MAX_NODES:
            current_id, current_type, current_depth = queue.popleft()
            depth_reached = max(depth_reached, current_depth)

            # Stop if max depth reached
            if current_depth >= max_depth:
                continue

            # Get edges from current node
            node_edges = self._get_node_edges(UUID(current_id), current_type)

            for edge in node_edges:
                # Check node limit
                if len(nodes) >= self.MAX_NODES:
                    truncated = True
                    break

                # Get target node
                target_id = edge["to_node_id"]

                # Add edge
                edges.append(
                    GraphEdge(
                        from_node_id=edge["from_node_id"],
                        to_node_id=target_id,
                        edge_type=edge["edge_type"],
                        properties=edge.get("properties", {}),
                    )
                )

                # Visit target node if not visited
                if target_id not in visited_nodes:
                    visited_nodes.add(target_id)

                    # Get target node data
                    target_node = self._get_node(UUID(target_id))
                    if target_node:
                        nodes.append(
                            GraphNode(
                                id=target_id,
                                type=target_node["type"],
                                data=self._sanitize_node_data(target_node),
                            )
                        )

                        # Add to queue for further traversal
                        queue.append((target_id, target_node["type"], current_depth + 1))

            if truncated:
                break

        # Validate all edges reference nodes in result
        node_ids = {node.id for node in nodes}
        valid_edges = [
            edge for edge in edges if edge.from_node_id in node_ids and edge.to_node_id in node_ids
        ]

        end_time = datetime.utcnow()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        logger.info(
            f"Graph traversal complete: {len(nodes)} nodes, {len(valid_edges)} edges, "
            f"depth {depth_reached}, {duration_ms}ms"
        )

        return GraphTraversalResponse(
            nodes=nodes,
            edges=valid_edges,
            total_nodes=len(nodes),
            total_edges=len(valid_edges),
            depth_reached=depth_reached,
            truncated=truncated,
        )

    def _get_node(self, node_id: UUID) -> Optional[Dict[str, Any]]:
        """Get node by ID, searching across all node types.

        Args:
            node_id: Node ID

        Returns:
            Node data dictionary or None if not found
        """
        node_id_str = str(node_id)
        node_types = [
            "Song",
            "Artist",
            "Album",
            "RecordLabel",
            "Instrument",
            "Venue",
            "Concert",
        ]

        try:
            for node_type in node_types:
                key = (self.db_client.namespace, node_type, node_id_str)
                try:
                    _, _, record = self.db_client._client.get(key)
                    if record:
                        expanded = self._expand(record)
                        expanded["type"] = expanded.get("node_type", node_type)
                        return expanded
                except Exception:
                    continue
            return None
        except Exception as e:
            logger.error(f"Failed to get node {node_id}: {e}")
            return None

    def _get_node_edges(self, node_id: UUID, node_type: str) -> List[Dict[str, Any]]:
        """Get all edges from/to a node by scanning edge sets.

        Args:
            node_id: Node ID
            node_type: Node type

        Returns:
            List of edge dictionaries
        """
        node_id_str = str(node_id)
        edges: List[Dict[str, Any]] = []
        edge_types = [
            "PERFORMED_IN",
            "PART_OF_ALBUM",
            "SIGNED_WITH",
            "SIMILAR_TO",
            "PLAYED_INSTRUMENT",
            "PERFORMED_AT",
        ]

        for edge_type in edge_types:
            try:
                scan = self.db_client._client.scan(self.db_client.namespace, edge_type)
                results: List[Dict[str, Any]] = []

                def _collect(input_tuple: Any, out: List = results) -> None:
                    _, _, record = input_tuple
                    if record and (
                        record.get("from_node_id") == node_id_str
                        or record.get("to_node_id") == node_id_str
                    ):
                        out.append(self._expand(record))

                scan.foreach(_collect)

                for rec in results:
                    from_id = rec.get("from_node_id", "")
                    to_id = rec.get("to_node_id", "")
                    edges.append(
                        {
                            "from_node_id": from_id,
                            "to_node_id": to_id,
                            "edge_type": rec.get("edge_type", edge_type),
                            "properties": {
                                k: v
                                for k, v in rec.items()
                                if k not in ("from_node_id", "to_node_id", "edge_type", "id")
                            },
                        }
                    )
            except Exception as e:
                logger.debug(f"Edge scan for {edge_type} failed: {e}")

        return edges

    async def get_full_graph(self) -> GraphTraversalResponse:
        """Scan all node and edge types to return the complete graph."""
        nodes: List[GraphNode] = []
        edges: List[GraphEdge] = []
        node_ids: Set[str] = set()

        node_types = [
            "Song",
            "Artist",
            "Album",
            "RecordLabel",
            "Instrument",
            "Venue",
            "Concert",
        ]
        edge_types = [
            "PERFORMED_IN",
            "PART_OF_ALBUM",
            "SIGNED_WITH",
            "SIMILAR_TO",
            "PLAYED_INSTRUMENT",
            "PERFORMED_AT",
        ]

        for node_type in node_types:
            try:
                scan = self.db_client._client.scan(self.db_client.namespace, node_type)
                results: List[Dict[str, Any]] = []

                def _collect(input_tuple: Any, out: List = results) -> None:
                    _, _, record = input_tuple
                    if record:
                        out.append(self._expand(record))

                scan.foreach(_collect)

                for record in results:
                    nid = record.get("id", "")
                    if nid and nid not in node_ids:
                        node_ids.add(nid)
                        record["type"] = record.get("node_type", node_type)
                        nodes.append(
                            GraphNode(
                                id=nid,
                                type=record["type"],
                                data=self._sanitize_node_data(record),
                            )
                        )
            except Exception as e:
                logger.debug(f"Full scan for {node_type} failed: {e}")

        for edge_type in edge_types:
            try:
                scan = self.db_client._client.scan(self.db_client.namespace, edge_type)
                results = []

                def _collect_edge(input_tuple: Any, out: List = results) -> None:
                    _, _, record = input_tuple
                    if record:
                        out.append(self._expand(record))

                scan.foreach(_collect_edge)

                for rec in results:
                    from_id = rec.get("from_node_id", "")
                    to_id = rec.get("to_node_id", "")
                    if from_id in node_ids and to_id in node_ids:
                        edges.append(
                            GraphEdge(
                                from_node_id=from_id,
                                to_node_id=to_id,
                                edge_type=rec.get("edge_type", edge_type),
                                properties={
                                    k: v
                                    for k, v in rec.items()
                                    if k not in ("from_node_id", "to_node_id", "edge_type", "id")
                                },
                            )
                        )
            except Exception as e:
                logger.debug(f"Full edge scan for {edge_type} failed: {e}")

        return GraphTraversalResponse(
            nodes=nodes,
            edges=edges,
            total_nodes=len(nodes),
            total_edges=len(edges),
            depth_reached=0,
            truncated=len(nodes) >= self.MAX_NODES,
        )

    def _sanitize_node_data(self, node: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize node data for frontend.

        Args:
            node: Node data dictionary

        Returns:
            Sanitized node data
        """
        # Remove internal fields
        sanitized = {k: v for k, v in node.items() if not k.startswith("_")}

        # Convert UUIDs to strings
        for key, value in sanitized.items():
            if isinstance(value, UUID):
                sanitized[key] = str(value)

        # Limit string lengths to prevent XSS
        for key, value in sanitized.items():
            if isinstance(value, str) and len(value) > 1000:
                sanitized[key] = value[:1000] + "..."

        return sanitized
