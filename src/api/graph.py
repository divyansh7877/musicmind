"""Graph traversal service for visualization."""

import logging
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Set
from uuid import UUID

from pydantic import BaseModel, Field

from src.database.aerospike_client import AerospikeClient

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

    def _get_node(self, node_id: UUID) -> Dict[str, Any]:
        """Get node by ID.

        Args:
            node_id: Node ID

        Returns:
            Node data dictionary or None if not found
        """
        try:
            # Try different node types
            node_types = [
                "Song",
                "Artist",
                "Album",
                "RecordLabel",
                "Instrument",
                "Venue",
                "Concert",
            ]

            for node_type in node_types:
                node = self.db_client._get_node_by_id(node_id)
                if node:
                    node["type"] = node_type
                    return node

            return None
        except Exception as e:
            logger.error(f"Failed to get node {node_id}: {e}")
            return None

    def _get_node_edges(self, node_id: UUID, node_type: str) -> List[Dict[str, Any]]:
        """Get all edges from a node.

        Args:
            node_id: Node ID
            node_type: Node type

        Returns:
            List of edge dictionaries
        """
        try:
            edges = []

            # Query edges based on node type
            # In production, implement proper edge queries
            # For now, return empty list as placeholder

            return edges
        except Exception as e:
            logger.error(f"Failed to get edges for node {node_id}: {e}")
            return []

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
