"""Estimate audio features from Last.fm/MusicBrainz tags.

The Spotify audio-features endpoint was deprecated in the February 2026 API
changes.  This module provides heuristic estimation of AudioFeatures fields
from user-generated tags returned by Last.fm and MusicBrainz.
"""

import logging
from typing import Dict, List, Optional

from src.models.nodes import AudioFeatures

logger = logging.getLogger(__name__)

TAG_SIGNALS: Dict[str, Dict[str, float]] = {
    # Energy signals
    "energetic": {"energy": 0.9},
    "high energy": {"energy": 0.95},
    "mellow": {"energy": 0.25},
    "chill": {"energy": 0.3, "valence": 0.5},
    "relaxing": {"energy": 0.2},
    "calm": {"energy": 0.2},
    "ambient": {"energy": 0.15, "acousticness": 0.6},
    "aggressive": {"energy": 0.95},
    "intense": {"energy": 0.85},
    "loud": {"energy": 0.85},
    "soft": {"energy": 0.2},
    "quiet": {"energy": 0.15},
    "hard rock": {"energy": 0.9},
    "heavy metal": {"energy": 0.95},
    "metal": {"energy": 0.9},
    "punk": {"energy": 0.9},
    "hardcore": {"energy": 0.95},
    "thrash metal": {"energy": 0.95},
    "death metal": {"energy": 0.95},
    "post-rock": {"energy": 0.5},
    "shoegaze": {"energy": 0.5, "acousticness": 0.2},
    # Danceability signals
    "dance": {"danceability": 0.85},
    "danceable": {"danceability": 0.9},
    "edm": {"danceability": 0.85, "energy": 0.85},
    "house": {"danceability": 0.85, "energy": 0.8},
    "techno": {"danceability": 0.8, "energy": 0.85},
    "disco": {"danceability": 0.9, "energy": 0.75},
    "funk": {"danceability": 0.85, "energy": 0.7},
    "groove": {"danceability": 0.8},
    "hip-hop": {"danceability": 0.75, "energy": 0.7},
    "hip hop": {"danceability": 0.75, "energy": 0.7},
    "rap": {"danceability": 0.7},
    "rnb": {"danceability": 0.7},
    "r&b": {"danceability": 0.7},
    "reggaeton": {"danceability": 0.85},
    "latin": {"danceability": 0.8},
    "salsa": {"danceability": 0.9},
    "trance": {"danceability": 0.75, "energy": 0.8},
    "drum and bass": {"danceability": 0.7, "energy": 0.9},
    # Valence signals
    "happy": {"valence": 0.9},
    "upbeat": {"valence": 0.85, "energy": 0.7},
    "uplifting": {"valence": 0.85},
    "cheerful": {"valence": 0.9},
    "feel good": {"valence": 0.85},
    "fun": {"valence": 0.8},
    "party": {"valence": 0.8, "danceability": 0.8, "energy": 0.8},
    "sad": {"valence": 0.15},
    "melancholy": {"valence": 0.2},
    "melancholic": {"valence": 0.2},
    "depressing": {"valence": 0.1},
    "dark": {"valence": 0.2, "energy": 0.5},
    "gloomy": {"valence": 0.15},
    "angry": {"valence": 0.25, "energy": 0.9},
    "emotional": {"valence": 0.35},
    "romantic": {"valence": 0.6},
    "love": {"valence": 0.6},
    # Acousticness signals
    "acoustic": {"acousticness": 0.9},
    "unplugged": {"acousticness": 0.9},
    "folk": {"acousticness": 0.75},
    "singer-songwriter": {"acousticness": 0.7},
    "classical": {"acousticness": 0.9, "energy": 0.3},
    "piano": {"acousticness": 0.8},
    "guitar": {"acousticness": 0.6},
    "jazz": {"acousticness": 0.6},
    "blues": {"acousticness": 0.55},
    "country": {"acousticness": 0.55},
    "bluegrass": {"acousticness": 0.8},
    "electronic": {"acousticness": 0.1},
    "synth": {"acousticness": 0.1},
    "synthpop": {"acousticness": 0.15, "danceability": 0.75},
    "industrial": {"acousticness": 0.05, "energy": 0.85},
    # Tempo hints (mapped to approximate BPM)
    "slow": {"tempo": 75.0},
    "ballad": {"tempo": 70.0, "energy": 0.25, "valence": 0.35},
    "downtempo": {"tempo": 85.0},
    "mid-tempo": {"tempo": 110.0},
    "fast": {"tempo": 150.0},
    "uptempo": {"tempo": 140.0},
    # Genre-based combined signals
    "pop": {"danceability": 0.65, "energy": 0.65, "valence": 0.6},
    "rock": {"energy": 0.75, "acousticness": 0.2},
    "alternative": {"energy": 0.6},
    "indie": {"energy": 0.5, "acousticness": 0.4},
    "soul": {"acousticness": 0.5, "valence": 0.55},
    "reggae": {"danceability": 0.7, "energy": 0.5, "valence": 0.65},
    "bossa nova": {"acousticness": 0.8, "energy": 0.25, "valence": 0.6},
    "lofi": {"energy": 0.3, "acousticness": 0.4},
    "lo-fi": {"energy": 0.3, "acousticness": 0.4},
}


def estimate_audio_features(tags: List[str]) -> Optional[AudioFeatures]:
    """Estimate AudioFeatures from a list of user-generated tags.

    Each recognised tag contributes a signal for one or more audio feature
    dimensions.  When multiple tags contribute to the same dimension, the
    values are averaged.  Dimensions with no signal are left as ``None``.

    Args:
        tags: List of tag strings (e.g. from Last.fm or MusicBrainz).

    Returns:
        An AudioFeatures instance, or None if no tags matched.
    """
    if not tags:
        return None

    accumulators: Dict[str, List[float]] = {
        "energy": [],
        "danceability": [],
        "valence": [],
        "acousticness": [],
        "tempo": [],
    }

    matched = 0
    for tag in tags:
        normalised = tag.lower().strip()
        if normalised in TAG_SIGNALS:
            matched += 1
            for dimension, value in TAG_SIGNALS[normalised].items():
                accumulators[dimension].append(value)

    if matched == 0:
        logger.debug("No recognised tags for audio feature estimation")
        return None

    def _avg(values: List[float]) -> Optional[float]:
        return round(sum(values) / len(values), 4) if values else None

    energy = _avg(accumulators["energy"])
    danceability = _avg(accumulators["danceability"])
    valence = _avg(accumulators["valence"])
    acousticness = _avg(accumulators["acousticness"])
    tempo = _avg(accumulators["tempo"])

    features = AudioFeatures(
        energy=energy,
        danceability=danceability,
        valence=valence,
        acousticness=acousticness,
        tempo=tempo,
    )

    logger.info(
        f"Estimated audio features from {matched}/{len(tags)} tags: "
        f"energy={energy}, dance={danceability}, valence={valence}, "
        f"acoustic={acousticness}, tempo={tempo}"
    )

    return features
