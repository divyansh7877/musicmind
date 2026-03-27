# Implementation Plan: MusicMind Agent Platform

## Overview

This implementation plan breaks down the MusicMind agent platform into manageable tasks organized by the 48-hour hackathon timeline. The platform demonstrates autonomous multi-agent orchestration with self-improvement capabilities, using Python for all backend services. Tasks are prioritized to deliver core functionality first (orchestrator + agents + graph DB), followed by self-improvement features, frontend, and demo preparation.

## Tasks

### Phase 1: Foundation (Hours 0-8)

- [x] 1. Project setup and infrastructure
  - [x] 1.1 Initialize Python project structure with virtual environment
    - Create project directory structure: `src/`, `tests/`, `config/`, `scripts/`
    - Set up `pyproject.toml` with dependencies: FastAPI, httpx, redis, pytest, hypothesis
    - Create `.env.example` for environment variables
    - Initialize Git repository with `.gitignore`
    - _Requirements: 17.1_
  
  - [x] 1.2 Configure Docker Compose for local development
    - Create `docker-compose.yml` with Aerospike Graph, Redis services
    - Configure Aerospike Graph with persistent volumes
    - Configure Redis with LRU eviction policy (2GB max memory)
    - Add health checks for all services
    - _Requirements: 12.2, 12.4_
  
  - [x] 1.3 Set up external API credentials and configuration
    - Obtain Spotify API client ID and secret
    - Obtain Last.fm API key
    - Configure MusicBrainz user agent with contact email
    - Create `config/settings.py` for centralized configuration
    - Store credentials in environment variables
    - _Requirements: 13.6, 16.7_


- [x] 2. Aerospike Graph database schema and operations
  - [x] 2.1 Design and implement graph schema for music entities
    - Define node types: Song, Artist, Album, RecordLabel, Instrument, Venue, Concert
    - Define edge types: PERFORMED_IN, PLAYED_INSTRUMENT, SIGNED_WITH, PART_OF_ALBUM, PERFORMED_AT, SIMILAR_TO
    - Create Python data models using Pydantic for all node and edge types
    - Implement validation rules for each entity type
    - _Requirements: 3.1, 3.2, 15.1, 15.2, 15.3, 15.4_
  
  - [x] 2.2 Implement Aerospike Graph database client wrapper
    - Create `src/database/aerospike_client.py` with connection pooling
    - Implement `upsert_node()` method with validation
    - Implement `upsert_edge()` method with node reference validation
    - Implement `query_neighbors()` for graph traversal
    - Implement `find_node_by_property()` for lookups
    - Add connection retry logic with exponential backoff
    - _Requirements: 3.3, 3.4, 3.5, 11.4, 12.4_
  
  - [ ]* 2.3 Write property test for graph node persistence
    - **Property 10: Graph Node Persistence**
    - **Validates: Requirements 3.3, 3.4, 3.5**
    - Generate random music entities with varying field populations
    - Verify all entities are persisted with unique IDs
    - Verify existing nodes are updated (upsert behavior)
    - Verify no duplicate nodes are created
  
  - [x] 2.4 Implement completeness score calculation
    - Create `calculate_completeness()` function in `src/utils/metrics.py`
    - Count total fields vs populated fields for each entity type
    - Weight critical fields (title, name) higher than optional fields
    - Return float between 0.0 and 1.0
    - _Requirements: 3.6, 3.7_
  
  - [ ]* 2.5 Write property test for completeness score calculation
    - **Property 1: Data Consistency**
    - **Validates: Requirements 3.6, 3.7, 4.6**
    - Generate random nodes with varying field populations
    - Verify completeness_score equals populated_fields / total_fields
    - Verify score is always between 0.0 and 1.0
    - Verify last_enriched timestamp is not in the future


- [x] 3. Orchestrator agent core implementation
  - [x] 3.1 Create orchestrator agent with parallel dispatch
    - Create `src/agents/orchestrator.py` with `OrchestratorAgent` class
    - Implement `enrich_song()` method as main entry point
    - Implement `dispatch_agents()` using `asyncio.gather()` for parallel execution
    - Set 30-second timeout for each agent using `asyncio.wait_for()`
    - Handle agent failures gracefully (continue with successful results)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 12.1_
  
  - [x] 3.2 Implement result merging with conflict resolution
    - Create `merge_results()` method in orchestrator
    - Implement `merge_song_data()` with quality-based conflict resolution
    - Implement field-specific strategies: single-value, multi-value, time-sensitive
    - Use source quality rankings from self-improvement engine
    - Calculate overall completeness score for merged data
    - _Requirements: 1.5, 2.5, 2.6, 2.7_
  
  - [ ]* 3.3 Write property test for merge conflict resolution
    - **Property 6: Merge Conflict Resolution**
    - **Validates: Requirements 2.5, 2.6, 2.7**
    - Generate random conflicting data from multiple sources
    - Verify merged result selects value from highest quality source
    - Verify multi-value fields contain union of all source values
    - Verify no data loss during merge
  
  - [x] 3.4 Integrate Redis caching for enrichment results
    - Create `src/cache/redis_client.py` wrapper
    - Implement cache key format: `song:{song_name}:v1`
    - Set TTL to 3600 seconds (1 hour)
    - Check cache before dispatching agents
    - Store enrichment results after successful merge
    - _Requirements: 1.6, 1.7, 12.2_
  
  - [x] 3.5 Integrate Overmind Lab tracing
    - Install Overmind Lab SDK for Python
    - Create trace context in `enrich_song()` with unique request ID
    - Create child spans for each agent dispatch
    - Log agent response times and status
    - End trace with success/failure status
    - _Requirements: 14.1, 14.2, 14.3, 14.5_
  
  - [ ]* 3.6 Write property test for parallel agent execution
    - **Property 9: Parallel Agent Execution**
    - **Validates: Requirements 1.1, 1.2, 1.4, 12.1**
    - Verify all available agents are dispatched concurrently
    - Verify 30-second timeout is enforced
    - Verify orchestrator continues with successful results when some fail
    - Verify all agents complete or timeout before returning


- [x] 4. Spotify agent implementation
  - [x] 4.1 Implement Spotify API authentication and client
    - Create `src/agents/spotify_agent.py` with `SpotifyAgent` class
    - Implement OAuth2 client credentials flow
    - Store access token with expiration tracking
    - Implement automatic token refresh
    - _Requirements: 2.1_
  
  - [x] 4.2 Implement Spotify data fetching methods
    - Implement `fetch_spotify_data()` as main entry point
    - Implement `search_track()` to find songs by name
    - Implement `get_artist_details()` for artist metadata
    - Implement `get_album_details()` for album information
    - Implement `get_audio_features()` for tempo, key, energy, etc.
    - Return structured `SpotifyResult` with completeness score
    - _Requirements: 2.1_
  
  - [x] 4.3 Implement rate limiting and error handling
    - Implement rate limiter: 100 requests/minute with burst allowance
    - Handle 429 rate limit errors with Retry-After header parsing
    - Implement exponential backoff with jitter for retries
    - Log all API calls to Overmind Lab
    - Return "failed" status with error message on unrecoverable errors
    - _Requirements: 11.2, 16.2, 16.5, 16.6_
  
  - [ ]* 4.4 Write property test for agent result integrity
    - **Property 2: Agent Result Integrity**
    - **Validates: Requirements 1.3, 1.4, 4.1**
    - Generate random agent results with various statuses
    - Verify status is one of: success, partial, failed
    - Verify successful results contain data with positive completeness
    - Verify failed results contain error messages
    - Verify all results have positive response times

- [ ] 5. Checkpoint - Verify end-to-end enrichment with Spotify
  - Test song enrichment with Spotify agent only
  - Verify data is persisted to Aerospike Graph
  - Verify caching works correctly
  - Verify Overmind Lab traces are created
  - Ensure all tests pass, ask the user if questions arise.


### Phase 2: Multi-Agent System (Hours 8-20)

- [ ] 6. MusicBrainz agent implementation
  - [ ] 6.1 Implement MusicBrainz API client
    - Create `src/agents/musicbrainz_agent.py` with `MusicBrainzAgent` class
    - Implement `fetch_musicbrainz_data()` as main entry point
    - Implement `search_recording()` to find recordings by name
    - Implement `get_recording_details()` for detailed metadata
    - Implement `get_artist_relationships()` for collaborations
    - Implement `get_label_info()` for record label data
    - _Requirements: 2.2_
  
  - [ ] 6.2 Implement strict rate limiting for MusicBrainz
    - Enforce 1 request per second rate limit
    - Queue requests when limit is reached
    - Include user agent string with contact email in all requests
    - Handle rate limit errors gracefully
    - Log all API calls to Overmind Lab
    - _Requirements: 16.1, 16.4, 16.7_
  
  - [ ]* 6.3 Write unit tests for MusicBrainz agent
    - Test recording search with valid song name
    - Test rate limiting enforcement (1 req/sec)
    - Test error handling for invalid responses
    - Test user agent header inclusion

- [ ] 7. Last.fm agent implementation
  - [ ] 7.1 Implement Last.fm API client
    - Create `src/agents/lastfm_agent.py` with `LastFMAgent` class
    - Implement `fetch_lastfm_data()` as main entry point
    - Implement `search_track()` to find tracks by name
    - Implement `get_track_info()` for track metadata
    - Implement `get_similar_tracks()` for recommendations
    - Implement `get_top_tags()` for user-generated tags
    - _Requirements: 2.3_
  
  - [ ] 7.2 Implement rate limiting and error handling
    - Enforce 5 requests per second rate limit
    - Handle API authentication with API key
    - Handle rate limit errors with retry logic
    - Log all API calls to Overmind Lab
    - _Requirements: 16.3, 16.4_
  
  - [ ]* 7.3 Write unit tests for Last.fm agent
    - Test track search with valid song name
    - Test similar tracks retrieval
    - Test tag extraction
    - Test rate limiting enforcement (5 req/sec)


- [ ] 8. Web scraper agent implementation
  - [ ] 8.1 Implement web scraper for concert and venue data
    - Create `src/agents/scraper_agent.py` with `WebScraperAgent` class
    - Implement `scrape_web_data()` as main entry point
    - Implement `scrape_concert_data()` using BeautifulSoup4
    - Implement `scrape_venue_info()` for venue details
    - Implement `scrape_setlists()` for concert setlists
    - Respect robots.txt and implement polite crawling delays
    - _Requirements: 2.4_
  
  - [ ] 8.2 Implement data extraction and validation
    - Parse HTML using CSS selectors and XPath
    - Extract structured data (dates, locations, performers)
    - Validate and clean scraped data before returning
    - Handle parsing errors gracefully
    - Return "failed" status when scraping blocked or fails
    - _Requirements: 11.3_
  
  - [ ]* 8.3 Write unit tests for web scraper
    - Test HTML parsing with sample concert page
    - Test data extraction and validation
    - Test error handling for invalid HTML
    - Test robots.txt compliance

- [ ] 9. Test multi-agent parallel execution
  - [ ] 9.1 Integrate all four agents into orchestrator
    - Update orchestrator to dispatch all 4 agents: Spotify, MusicBrainz, Last.fm, Scraper
    - Verify parallel execution using asyncio
    - Test with various songs to ensure data merging works
    - _Requirements: 1.1, 12.1, 17.1_
  
  - [ ]* 9.2 Write integration test for multi-agent enrichment
    - Test enrichment with all agents succeeding
    - Test enrichment with some agents failing
    - Test enrichment with agent timeouts
    - Verify merged data contains contributions from all successful agents
    - _Requirements: 1.3, 1.4, 1.5_


- [ ] 10. Data quality tracking implementation
  - [ ] 10.1 Implement quality metrics calculation
    - Create `src/self_improvement/quality_tracker.py` with `QualityTracker` class
    - Implement `analyze_data_quality()` to process agent results
    - Calculate completeness, accuracy, freshness, response time metrics
    - Use exponential moving average for metric updates
    - Calculate overall accuracy score combining all metrics
    - _Requirements: 4.1, 4.2, 4.3_
  
  - [ ] 10.2 Implement quality metrics persistence and logging
    - Persist quality metrics to Redis or database
    - Load historical metrics for each agent
    - Log all metrics to Overmind Lab for visualization
    - Ensure all scores remain between 0.0 and 1.0
    - Ensure success_rate calculation is correct
    - _Requirements: 4.4, 4.5, 4.6, 4.7_
  
  - [ ]* 10.3 Write property test for quality metrics validity
    - **Property 3: Quality Metrics Validity**
    - **Validates: Requirements 4.6, 4.7**
    - Generate random agent results with various success/failure patterns
    - Verify all scores remain between 0.0 and 1.0
    - Verify success_rate = (total_requests - failed_requests) / total_requests
    - Verify request counts are non-negative
    - Verify failed_requests <= total_requests
  
  - [ ] 10.3 Implement source quality rankings
    - Create `get_source_quality_report()` method
    - Rank agents by overall accuracy score
    - Use rankings in conflict resolution during merge
    - Update rankings after each enrichment cycle
    - _Requirements: 4.3, 17.3_

- [ ] 11. Checkpoint - Verify quality tracking works
  - Enrich multiple songs and verify quality metrics are updated
  - Verify source rankings change based on performance
  - Verify metrics are logged to Overmind Lab
  - Ensure all tests pass, ask the user if questions arise.


- [ ] 12. Proactive enrichment implementation
  - [ ] 12.1 Implement incomplete node identification
    - Create `src/self_improvement/enrichment_scheduler.py` with `EnrichmentScheduler` class
    - Implement `identify_incomplete_nodes()` to find nodes with completeness < 0.7
    - Identify missing fields for each incomplete node
    - Determine which agents can provide missing fields
    - Create enrichment tasks with priority based on completeness
    - _Requirements: 5.1, 5.2, 5.3, 5.4_
  
  - [ ] 12.2 Implement stale node detection
    - Check for nodes not enriched in 30 days
    - Create low-priority enrichment tasks for stale nodes
    - Log enrichment opportunities to Overmind Lab
    - _Requirements: 5.5_
  
  - [ ]* 12.3 Write property test for proactive enrichment scheduling
    - **Property 8: Proactive Enrichment Scheduling**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**
    - Generate random nodes with varying completeness scores
    - Verify nodes with completeness < 0.7 have enrichment tasks
    - Verify each task has at least one target agent
    - Verify missing fields are valid for node type
  
  - [ ]* 12.4 Write property test for stale node detection
    - **Property 11: Stale Node Detection**
    - **Validates: Requirements 5.5**
    - Generate random nodes with varying last_enriched timestamps
    - Verify nodes not enriched in 30 days have low-priority tasks
  
  - [ ] 12.5 Implement enrichment task scheduling
    - Implement `schedule_proactive_enrichment()` method
    - Schedule high-priority tasks immediately
    - Schedule medium-priority tasks within 1 hour
    - Schedule low-priority tasks within 24 hours
    - Use background task queue (asyncio or Celery)
    - Deduplicate tasks for same node
    - _Requirements: 5.6, 5.7_
  
  - [ ]* 12.6 Write property test for enrichment task priority
    - **Property 5: Enrichment Task Priority**
    - **Validates: Requirements 5.4**
    - Generate random nodes with various completeness scores
    - Verify priority correctly maps to completeness ranges
    - Verify all tasks have valid priority values (high, medium, low)


- [ ] 13. User feedback integration
  - [ ] 13.1 Implement user feedback processing
    - Create `src/self_improvement/feedback_processor.py` with `FeedbackProcessor` class
    - Implement `process_user_feedback()` method
    - Handle "like" feedback: increase user_satisfaction_score for sources
    - Handle "dislike" feedback: decrease scores and schedule re-enrichment
    - Handle "correction" feedback: update node and penalize incorrect sources
    - Handle "report" feedback: create issue report and reduce visibility
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_
  
  - [ ] 13.2 Implement feedback logging and persistence
    - Log all feedback events to Overmind Lab
    - Persist feedback for historical analysis
    - Update source quality metrics based on feedback
    - _Requirements: 6.7_
  
  - [ ]* 13.3 Write property test for user feedback impact
    - **Property 7: User Feedback Impact**
    - **Validates: Requirements 6.3, 6.4**
    - Generate random correction feedback
    - Verify corresponding node is updated with corrected data
    - Verify node includes "user_correction" as data source
    - Verify last_enriched timestamp is after feedback timestamp
  
  - [ ]* 13.4 Write property test for user feedback processing
    - **Property 12: User Feedback Processing**
    - **Validates: Requirements 6.1, 6.2, 6.5, 6.6, 6.7**
    - Generate random feedback (like, dislike, correction, report)
    - Verify quality scores are updated appropriately
    - Verify events are logged to Overmind Lab

- [ ] 14. Wire self-improvement engine into orchestrator
  - [ ] 14.1 Integrate quality tracking into enrichment flow
    - Call `analyze_data_quality()` after merging results
    - Update source rankings after each enrichment
    - Use rankings in conflict resolution
    - _Requirements: 4.1, 4.3, 17.2, 17.3_
  
  - [ ] 14.2 Integrate proactive enrichment into enrichment flow
    - Call `identify_incomplete_nodes()` after persisting to graph
    - Schedule enrichment tasks for incomplete nodes
    - Log self-improvement activities to Overmind Lab
    - _Requirements: 5.1, 5.6, 17.4_
  
  - [ ]* 14.3 Write integration test for self-improvement cycle
    - Enrich multiple songs with varying data quality
    - Verify quality metrics are updated correctly
    - Verify source rankings change based on performance
    - Verify incomplete nodes are identified and scheduled
    - _Requirements: 17.2, 17.3, 17.4_

- [ ] 15. Checkpoint - Verify self-improvement engine works
  - Test complete self-improvement cycle end-to-end
  - Verify quality metrics improve over time
  - Verify proactive enrichment tasks are scheduled
  - Verify user feedback updates quality scores
  - Ensure all tests pass, ask the user if questions arise.


### Phase 3: Frontend and Social Features (Hours 20-36)

- [ ] 16. Backend API for web frontend
  - [ ] 16.1 Create FastAPI application with REST endpoints
    - Create `src/api/main.py` with FastAPI app
    - Implement `/api/search` endpoint for song enrichment
    - Implement `/api/graph/{node_id}` endpoint for graph traversal
    - Implement `/api/feedback` endpoint for user feedback
    - Implement `/api/activity` endpoint for activity feed
    - Enable CORS for frontend access
    - _Requirements: 8.1, 8.2, 9.1_
  
  - [ ] 16.2 Implement graph traversal endpoint
    - Create `traverse_graph_for_visualization()` function
    - Implement breadth-first traversal with max depth limit (1-5)
    - Ensure no node is visited more than once
    - Ensure all edges reference nodes in result
    - Limit result to maximum 1000 nodes
    - Return results within 500ms for depth 2, 1s for depth 3
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 12.6_
  
  - [ ]* 16.3 Write property test for graph traversal completeness
    - **Property 4: Graph Traversal Completeness**
    - **Validates: Requirements 7.2, 7.3, 7.4**
    - Generate random graph structures
    - Verify traversal contains at least start node as first element
    - Verify all edges reference nodes in result
    - Verify no node exceeds max depth limit
    - Verify no node is visited more than once
  
  - [ ]* 16.4 Write property test for graph traversal limits
    - **Property 19: Graph Traversal Limits**
    - **Validates: Requirements 12.6**
    - Generate large graph structures
    - Verify result is limited to maximum 1000 nodes
  
  - [ ] 16.5 Implement authentication endpoints
    - Implement `/api/auth/register` for user registration
    - Implement `/api/auth/login` for JWT token generation
    - Implement `/api/auth/refresh` for token refresh
    - Hash passwords using bcrypt with salt
    - Set access token expiration to 1 hour
    - Set refresh token expiration to 7 days
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_
  
  - [ ]* 16.6 Write property test for authentication token management
    - **Property 16: Authentication Token Management**
    - **Validates: Requirements 10.4, 10.5, 10.6**
    - Generate random JWT tokens
    - Verify access tokens expire in 1 hour
    - Verify refresh tokens expire in 7 days
    - Verify feedback operations require valid token


  - [ ] 16.7 Implement input validation and security
    - Validate all user inputs against whitelist patterns
    - Limit song name input to 200 characters
    - Sanitize user-generated content to prevent XSS
    - Implement CSRF tokens for state-changing operations
    - Implement rate limiting: 10 search requests per minute per user
    - _Requirements: 12.5, 13.2, 13.3, 13.4, 13.5_
  
  - [ ]* 16.8 Write property test for input validation and security
    - **Property 17: Input Validation and Security**
    - **Validates: Requirements 13.2, 13.3, 13.4, 13.5**
    - Generate random user inputs including malicious patterns
    - Verify inputs are validated against whitelist
    - Verify song names are limited to 200 characters
    - Verify XSS patterns are sanitized
    - Verify CSRF tokens are required for state changes

- [ ] 17. React frontend application
  - [ ] 17.1 Set up React project with TypeScript and Vite
    - Initialize React project with Vite
    - Install dependencies: React Router, Axios, TanStack Query, Tailwind CSS
    - Create project structure: `components/`, `pages/`, `hooks/`, `utils/`
    - Configure Tailwind CSS for styling
    - _Requirements: 8.1_
  
  - [ ] 17.2 Implement search interface
    - Create `SearchPage` component with search input
    - Implement search form with validation
    - Display loading indicator during enrichment
    - Display error messages with retry option
    - Navigate to graph visualization on success
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_
  
  - [ ]* 17.3 Write unit tests for search interface
    - Test search form submission
    - Test loading state display
    - Test error handling and retry
    - Test navigation on success


- [ ] 18. Graph visualization implementation
  - [ ] 18.1 Implement graph visualization with D3.js or Cytoscape.js
    - Create `GraphVisualization` component
    - Render nodes and edges from API response
    - Implement force-directed layout for node positioning
    - Color-code nodes by type (Song, Artist, Album, etc.)
    - Display node labels and edge types
    - _Requirements: 7.7, 8.4_
  
  - [ ] 18.2 Implement interactive graph navigation
    - Implement node click to expand neighbors
    - Implement zoom and pan controls
    - Display node details panel on hover/click
    - Show completeness score for each node
    - Implement depth control slider (1-5)
    - _Requirements: 7.7, 8.6, 8.7_
  
  - [ ]* 18.3 Write unit tests for graph visualization
    - Test graph rendering with sample data
    - Test node click expansion
    - Test zoom and pan controls
    - Test node detail panel display

- [ ] 19. Social features implementation
  - [ ] 19.1 Implement user authentication UI
    - Create `LoginPage` and `RegisterPage` components
    - Implement login form with email and password
    - Implement registration form with validation
    - Store JWT tokens in localStorage
    - Implement automatic token refresh
    - Redirect to login on token expiration
    - _Requirements: 10.1, 10.3, 10.7_
  
  - [ ] 19.2 Implement feedback UI
    - Add like/dislike buttons to node detail panel
    - Create correction form for user corrections
    - Create report form for issue reporting
    - Send feedback to backend API
    - Display feedback confirmation messages
    - _Requirements: 6.1, 6.2, 6.3, 6.5, 9.6, 9.7_
  
  - [ ] 19.3 Implement activity feed
    - Create `ActivityFeed` component
    - Display recent song enrichments by all users
    - Show timestamp and user identifier for each activity
    - Auto-refresh feed every 30 seconds
    - _Requirements: 9.1, 9.2_
  
  - [ ] 19.4 Implement sharing functionality
    - Add share button to graph visualization
    - Generate unique URL for current graph view
    - Copy URL to clipboard on share
    - Support loading shared graph views
    - _Requirements: 9.3, 9.4, 9.5_
  
  - [ ]* 19.5 Write unit tests for social features
    - Test authentication flow
    - Test feedback submission
    - Test activity feed display
    - Test sharing functionality


- [ ] 20. Error handling and resilience
  - [ ] 20.1 Implement comprehensive error handling in backend
    - Handle agent timeouts after 30 seconds
    - Handle API rate limit errors (429) with retry logic
    - Handle database connection failures with retry and backoff
    - Handle concurrent write conflicts with optimistic locking
    - Log all errors to Overmind Lab with full context
    - _Requirements: 11.1, 11.2, 11.4, 11.6, 11.7_
  
  - [ ]* 20.2 Write property test for error resilience
    - **Property 18: Error Resilience**
    - **Validates: Requirements 11.1, 11.2, 11.4, 11.6**
    - Simulate agent timeouts and failures
    - Verify orchestrator marks results as failed
    - Verify orchestrator continues with other results
    - Verify errors are logged to Overmind Lab
    - Verify retry logic with exponential backoff
  
  - [ ] 20.3 Implement data validation in backend
    - Validate all node fields before persistence
    - Reject invalid fields but accept valid fields
    - Validate edge references to existing nodes
    - Ensure at least one external ID for each node
    - _Requirements: 11.3, 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7_
  
  - [ ]* 20.4 Write property test for data validation
    - **Property 13: Data Validation**
    - **Validates: Requirements 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7**
    - Generate random nodes with invalid fields
    - Verify validation rejects invalid fields
    - Verify validation accepts valid fields
    - Verify required constraints are enforced

- [ ] 21. Checkpoint - Verify frontend and backend integration
  - Test complete user flow: search → visualization → feedback
  - Verify authentication works correctly
  - Verify graph visualization displays correctly
  - Verify social features work end-to-end
  - Ensure all tests pass, ask the user if questions arise.


### Phase 4: Demo Preparation and Deployment (Hours 36-48)

- [ ] 22. Self-improvement demonstration preparation
  - [ ] 22.1 Create demo script showing measurable improvement
    - Enrich 10-15 songs to generate quality metrics
    - Document initial completeness scores and source rankings
    - Run proactive enrichment tasks
    - Document improved completeness scores
    - Show source rankings changing based on performance
    - _Requirements: 17.2, 17.3_
  
  - [ ] 22.2 Prepare Overmind Lab dashboards
    - Create dashboard showing quality metrics over time
    - Create dashboard showing agent performance comparison
    - Create dashboard showing completeness score trends
    - Create dashboard showing proactive enrichment activity
    - Export screenshots for demo video
    - _Requirements: 14.4, 17.5_
  
  - [ ] 22.3 Create demo data showing graph connections
    - Enrich songs that reveal interesting artist connections
    - Find examples of artists connected through venues or labels
    - Find examples of instrument credits across albums
    - Prepare graph visualizations for demo
    - _Requirements: 17.6_

- [ ] 23. TrueFoundry deployment
  - [ ] 23.1 Create TrueFoundry deployment configuration
    - Create `truefoundry.yaml` for service definitions
    - Configure backend service with environment variables
    - Configure frontend service with build settings
    - Configure Aerospike Graph and Redis as managed services
    - Set up secrets for API keys
    - _Requirements: 17.7_
  
  - [ ] 23.2 Deploy backend services to TrueFoundry
    - Build Docker image for backend
    - Push image to container registry
    - Deploy using TrueFoundry CLI
    - Configure environment variables and secrets
    - Verify deployment health checks
    - Test API endpoints on deployed service
  
  - [ ] 23.3 Deploy frontend to TrueFoundry
    - Build production frontend bundle
    - Create Docker image for frontend
    - Deploy using TrueFoundry CLI
    - Configure CORS for backend API
    - Verify frontend loads and connects to backend
  
  - [ ] 23.4 Configure production monitoring
    - Enable Overmind Lab tracing in production
    - Set up error alerting
    - Configure performance monitoring
    - Test end-to-end flow in production


- [ ] 24. Documentation and demo video
  - [ ] 24.1 Write comprehensive README
    - Document project overview and architecture
    - Document setup instructions for local development
    - Document API endpoints and usage
    - Document deployment process
    - Include architecture diagrams
    - Document hackathon judging criteria alignment
  
  - [ ] 24.2 Record demo video (max 3 minutes)
    - **Minute 1: Problem and Solution**
      - Explain fragmented music data problem
      - Show architecture with orchestrator and 4 agents
      - Introduce MusicMind as solution
    - **Minute 2: Autonomous Behavior and Self-Improvement**
      - Live demo: search for "Bohemian Rhapsody"
      - Show Overmind Lab trace with parallel agents
      - Show graph visualization
      - Show self-improvement engine identifying incomplete nodes
      - Show quality metrics dashboard
    - **Minute 3: Learning and Impact**
      - Show user correction being applied
      - Show before/after metrics (completeness improvement)
      - Show graph revealing artist connections
      - Emphasize measurable learning over time
      - Show deployed application URL
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7_
  
  - [ ] 24.3 Create presentation slides
    - Slide 1: Problem statement
    - Slide 2: Architecture overview
    - Slide 3: Autonomous agent behavior
    - Slide 4: Self-improvement capabilities
    - Slide 5: Technical implementation highlights
    - Slide 6: Demo results and metrics
    - Slide 7: Future enhancements
  
  - [ ] 24.4 Write DevPost submission
    - Write project description
    - List technologies used
    - Explain how it meets hackathon criteria
    - Include demo video link
    - Include deployed application link
    - Include GitHub repository link


- [ ] 25. Final testing and polish
  - [ ] 25.1 Run comprehensive end-to-end tests
    - Test complete enrichment flow with all agents
    - Test self-improvement cycle with multiple songs
    - Test user feedback integration
    - Test graph visualization with complex graphs
    - Test authentication and authorization
    - Test error handling and resilience
  
  - [ ] 25.2 Performance optimization
    - Profile API response times
    - Optimize database queries with indexes
    - Optimize graph traversal performance
    - Verify cache hit rates are acceptable
    - Verify rate limiting works correctly
    - _Requirements: 12.1, 12.2, 12.3, 12.4_
  
  - [ ]* 25.3 Write property test for cache behavior
    - **Property 20: Cache Behavior**
    - **Validates: Requirements 12.2**
    - Enrich same song multiple times
    - Verify first request takes longer (cold cache)
    - Verify subsequent requests return cached results
    - Verify cache expires after 1 hour
  
  - [ ] 25.4 Security audit
    - Verify HTTPS/TLS is enabled in production
    - Verify API keys are stored in environment variables
    - Verify passwords are hashed with bcrypt
    - Verify input validation is working
    - Verify CSRF protection is enabled
    - Verify rate limiting is enforced
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6_
  
  - [ ] 25.5 Fix any remaining bugs
    - Review error logs from testing
    - Fix critical bugs blocking demo
    - Fix UI/UX issues
    - Test fixes thoroughly
  
  - [ ] 25.6 Final demo rehearsal
    - Run through complete demo script
    - Verify all features work as expected
    - Time demo to ensure it fits in 3 minutes
    - Prepare backup plan for live demo failures

- [ ] 26. Final checkpoint - Submit to hackathon
  - Verify all core features are working
  - Verify demo video is uploaded
  - Verify application is deployed and accessible
  - Submit to DevPost
  - Celebrate! 🎉


## Notes

- Tasks marked with `*` are optional property-based tests and can be skipped for faster MVP delivery
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at key milestones
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The implementation uses Python for all backend services as selected by the user
- Frontend uses React with TypeScript for type safety
- All agents integrate with Overmind Lab for distributed tracing
- Self-improvement is a core feature and must be demonstrated for hackathon judging
- Focus on delivering working demo over perfect code quality given 48-hour timeline

## Priority Guidance

**Must-Have for Demo (Critical Path):**
1. Orchestrator with parallel agent dispatch (Tasks 3, 4)
2. At least 2 working agents: Spotify + MusicBrainz (Tasks 4, 6)
3. Aerospike Graph database with basic schema (Task 2)
4. Quality tracking showing measurable improvement (Task 10)
5. Proactive enrichment scheduling (Task 12)
6. Basic web frontend with search and visualization (Tasks 16, 17, 18)
7. Overmind Lab integration for tracing (Tasks 3.5, 10.2)
8. Deployment to TrueFoundry (Task 23)
9. Demo video showing self-improvement (Task 24.2)

**Nice-to-Have (If Time Permits):**
1. All 4 agents working (Last.fm + Web Scraper)
2. User feedback integration (Task 13)
3. Social features (activity feed, sharing) (Task 19)
4. Authentication (Task 16.5, 19.1)
5. All property-based tests
6. Performance optimization (Task 25.2)

**Fallback Plan (If Behind Schedule):**
- Skip web scraper agent (focus on 3 API-based agents)
- Skip social features (focus on core enrichment)
- Skip authentication (use demo mode)
- Create CLI demo instead of web frontend
- Use local deployment instead of TrueFoundry

