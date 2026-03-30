"""LLM-based natural language query agent for the music knowledge graph."""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from openai import OpenAI

from config.settings import settings
from src.database.aerospike_client import AerospikeClient, _BIN_NAME_REVERSE

logger = logging.getLogger(__name__)

GRAPH_SCHEMA = """
NODE TYPES:
- Song: title, duration_ms, release_date, isrc, spotify_id, tags, play_count, listener_count, completeness_score
- Artist: name, genres, country, formed_date, disbanded_date, spotify_id, popularity, follower_count, biography
- Album: title, release_date, album_type (album/single/compilation/ep), total_tracks, label, cover_art_url
- RecordLabel: name, country, founded_date, website_url
- Instrument: name, category (string/percussion/wind/keyboard/electronic/vocal/other)
- Venue: name, city, country, capacity, latitude, longitude, address
- Concert: concert_date, venue_id, tour_name, setlist, attendance, ticket_price_range

EDGE TYPES (from -> to):
- PERFORMED_IN: Artist -> Song (role, is_lead)
- PLAYED_INSTRUMENT: Artist -> Instrument (song_id, is_primary)
- SIGNED_WITH: Artist -> RecordLabel (start_date, end_date, contract_type)
- PART_OF_ALBUM: Song -> Album (track_number, disc_number)
- PERFORMED_AT: Artist -> Concert (performance_order, duration_minutes)
- SIMILAR_TO: Song -> Song (similarity_score, source)
"""

SYSTEM_PROMPT = f"""You are a query planner for a music knowledge graph stored in Aerospike.
Given a user's natural language question, generate a query plan using the available commands.

{GRAPH_SCHEMA}

AVAILABLE COMMANDS (one per line):
- FIND_NODE <node_type> <property_key> <property_value>
  Searches for nodes of a given type where a property matches the value.
  Example: FIND_NODE Artist name Radiohead

- GET_NODE <node_id>
  Retrieves a specific node by its UUID.
  Example: GET_NODE 550e8400-e29b-41d4-a716-446655440000

- QUERY_NEIGHBORS <node_id> [edge_type]
  Finds all neighbors of a node, optionally filtered by edge type.
  Example: QUERY_NEIGHBORS 550e8400-e29b-41d4-a716-446655440000 PERFORMED_IN

- SCAN_ALL <node_type>
  Lists all nodes of a given type.
  Example: SCAN_ALL Song

RULES:
1. Output ONLY the commands, one per line. No explanations or markdown.
2. Use FIND_NODE first to locate entities by name/title, then QUERY_NEIGHBORS to explore relationships.
3. Property values with spaces should be written as-is (no quotes needed).
4. You can output multiple commands. Later commands can reference results from earlier ones using $RESULT_N (0-indexed).
   Example:
   FIND_NODE Artist name Radiohead
   QUERY_NEIGHBORS $RESULT_0 PERFORMED_IN
5. Keep plans minimal -- only the commands needed to answer the question.
"""

SUMMARIZE_PROMPT = """You are a helpful music knowledge assistant. Given the user's question and the raw data retrieved from the music knowledge graph, provide a clear, concise natural language answer.

If the data contains empty arrays, "skipped" entries, or errors, it means the entity was NOT found in the knowledge graph. In that case, tell the user clearly:
- The entity they asked about has not been enriched into the graph yet.
- They should first search for a song on the Search page to add data to the graph.
Do NOT suggest external sources or make up information. Only use data present in the graph results.
Keep your answer focused and informative. Do not include any thinking or reasoning tags."""

VALID_COMMANDS = {"FIND_NODE", "GET_NODE", "QUERY_NEIGHBORS", "SCAN_ALL"}


class LLMQueryAgent:
    """Translates natural language queries into graph operations via an LLM."""

    def __init__(
        self,
        db_client: Optional[AerospikeClient] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.db_client = db_client
        self.model = model or settings.llm_model
        resolved_key = api_key or settings.llm_api_key
        resolved_base = base_url or settings.llm_base_url

        if not resolved_key:
            raise ValueError("LLM API key is required. Set LLM_API_KEY in your .env file.")

        self.client = OpenAI(api_key=resolved_key, base_url=resolved_base)

    async def query(self, question: str) -> Dict[str, Any]:
        """Answer a natural language question about the music graph.

        Returns dict with 'answer' (str) and 'data' (list of raw results).
        """
        plan = self._generate_plan(question)
        logger.info("LLM query plan: %s", plan)

        results = self._execute_plan(plan)

        answer = self._summarize(question, results)

        return {"answer": answer, "data": results}

    @staticmethod
    def _strip_think_tags(text: str) -> str:
        """Remove <think>...</think> blocks and markdown code fences."""
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        text = re.sub(r"```[a-z]*\n?", "", text)
        return text.strip()

    def _generate_plan(self, question: str) -> List[str]:
        """Ask the LLM to produce a list of graph commands."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
            temperature=0.2,
        )
        raw = self._strip_think_tags(response.choices[0].message.content or "")
        lines = []
        for ln in raw.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            first_word = ln.split()[0].upper() if ln.split() else ""
            if first_word in VALID_COMMANDS:
                lines.append(ln)
        return lines

    def _execute_plan(self, plan: List[str]) -> List[Any]:
        """Parse and execute each command in the plan sequentially.

        Skips commands whose $RESULT_N references point to empty/error results.
        """
        results: List[Any] = []

        for line in plan:
            resolved, ok = self._resolve_refs(line, results)
            if not ok:
                results.append({"skipped": f"Dependency returned no results for: {line}"})
                continue
            result = self._execute_command(resolved)
            results.append(result)

        return results

    def _resolve_refs(self, line: str, results: List[Any]) -> tuple:
        """Replace $RESULT_N references with actual node IDs from prior results.

        Returns (resolved_line, success). success is False if any reference
        points to an empty or error result.
        """
        resolved_ok = True

        def _replacer(match: re.Match[str]) -> str:
            nonlocal resolved_ok
            idx = int(match.group(1))
            if idx >= len(results):
                resolved_ok = False
                return str(match.group(0))
            prev = results[idx]
            # Empty list or error dict -- dependency has no usable data
            if isinstance(prev, list) and len(prev) == 0:
                resolved_ok = False
                return str(match.group(0))
            if isinstance(prev, dict) and ("error" in prev or "skipped" in prev):
                resolved_ok = False
                return str(match.group(0))
            # Extract node ID from the result
            if isinstance(prev, list) and len(prev) > 0:
                node = prev[0]
                if isinstance(node, dict) and "id" in node:
                    return str(node["id"])
            if isinstance(prev, dict) and "id" in prev:
                return str(prev["id"])
            resolved_ok = False
            return str(match.group(0))

        resolved = re.sub(r"\$RESULT_(\d+)", _replacer, line)
        return resolved, resolved_ok

    def _execute_command(self, line: str) -> Any:
        """Execute a single plan command against Aerospike."""
        if not self.db_client:
            return {"error": "Database not available"}

        parts = line.split(None, 3)
        if not parts:
            return {"error": "Empty command"}

        cmd = parts[0].upper()

        try:
            if cmd == "FIND_NODE" and len(parts) >= 4:
                node_type = parts[1]
                prop_key = parts[2]
                prop_value = parts[3]
                return self.db_client.find_node_by_property(node_type, prop_key, prop_value)

            elif cmd == "GET_NODE" and len(parts) >= 2:
                from uuid import UUID

                node_id = UUID(parts[1])
                node = self.db_client._get_node_by_id(node_id)
                return node if node else {"error": f"Node {parts[1]} not found"}

            elif cmd == "QUERY_NEIGHBORS" and len(parts) >= 2:
                from uuid import UUID

                node_id = UUID(parts[1])
                edge_type = parts[2] if len(parts) >= 3 else None
                return self.db_client.query_neighbors(node_id, edge_type)

            elif cmd == "SCAN_ALL" and len(parts) >= 2:
                node_type = parts[1]
                return self.db_client.find_node_by_property(
                    node_type, "__scan__", None
                ) or self._scan_all(node_type)

            else:
                return {"error": f"Unknown or malformed command: {line}"}

        except Exception as e:
            logger.warning("Command execution failed: %s — %s", line, e)
            return {"error": str(e)}

    def _scan_all(self, node_type: str) -> List[Dict[str, Any]]:
        """Scan all records of a given node type."""
        if not self.db_client or not self.db_client._client:
            return []

        records: List[Dict[str, Any]] = []
        scan = self.db_client._client.scan(self.db_client.namespace, node_type)

        def _collect(input_tuple: Any, out: List = records) -> None:
            _, _, record = input_tuple
            if record:
                out.append({_BIN_NAME_REVERSE.get(k, k): v for k, v in record.items()})

        scan.foreach(_collect)
        return records

    def _summarize(self, question: str, results: List[Any]) -> str:
        """Ask the LLM to produce a human-readable answer from raw results."""
        serializable = self._make_serializable(results)
        data_str = json.dumps(serializable, indent=2, default=str)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SUMMARIZE_PROMPT},
                {
                    "role": "user",
                    "content": f"Question: {question}\n\nGraph data:\n{data_str}",
                },
            ],
            temperature=0.3,
        )
        raw = response.choices[0].message.content or "Unable to generate an answer."
        return self._strip_think_tags(raw) or "Unable to generate an answer."

    def _make_serializable(self, obj: Any) -> Any:
        """Recursively convert non-serializable objects."""
        if isinstance(obj, dict):
            return {k: self._make_serializable(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._make_serializable(item) for item in obj]
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return str(obj)
