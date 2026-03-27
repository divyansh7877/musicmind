"""Aerospike Graph database client wrapper with connection pooling and retry logic."""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
from uuid import UUID

import aerospike
from pydantic import BaseModel, ValidationError

from config.settings import settings

logger = logging.getLogger(__name__)


class AerospikeClient:
    """Wrapper for Aerospike Graph database operations with connection pooling."""

    def __init__(
        self,
        host: str = settings.aerospike_host,
        port: int = settings.aerospike_port,
        namespace: str = settings.aerospike_namespace,
        max_retries: int = 3,
        initial_backoff: float = 0.5,
    ):
        """Initialize Aerospike client with connection pooling.

        Args:
            host: Aerospike server host
            port: Aerospike server port
            namespace: Aerospike namespace
            max_retries: Maximum number of retry attempts
            initial_backoff: Initial backoff delay in seconds
        """
        self.host = host
        self.port = port
        self.namespace = namespace
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self._client: Optional[aerospike.Client] = None

    def connect(self) -> None:
        """Establish connection to Aerospike with retry logic."""
        config = {
            "hosts": [(self.host, self.port)],
            "policies": {
                "timeout": 5000,  # 5 second timeout
            },
        }

        for attempt in range(self.max_retries):
            try:
                self._client = aerospike.client(config).connect()
                logger.info(f"Connected to Aerospike at {self.host}:{self.port}")
                return
            except Exception as e:
                backoff = self.initial_backoff * (2**attempt)
                logger.warning(
                    f"Connection attempt {attempt + 1}/{self.max_retries} failed: {e}. "
                    f"Retrying in {backoff}s..."
                )
                if attempt < self.max_retries - 1:
                    time.sleep(backoff)
                else:
                    logger.error("Failed to connect to Aerospike after all retries")
                    raise ConnectionError(
                        f"Could not connect to Aerospike at {self.host}:{self.port}"
                    ) from e

    def disconnect(self) -> None:
        """Close connection to Aerospike."""
        if self._client:
            self._client.close()
            self._client = None
            logger.info("Disconnected from Aerospike")

    def _ensure_connected(self) -> None:
        """Ensure client is connected, reconnect if necessary."""
        if not self._client:
            self.connect()

    def upsert_node(
        self, node_type: str, properties: Dict[str, Any], node_model: Optional[type] = None
    ) -> UUID:
        """Insert or update a graph node with validation.

        Args:
            node_type: Type of node (Song, Artist, Album, etc.)
            properties: Node properties as dictionary
            node_model: Optional Pydantic model for validation

        Returns:
            UUID of the created or updated node

        Raises:
            ValidationError: If properties fail validation
            ConnectionError: If database connection fails
        """
        self._ensure_connected()

        # Validate properties if model provided
        if node_model:
            try:
                validated_node = node_model(**properties)
                properties = validated_node.model_dump(mode="json")
            except ValidationError as e:
                logger.error(f"Validation failed for {node_type}: {e}")
                raise

        # Convert UUID to string for storage
        node_id = properties.get("id")
        if isinstance(node_id, UUID):
            node_id = str(node_id)
        elif not node_id:
            from uuid import uuid4

            node_id = str(uuid4())
            properties["id"] = node_id

        # Create Aerospike key
        key = (self.namespace, node_type, node_id)

        # Prepare bins (Aerospike's term for fields)
        bins = self._prepare_bins(properties)

        # Upsert with retry logic
        for attempt in range(self.max_retries):
            try:
                self._client.put(key, bins)
                logger.debug(f"Upserted {node_type} node with ID {node_id}")
                return UUID(node_id)
            except Exception as e:
                backoff = self.initial_backoff * (2**attempt)
                logger.warning(
                    f"Upsert attempt {attempt + 1}/{self.max_retries} failed: {e}. "
                    f"Retrying in {backoff}s..."
                )
                if attempt < self.max_retries - 1:
                    time.sleep(backoff)
                else:
                    logger.error(f"Failed to upsert {node_type} node after all retries")
                    raise

    def upsert_edge(
        self,
        from_node_id: UUID,
        to_node_id: UUID,
        edge_type: str,
        properties: Dict[str, Any],
        edge_model: Optional[type] = None,
    ) -> UUID:
        """Insert or update a graph edge with node reference validation.

        Args:
            from_node_id: Source node UUID
            to_node_id: Target node UUID
            edge_type: Type of edge (PERFORMED_IN, PLAYED_INSTRUMENT, etc.)
            properties: Edge properties as dictionary
            edge_model: Optional Pydantic model for validation

        Returns:
            UUID of the created or updated edge

        Raises:
            ValidationError: If properties fail validation
            ValueError: If referenced nodes don't exist
            ConnectionError: If database connection fails
        """
        self._ensure_connected()

        # Validate that both nodes exist
        if not self._node_exists(from_node_id):
            raise ValueError(f"Source node {from_node_id} does not exist")
        if not self._node_exists(to_node_id):
            raise ValueError(f"Target node {to_node_id} does not exist")

        # Add node IDs to properties
        properties["from_node_id"] = from_node_id
        properties["to_node_id"] = to_node_id
        properties["edge_type"] = edge_type

        # Validate properties if model provided
        if edge_model:
            try:
                validated_edge = edge_model(**properties)
                properties = validated_edge.model_dump(mode="json")
            except ValidationError as e:
                logger.error(f"Validation failed for {edge_type}: {e}")
                raise

        # Generate edge ID
        edge_id = properties.get("id")
        if isinstance(edge_id, UUID):
            edge_id = str(edge_id)
        elif not edge_id:
            from uuid import uuid4

            edge_id = str(uuid4())
            properties["id"] = edge_id

        # Create Aerospike key
        key = (self.namespace, edge_type, edge_id)

        # Prepare bins
        bins = self._prepare_bins(properties)

        # Upsert with retry logic
        for attempt in range(self.max_retries):
            try:
                self._client.put(key, bins)
                logger.debug(f"Upserted {edge_type} edge with ID {edge_id}")
                return UUID(edge_id)
            except Exception as e:
                backoff = self.initial_backoff * (2**attempt)
                logger.warning(
                    f"Upsert attempt {attempt + 1}/{self.max_retries} failed: {e}. "
                    f"Retrying in {backoff}s..."
                )
                if attempt < self.max_retries - 1:
                    time.sleep(backoff)
                else:
                    logger.error(f"Failed to upsert {edge_type} edge after all retries")
                    raise

    def query_neighbors(
        self, node_id: UUID, edge_type: Optional[str] = None, depth: int = 1
    ) -> List[Dict[str, Any]]:
        """Query neighbors of a node through graph traversal.

        Args:
            node_id: Starting node UUID
            edge_type: Optional edge type filter
            depth: Traversal depth (default 1)

        Returns:
            List of neighbor nodes with edge information

        Raises:
            ValueError: If node doesn't exist
            ConnectionError: If database connection fails
        """
        self._ensure_connected()

        if not self._node_exists(node_id):
            raise ValueError(f"Node {node_id} does not exist")

        # Query edges from this node
        node_id_str = str(node_id)
        neighbors = []

        # Scan for edges where from_node_id matches
        scan = self._client.scan(self.namespace, edge_type if edge_type else None)

        def callback(input_tuple):
            (key, metadata, record) = input_tuple
            if record.get("from_node_id") == node_id_str:
                to_node_id = record.get("to_node_id")
                if to_node_id:
                    # Fetch the target node
                    target_node = self._get_node_by_id(UUID(to_node_id))
                    if target_node:
                        neighbors.append(
                            {
                                "edge_id": record.get("id"),
                                "edge_type": record.get("edge_type"),
                                "edge_properties": record,
                                "node": target_node,
                            }
                        )

        scan.foreach(callback)

        return neighbors

    def find_node_by_property(
        self, node_type: str, property_key: str, property_value: Any
    ) -> List[Dict[str, Any]]:
        """Find nodes by property value.

        Args:
            node_type: Type of node to search
            property_key: Property name to match
            property_value: Property value to match

        Returns:
            List of matching nodes

        Raises:
            ConnectionError: If database connection fails
        """
        self._ensure_connected()

        matching_nodes = []
        scan = self._client.scan(self.namespace, node_type)

        def callback(input_tuple):
            (key, metadata, record) = input_tuple
            if record.get(property_key) == property_value:
                matching_nodes.append(record)

        scan.foreach(callback)

        return matching_nodes

    def _node_exists(self, node_id: UUID) -> bool:
        """Check if a node exists in the database.

        Args:
            node_id: Node UUID to check

        Returns:
            True if node exists, False otherwise
        """
        node_id_str = str(node_id)

        # Check across all node types
        node_types = ["Song", "Artist", "Album", "RecordLabel", "Instrument", "Venue", "Concert"]

        for node_type in node_types:
            key = (self.namespace, node_type, node_id_str)
            try:
                (key, metadata, record) = self._client.get(key)
                if record:
                    return True
            except Exception:
                continue

        return False

    def _get_node_by_id(self, node_id: UUID) -> Optional[Dict[str, Any]]:
        """Get a node by its ID.

        Args:
            node_id: Node UUID

        Returns:
            Node data or None if not found
        """
        node_id_str = str(node_id)

        # Check across all node types
        node_types = ["Song", "Artist", "Album", "RecordLabel", "Instrument", "Venue", "Concert"]

        for node_type in node_types:
            key = (self.namespace, node_type, node_id_str)
            try:
                (key, metadata, record) = self._client.get(key)
                if record:
                    return record
            except Exception:
                continue

        return None

    def _prepare_bins(self, properties: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare properties for Aerospike storage.

        Args:
            properties: Raw properties dictionary

        Returns:
            Prepared bins dictionary
        """
        bins = {}
        for key, value in properties.items():
            # Convert UUIDs to strings
            if isinstance(value, UUID):
                bins[key] = str(value)
            # Convert datetime to ISO format string
            elif hasattr(value, "isoformat"):
                bins[key] = value.isoformat()
            # Convert nested models to dict
            elif isinstance(value, BaseModel):
                bins[key] = value.model_dump(mode="json")
            # Keep other types as-is
            else:
                bins[key] = value

        return bins

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
