#!/usr/bin/env python3
"""
TrueFoundry deployment script for MusicMind Agent Platform.

Prerequisites:
    pip install truefoundry
    tfy login --host <your-truefoundry-platform-url>

Usage:
    python deploy.py --workspace <workspace-fqn> [--backend-host <host>] [--frontend-host <host>]

Example:
    python deploy.py \
        --workspace "tfy-ws-xxxxx" \
        --backend-host "musicmind-api.your-domain.com" \
        --frontend-host "musicmind.your-domain.com"
"""

import argparse
import sys


def deploy_backend(workspace_fqn: str, host: str) -> None:
    from truefoundry.deploy import (
        Build,
        DockerFileBuild,
        LocalSource,
        Port,
        Resources,
        Service,
    )

    service = Service(
        name="musicmind-backend",
        image=Build(
            build_source=LocalSource(local_build=False),
            build_spec=DockerFileBuild(
                dockerfile_path="Dockerfile",
                build_context_path=".",
            ),
        ),
        ports=[
            Port(
                port=8000,
                host=host,
                path="/",
            ),
        ],
        env={
            "APP_ENV": "production",
            "APP_HOST": "0.0.0.0",
            "APP_PORT": "8000",
            "CACHE_TTL_SECONDS": "3600",
            "AGENT_TIMEOUT_MS": "30000",
            "COMPLETENESS_THRESHOLD": "0.7",
            "ENRICHMENT_STALE_DAYS": "30",
            "RATE_LIMIT_REQUESTS_PER_MINUTE": "10",
        },
        resources=Resources(
            cpu_request=0.5,
            cpu_limit=1.0,
            memory_request=1024,
            memory_limit=2048,
            ephemeral_storage_request=512,
            ephemeral_storage_limit=1024,
        ),
    )

    print(f"Deploying backend to workspace: {workspace_fqn}")
    print(f"Backend host: {host}")
    service.deploy(workspace_fqn=workspace_fqn, wait=False)
    print("Backend deployment initiated.")


def deploy_frontend(workspace_fqn: str, host: str, backend_url: str) -> None:
    from truefoundry.deploy import (
        Build,
        DockerFileBuild,
        LocalSource,
        Port,
        Resources,
        Service,
    )

    service = Service(
        name="musicmind-frontend",
        image=Build(
            build_source=LocalSource(local_build=False),
            build_spec=DockerFileBuild(
                dockerfile_path="frontend/Dockerfile",
                build_context_path="frontend",
                build_args={"VITE_API_URL": backend_url},
            ),
        ),
        ports=[
            Port(
                port=80,
                host=host,
                path="/",
            ),
        ],
        resources=Resources(
            cpu_request=0.25,
            cpu_limit=0.5,
            memory_request=256,
            memory_limit=512,
            ephemeral_storage_request=256,
            ephemeral_storage_limit=512,
        ),
    )

    print(f"Deploying frontend to workspace: {workspace_fqn}")
    print(f"Frontend host: {host}")
    service.deploy(workspace_fqn=workspace_fqn, wait=False)
    print("Frontend deployment initiated.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deploy MusicMind to TrueFoundry",
    )
    parser.add_argument(
        "--workspace",
        required=True,
        help="TrueFoundry workspace FQN (e.g. tfy-ws-xxxxx)",
    )
    parser.add_argument(
        "--backend-host",
        default="musicmind-api.example.com",
        help="Host for backend API endpoint",
    )
    parser.add_argument(
        "--frontend-host",
        default="musicmind.example.com",
        help="Host for frontend endpoint",
    )
    parser.add_argument(
        "--component",
        choices=["backend", "frontend", "all"],
        default="all",
        help="Which component to deploy (default: all)",
    )

    args = parser.parse_args()

    backend_url = f"https://{args.backend_host}"

    try:
        if args.component in ["backend", "all"]:
            deploy_backend(args.workspace, args.backend_host)

        if args.component in ["frontend", "all"]:
            deploy_frontend(args.workspace, args.frontend_host, backend_url)

        print("\nDeployment initiated successfully!")
        print("\nIMPORTANT: Configure these secrets in TrueFoundry dashboard:")
        print("  - SPOTIFY_CLIENT_ID")
        print("  - SPOTIFY_CLIENT_SECRET")
        print("  - LASTFM_API_KEY")
        print("  - SECRET_KEY")
        print("  - OVERMIND_API_KEY")
        print("  - REDIS_HOST / REDIS_PORT (if using managed Redis)")
        print("  - AEROSPIKE_HOST / AEROSPIKE_PORT (if using managed Aerospike)")

        return 0

    except ImportError:
        print("ERROR: truefoundry package not installed.")
        print("Install it with: pip install truefoundry")
        print("Then login with: tfy login --host <your-truefoundry-url>")
        return 1
    except Exception as e:
        print(f"ERROR: Deployment failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
