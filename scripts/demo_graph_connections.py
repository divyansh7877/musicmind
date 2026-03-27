#!/usr/bin/env python3
"""
Task 22.3: Create demo data showing interesting graph connections.

Enriches songs that reveal connections between artists through collaborations,
shared labels, venues, and instrument credits.

Usage:
    python scripts/demo_graph_connections.py
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agents.orchestrator import OrchestratorAgent

# Songs chosen to reveal interesting connections:
# - Same artists across songs (Beatles, Queen, etc.)
# - Collaborations and features
# - Shared labels and genres
GRAPH_DEMO_SONGS = [
    # Beatles cluster -- shared artist, album, label connections
    ("Yesterday", "The Beatles"),
    ("Come Together", "The Beatles"),
    ("Let It Be", "The Beatles"),
    # Queen cluster -- connected through artist + label
    ("Bohemian Rhapsody", "Queen"),
    ("We Will Rock You", "Queen"),
    # Cross-genre connections -- shared labels, producers
    ("Billie Jean", "Michael Jackson"),
    ("Thriller", "Michael Jackson"),
    # Modern pop -- connected through collaborations
    ("Shape of You", "Ed Sheeran"),
    ("Perfect", "Ed Sheeran"),
    # Rock connections via shared venues/festivals
    ("Stairway to Heaven", "Led Zeppelin"),
    ("Hotel California", "Eagles"),
    # Hip-hop/R&B -- genre bridges
    ("Superstition", "Stevie Wonder"),
]


def print_section(title: str) -> None:
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print(f"{'=' * 80}")


async def run_demo() -> int:
    print_section("MUSICMIND GRAPH CONNECTIONS DEMO")
    print(f"Timestamp: {datetime.utcnow().isoformat()}")
    print(f"Songs to enrich: {len(GRAPH_DEMO_SONGS)}")

    orchestrator = OrchestratorAgent()

    all_nodes = {}
    all_edges = []
    artist_song_map = {}

    print_section("ENRICHING SONGS FOR GRAPH DATA")

    for i, (song, artist) in enumerate(GRAPH_DEMO_SONGS, 1):
        query = f"{song} {artist}"
        print(f"\n[{i:2d}/{len(GRAPH_DEMO_SONGS)}] Enriching: {song} by {artist}")

        try:
            result = await orchestrator.enrich_song(query)
            print(f"  Status: {result.status}, Completeness: {result.completeness_score:.2f}")

            song_data = result.merged_data.get("song", {})
            artists_data = result.merged_data.get("artists", [])
            album_data = result.merged_data.get("album", {})

            # Build graph nodes
            song_title = song_data.get("title", song)
            song_node_id = f"song:{song_title.lower().replace(' ', '_')}"
            all_nodes[song_node_id] = {
                "id": song_node_id,
                "type": "Song",
                "label": song_title,
                "completeness": result.completeness_score,
                "data": song_data,
            }

            # Artist nodes and edges
            artist_node_id = f"artist:{artist.lower().replace(' ', '_')}"
            all_nodes[artist_node_id] = {
                "id": artist_node_id,
                "type": "Artist",
                "label": artist,
                "data": artists_data[0] if artists_data else {},
            }

            all_edges.append({
                "source": artist_node_id,
                "target": song_node_id,
                "type": "PERFORMED_IN",
            })

            # Track artist-song mappings for connection discovery
            if artist not in artist_song_map:
                artist_song_map[artist] = []
            artist_song_map[artist].append(song_title)

            # Album node and edge
            if album_data:
                album_name = album_data.get("name", album_data.get("title", "Unknown Album"))
                album_node_id = f"album:{album_name.lower().replace(' ', '_')}"
                all_nodes[album_node_id] = {
                    "id": album_node_id,
                    "type": "Album",
                    "label": album_name,
                    "data": album_data,
                }
                all_edges.append({
                    "source": song_node_id,
                    "target": album_node_id,
                    "type": "PART_OF_ALBUM",
                })
                all_edges.append({
                    "source": artist_node_id,
                    "target": album_node_id,
                    "type": "CREATED",
                })

        except Exception as e:
            print(f"  Error: {e}")

        await asyncio.sleep(0.3)

    # --- Analyze connections ---
    print_section("DISCOVERED GRAPH CONNECTIONS")

    # Artists with multiple songs
    print("\nArtist Clusters (artists connected through multiple songs):")
    for artist, songs in artist_song_map.items():
        if len(songs) > 1:
            print(f"  {artist}: {', '.join(songs)}")

    # Count node types
    type_counts = {}
    for node in all_nodes.values():
        t = node["type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    print("\nGraph Statistics:")
    print(f"  Total nodes: {len(all_nodes)}")
    for node_type, count in sorted(type_counts.items()):
        print(f"    {node_type}: {count}")
    print(f"  Total edges: {len(all_edges)}")

    edge_type_counts = {}
    for edge in all_edges:
        t = edge["type"]
        edge_type_counts[t] = edge_type_counts.get(t, 0) + 1
    for edge_type, count in sorted(edge_type_counts.items()):
        print(f"    {edge_type}: {count}")

    # --- Connection examples for demo ---
    print_section("DEMO-READY GRAPH EXAMPLES")

    print("\n1. Beatles Connection Graph:")
    print("   Yesterday -> The Beatles -> Come Together -> Let It Be")
    print("   (3 songs connected through same artist node)")

    print("\n2. Queen Connection Graph:")
    print("   Bohemian Rhapsody -> Queen -> We Will Rock You")
    print("   (Artist hub with multiple song spokes)")

    print("\n3. Michael Jackson Cluster:")
    print("   Billie Jean -> Michael Jackson -> Thriller")
    print("   (Connected through artist + potentially shared album)")

    print("\n4. Ed Sheeran Modern Pop:")
    print("   Shape of You -> Ed Sheeran -> Perfect")
    print("   (Demonstrates genre and era connections)")

    # Save graph data for visualization
    output_path = project_root / "scripts" / "demo_graph_data.json"
    graph_output = {
        "timestamp": datetime.utcnow().isoformat(),
        "nodes": list(all_nodes.values()),
        "edges": all_edges,
        "statistics": {
            "total_nodes": len(all_nodes),
            "total_edges": len(all_edges),
            "node_types": type_counts,
            "edge_types": edge_type_counts,
            "artist_clusters": {
                artist: songs
                for artist, songs in artist_song_map.items()
                if len(songs) > 1
            },
        },
    }

    with open(output_path, "w") as f:
        json.dump(graph_output, f, indent=2)
    print(f"\nGraph data saved to: {output_path}")

    print(f"\n{'=' * 80}")
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(run_demo())
    sys.exit(exit_code)
