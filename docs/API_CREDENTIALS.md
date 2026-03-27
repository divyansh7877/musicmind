# API Credentials Setup Guide

This guide explains how to obtain the required API credentials for the MusicMind Agent Platform.

## Spotify API Credentials

### Steps to Obtain Spotify API Credentials

1. **Create a Spotify Account** (if you don't have one)
   - Visit [spotify.com](https://www.spotify.com) and sign up

2. **Access Spotify Developer Dashboard**
   - Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
   - Log in with your Spotify account

3. **Create a New App**
   - Click "Create app" button
   - Fill in the required information:
     - **App name**: MusicMind Agent Platform (or your preferred name)
     - **App description**: Music data enrichment platform
     - **Redirect URI**: http://localhost:8000/callback (for development)
     - **API/SDKs**: Check "Web API"
   - Accept the Terms of Service
   - Click "Save"

4. **Get Your Credentials**
   - On your app's dashboard, click "Settings"
   - You'll see:
     - **Client ID**: Copy this value
     - **Client Secret**: Click "View client secret" and copy this value
   - Add these to your `.env` file:
     ```
     SPOTIFY_CLIENT_ID=your_client_id_here
     SPOTIFY_CLIENT_SECRET=your_client_secret_here
     ```

### Rate Limits
- Spotify allows 100 requests per minute with burst allowance
- The platform automatically handles rate limiting

---

## Last.fm API Key

### Steps to Obtain Last.fm API Key

1. **Create a Last.fm Account** (if you don't have one)
   - Visit [last.fm](https://www.last.fm) and sign up

2. **Access API Account Creation**
   - Go to [last.fm/api/account/create](https://www.last.fm/api/account/create)
   - Log in with your Last.fm account

3. **Create API Account**
   - Fill in the required information:
     - **Application name**: MusicMind Agent Platform
     - **Application description**: Autonomous music data enrichment platform
     - **Callback URL**: http://localhost:8000/callback (for development)
   - Accept the Terms of Service
   - Click "Submit"

4. **Get Your API Key**
   - After submission, you'll see your API credentials:
     - **API Key**: Copy this value
     - **Shared Secret**: (not needed for read-only operations)
   - Add the API key to your `.env` file:
     ```
     LASTFM_API_KEY=your_api_key_here
     ```

### Rate Limits
- Last.fm allows 5 requests per second
- The platform automatically handles rate limiting

---

## MusicBrainz User Agent

### Configuration Requirements

MusicBrainz requires a user agent string with contact information for all API requests.

1. **Format Your User Agent**
   - Format: `ApplicationName/Version (contact@email.com)`
   - Example: `MusicMindAgent/0.1.0 (yourname@example.com)`

2. **Update Configuration**
   - Add to your `.env` file:
     ```
     MUSICBRAINZ_USER_AGENT=MusicMindAgent/0.1.0 (your_email@example.com)
     ```
   - Replace `your_email@example.com` with your actual email address

### Rate Limits
- MusicBrainz allows 1 request per second
- The platform automatically handles rate limiting
- **Important**: Always include a valid contact email in the user agent

### No API Key Required
- MusicBrainz does not require API key registration
- Just provide a proper user agent string with contact information

---

## Overmind Lab Configuration (Optional)

Overmind Lab is used for distributed tracing and monitoring.

### Steps to Obtain Overmind Lab API Key

1. **Sign Up for Overmind Lab**
   - Visit [overmind.com](https://overmind.com) (or your tracing provider)
   - Create an account

2. **Create a New Project**
   - Navigate to your dashboard
   - Create a new project for MusicMind

3. **Get Your API Key**
   - Go to project settings
   - Copy your API key
   - Add to your `.env` file:
     ```
     OVERMIND_API_KEY=your_overmind_api_key_here
     OVERMIND_ENDPOINT=https://api.overmind.com
     ```

### Note
- Overmind Lab integration is optional for development
- The platform will work without it, but tracing features will be disabled

---

## Complete .env Configuration

After obtaining all credentials, your `.env` file should look like this:

```bash
# External API Credentials
SPOTIFY_CLIENT_ID=abc123def456
SPOTIFY_CLIENT_SECRET=xyz789uvw012
LASTFM_API_KEY=1234567890abcdef
MUSICBRAINZ_USER_AGENT=MusicMindAgent/0.1.0 (yourname@example.com)

# Database Configuration
AEROSPIKE_HOST=localhost
AEROSPIKE_PORT=3000
AEROSPIKE_NAMESPACE=musicmind

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0
REDIS_MAX_MEMORY=2gb

# Application Configuration
APP_ENV=development
APP_HOST=0.0.0.0
APP_PORT=8000
SECRET_KEY=generate_a_secure_random_key_here
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Overmind Lab Configuration (Optional)
OVERMIND_API_KEY=your_overmind_api_key_here
OVERMIND_ENDPOINT=https://api.overmind.com

# Rate Limiting
RATE_LIMIT_REQUESTS_PER_MINUTE=10

# Cache Configuration
CACHE_TTL_SECONDS=3600

# Agent Timeouts (milliseconds)
AGENT_TIMEOUT_MS=30000

# Self-Improvement Configuration
COMPLETENESS_THRESHOLD=0.7
ENRICHMENT_STALE_DAYS=30
```

---

## Security Best Practices

1. **Never commit `.env` file to version control**
   - The `.gitignore` file already excludes it

2. **Generate a secure SECRET_KEY**
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

3. **Use different credentials for production**
   - Create separate API applications for production
   - Use environment-specific configuration

4. **Rotate credentials regularly**
   - Change API keys periodically
   - Update SECRET_KEY when deploying to production

---

## Troubleshooting

### Spotify API Issues
- **401 Unauthorized**: Check that Client ID and Secret are correct
- **429 Rate Limited**: The platform will automatically retry after the specified delay

### Last.fm API Issues
- **Invalid API Key**: Verify the API key is copied correctly
- **403 Forbidden**: Check that your API account is active

### MusicBrainz Issues
- **503 Service Unavailable**: You may be exceeding the 1 req/sec rate limit
- **User Agent Error**: Ensure your user agent includes a valid email address

### General Issues
- **Environment variables not loading**: Ensure `.env` file is in the project root
- **Import errors**: Verify all dependencies are installed with `pip install -e ".[dev]"`
