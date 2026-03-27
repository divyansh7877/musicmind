# Spotify Agent Documentation

## Overview

The Spotify Agent is a specialized sub-agent responsible for fetching comprehensive music data from the Spotify Web API. It implements OAuth2 authentication, rate limiting, automatic token refresh, and robust error handling with exponential backoff retries.

## Features

### 1. OAuth2 Authentication (Sub-task 4.1)

- **Client Credentials Flow**: Authenticates using Spotify client ID and secret
- **Automatic Token Refresh**: Monitors token expiration and refreshes proactively (5-minute buffer)
- **Token Storage**: Maintains access token and expiration timestamp in memory

```python
from src.agents.spotify_agent import SpotifyAgent

agent = SpotifyAgent(
    client_id="your_client_id",
    client_secret="your_client_secret"
)

# Authentication happens automatically on first API call
result = await agent.fetch_spotify_data("Song Name")
```

### 2. Data Fetching Methods (Sub-task 4.2)

The agent provides multiple methods for fetching different types of data:

#### `fetch_spotify_data(song_name: str) -> SpotifyResult`

Main entry point that orchestrates all data fetching:

1. Searches for the track by name
2. Fetches audio features (tempo, key, energy, etc.)
3. Retrieves detailed artist information
4. Gets album metadata
5. Calculates completeness scores
6. Returns structured `SpotifyResult`

```python
result = await agent.fetch_spotify_data("Bohemian Rhapsody")

# Access song data
print(result.song.title)
print(result.song.duration_ms)
print(result.song.audio_features.tempo)

# Access artist data
for artist in result.artists:
    print(artist.name, artist.genres)

# Access album data
print(result.album.title)
print(result.album.release_date)

# Check completeness
print(f"Completeness: {result.completeness_score:.2%}")
```

#### `search_track(query: str) -> Optional[Dict]`

Searches for a track by name and returns the first match.

#### `get_artist_details(artist_id: str) -> Optional[Dict]`

Fetches detailed artist information including genres, popularity, and follower count.

#### `get_album_details(album_id: str) -> Optional[Dict]`

Retrieves album metadata including release date, label, and track count.

#### `get_audio_features(track_id: str) -> Optional[Dict]`

Gets audio analysis features like tempo, key, energy, and danceability.

### 3. Rate Limiting and Error Handling (Sub-task 4.3)

#### Rate Limiting

The agent implements a **token bucket rate limiter** with the following characteristics:

- **Rate**: 100 requests per minute
- **Burst Allowance**: 10 additional requests for burst traffic
- **Automatic Throttling**: Blocks requests when limit is reached
- **Token Refill**: Continuously refills tokens based on elapsed time

```python
# Rate limiter is used automatically for all API calls
# No manual intervention needed

# Example: Making multiple requests
tasks = [agent.fetch_spotify_data(song) for song in song_list]
results = await asyncio.gather(*tasks)  # Rate limiting applied automatically
```

#### Error Handling

The agent implements comprehensive error handling:

1. **429 Rate Limit Errors**:
   - Parses `Retry-After` header
   - Waits specified duration before retry
   - Logs event to Overmind Lab

2. **Server Errors (5xx)**:
   - Implements exponential backoff with jitter
   - Retries up to 3 times
   - Formula: `wait_time = (2 ** attempt) + random_jitter`

3. **Client Errors (4xx)**:
   - No retry (except 429)
   - Returns error immediately
   - Logs to Overmind Lab

4. **Timeout Errors**:
   - 10-second timeout per request
   - Retries with exponential backoff
   - Returns "failed" status after all retries

5. **Unrecoverable Errors**:
   - Returns `SpotifyResult` with `completeness_score=0.0`
   - Logs error with full stack trace
   - Allows orchestrator to continue with other agents

```python
# Error handling is automatic
result = await agent.fetch_spotify_data("Invalid Song XYZ123")

if result.completeness_score == 0.0:
    print("Failed to fetch data")
else:
    print(f"Partial data retrieved: {result.completeness_score:.2%}")
```

#### Overmind Lab Integration

All API calls and errors are logged to Overmind Lab for monitoring:

```python
from src.tracing.overmind_client import OvermindClient

overmind = OvermindClient()
agent = SpotifyAgent(overmind_client=overmind)

# All API calls will be logged automatically
result = await agent.fetch_spotify_data("Song Name")
```

Logged events include:
- `spotify_api_call`: Each API request with endpoint and attempt number
- `spotify_rate_limit`: Rate limit errors with retry duration
- Error logs with full context

## Data Models

### SpotifyResult

Container for Spotify data with completeness score:

```python
class SpotifyResult:
    song: Optional[Song]              # Song data
    artists: List[Artist]             # List of artists
    album: Optional[Album]            # Album data
    completeness_score: float         # 0.0 to 1.0
```

### Song

```python
class Song:
    title: str
    duration_ms: int
    spotify_id: str
    audio_features: Optional[AudioFeatures]
    data_sources: List[str]
    completeness_score: float
    # ... other fields
```

### Artist

```python
class Artist:
    name: str
    genres: List[str]
    spotify_id: str
    popularity: int                   # 0-100
    follower_count: int
    image_urls: List[str]
    completeness_score: float
    # ... other fields
```

### Album

```python
class Album:
    title: str
    release_date: date
    album_type: str                   # album, single, compilation, ep
    total_tracks: int
    spotify_id: str
    label: str
    cover_art_url: str
    completeness_score: float
    # ... other fields
```

### AudioFeatures

```python
class AudioFeatures:
    tempo: float                      # BPM
    key: int                          # 0-11 (C, C#, D, ...)
    mode: int                         # 0=minor, 1=major
    time_signature: int               # 1-7
    energy: float                     # 0.0-1.0
    danceability: float               # 0.0-1.0
    valence: float                    # 0.0-1.0 (positivity)
    acousticness: float               # 0.0-1.0
```

## Integration with Orchestrator

The Spotify agent is automatically integrated with the orchestrator:

```python
from src.agents.orchestrator import OrchestratorAgent

orchestrator = OrchestratorAgent()

# Spotify agent is called automatically along with other agents
result = await orchestrator.enrich_song("Song Name")

# Access Spotify data from merged results
song_data = result.merged_data["song"]
artist_data = result.merged_data["artists"]
album_data = result.merged_data["album"]
```

The orchestrator:
1. Dispatches Spotify agent in parallel with other agents
2. Applies 30-second timeout
3. Merges Spotify data with other sources
4. Resolves conflicts using quality rankings
5. Calculates overall completeness score

## Configuration

Configuration is managed through environment variables:

```bash
# .env file
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here
```

Or programmatically:

```python
from config.settings import settings

# Override settings
settings.spotify_client_id = "custom_id"
settings.spotify_client_secret = "custom_secret"

agent = SpotifyAgent()  # Uses settings
```

## Testing

### Unit Tests

Run unit tests for the Spotify agent:

```bash
pytest tests/test_spotify_agent.py -v
```

Tests cover:
- OAuth2 authentication flow
- Token refresh logic
- Rate limiting behavior
- API request handling
- Error handling and retries
- Data fetching methods
- Completeness calculation

### Integration Tests

Run integration tests with orchestrator:

```bash
pytest tests/test_spotify_integration.py -v
```

Tests cover:
- End-to-end data fetching
- Orchestrator integration
- Parallel execution
- Error handling in context

### Manual Testing

Test with real Spotify API:

```bash
python scripts/test_spotify_agent.py
```

This script:
- Fetches data for multiple songs
- Demonstrates rate limiting
- Shows completeness scores
- Validates all features

## Performance Characteristics

- **Average Response Time**: 200-500ms per song (depends on network)
- **Rate Limit**: 100 requests/minute with 10-request burst
- **Timeout**: 10 seconds per API call
- **Retry Attempts**: Up to 3 retries with exponential backoff
- **Completeness**: Typically 70-90% for popular songs

## Error Scenarios

| Scenario | Behavior | Status |
|----------|----------|--------|
| Song not found | Returns empty result | `completeness_score=0.0` |
| Rate limit hit | Waits and retries | Success after wait |
| Server error | Retries with backoff | Success or failed |
| Timeout | Retries up to 3 times | Failed after retries |
| Invalid credentials | Raises exception | Authentication failed |
| Network error | Retries with backoff | Failed after retries |

## Best Practices

1. **Reuse Agent Instance**: Create one agent and reuse for multiple requests
2. **Close After Use**: Always call `await agent.close()` when done
3. **Handle Failures**: Check `completeness_score` to detect failures
4. **Monitor Logs**: Use Overmind Lab to track API usage and errors
5. **Respect Rate Limits**: Let the rate limiter handle throttling automatically

## Example Usage

### Basic Usage

```python
import asyncio
from src.agents.spotify_agent import SpotifyAgent

async def main():
    agent = SpotifyAgent()
    
    try:
        result = await agent.fetch_spotify_data("Bohemian Rhapsody")
        
        if result.song:
            print(f"Found: {result.song.title}")
            print(f"Artist: {result.artists[0].name}")
            print(f"Completeness: {result.completeness_score:.2%}")
        else:
            print("Song not found")
    
    finally:
        await agent.close()

asyncio.run(main())
```

### Batch Processing

```python
async def fetch_multiple_songs(song_names):
    agent = SpotifyAgent()
    
    try:
        tasks = [agent.fetch_spotify_data(name) for name in song_names]
        results = await asyncio.gather(*tasks)
        
        for song_name, result in zip(song_names, results):
            if result.song:
                print(f"✓ {song_name}: {result.completeness_score:.2%}")
            else:
                print(f"✗ {song_name}: Not found")
        
        return results
    
    finally:
        await agent.close()

songs = ["Song 1", "Song 2", "Song 3"]
results = asyncio.run(fetch_multiple_songs(songs))
```

### With Overmind Tracing

```python
from src.agents.spotify_agent import SpotifyAgent
from src.tracing.overmind_client import OvermindClient

async def main():
    overmind = OvermindClient()
    agent = SpotifyAgent(overmind_client=overmind)
    
    try:
        result = await agent.fetch_spotify_data("Song Name")
        # All API calls are logged to Overmind Lab
    finally:
        await agent.close()

asyncio.run(main())
```

## Troubleshooting

### Authentication Errors

```
Error: Authentication failed: 401 Invalid credentials
```

**Solution**: Check that `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` are correct in `.env` file.

### Rate Limit Errors

```
Warning: Rate limited by Spotify, waiting 30s
```

**Solution**: This is normal. The agent will automatically wait and retry. Consider reducing request rate if this happens frequently.

### Timeout Errors

```
Error: Request timed out after all retries
```

**Solution**: Check network connection. Increase timeout if needed (default is 10s per request).

### No Results Found

```
completeness_score: 0.0
```

**Solution**: Song may not exist in Spotify catalog. Try different search terms or check spelling.

## API Reference

See the [Spotify Web API Documentation](https://developer.spotify.com/documentation/web-api/) for details on:
- Available endpoints
- Rate limits
- Authentication
- Data schemas

## Requirements Validation

This implementation satisfies the following requirements:

- **Requirement 2.1**: Spotify agent fetches song metadata, artist details, album information, and audio features ✓
- **Requirement 11.2**: Handles 429 rate limit errors with Retry-After header parsing ✓
- **Requirement 16.2**: Enforces rate limit of 100 requests/minute with burst allowance ✓
- **Requirement 16.5**: Parses Retry-After header and waits specified duration ✓
- **Requirement 16.6**: Implements exponential backoff with jitter for retries ✓

## Future Enhancements

Potential improvements for future iterations:

1. **Caching**: Cache artist/album data to reduce API calls
2. **Batch Requests**: Use Spotify's batch endpoints where available
3. **Playlist Support**: Add methods for fetching playlist data
4. **Related Artists**: Fetch related artists for discovery
5. **User Library**: Support for user-specific data (requires different auth flow)
6. **Metrics**: Track API usage statistics and performance metrics
