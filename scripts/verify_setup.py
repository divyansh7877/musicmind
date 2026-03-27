#!/usr/bin/env python3
"""Verify MusicMind Agent Platform setup and configuration."""

import os
import sys
from pathlib import Path


def check_python_version():
    """Check Python version is 3.11 or higher."""
    print("Checking Python version...")
    if sys.version_info < (3, 11):
        print(f"❌ Python 3.11+ required, found {sys.version_info.major}.{sys.version_info.minor}")
        return False
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    return True


def check_env_file():
    """Check if .env file exists and has required variables."""
    print("\nChecking .env file...")
    env_path = Path(".env")
    
    if not env_path.exists():
        print("❌ .env file not found. Copy .env.example to .env and configure it.")
        return False
    
    print("✅ .env file exists")
    
    required_vars = [
        "SPOTIFY_CLIENT_ID",
        "SPOTIFY_CLIENT_SECRET",
        "LASTFM_API_KEY",
        "MUSICBRAINZ_USER_AGENT",
        "SECRET_KEY",
    ]
    
    missing_vars = []
    placeholder_vars = []
    
    with open(env_path) as f:
        env_content = f.read()
        for var in required_vars:
            if var not in env_content:
                missing_vars.append(var)
            elif f"{var}=your_" in env_content or f"{var}=change_" in env_content:
                placeholder_vars.append(var)
    
    if missing_vars:
        print(f"❌ Missing required variables: {', '.join(missing_vars)}")
        return False
    
    if placeholder_vars:
        print(f"⚠️  Warning: Placeholder values detected for: {', '.join(placeholder_vars)}")
        print("   Update these with actual credentials before running the application.")
        return True
    
    print("✅ All required environment variables configured")
    return True


def check_project_structure():
    """Check if project structure is correct."""
    print("\nChecking project structure...")
    
    required_dirs = ["src", "tests", "config", "scripts", "docs"]
    required_files = [
        "pyproject.toml",
        "docker-compose.yml",
        ".gitignore",
        "README.md",
        "config/settings.py",
        "docs/API_CREDENTIALS.md",
    ]
    
    all_good = True
    
    for dir_name in required_dirs:
        if not Path(dir_name).is_dir():
            print(f"❌ Missing directory: {dir_name}")
            all_good = False
    
    for file_name in required_files:
        if not Path(file_name).is_file():
            print(f"❌ Missing file: {file_name}")
            all_good = False
    
    if all_good:
        print("✅ Project structure is correct")
    
    return all_good


def check_git_repository():
    """Check if git repository is initialized."""
    print("\nChecking git repository...")
    
    if not Path(".git").is_dir():
        print("❌ Git repository not initialized. Run: git init")
        return False
    
    print("✅ Git repository initialized")
    return True


def check_dependencies():
    """Check if dependencies can be imported."""
    print("\nChecking Python dependencies...")
    
    required_packages = [
        "fastapi",
        "uvicorn",
        "httpx",
        "redis",
        "pydantic",
        "pydantic_settings",
        "pytest",
        "hypothesis",
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"❌ Missing packages: {', '.join(missing_packages)}")
        print('   Install with: pip install -e ".[dev]"')
        return False
    
    print("✅ All required packages installed")
    return True


def check_docker():
    """Check if Docker is available."""
    print("\nChecking Docker...")
    
    import subprocess
    
    try:
        result = subprocess.run(
            ["docker", "--version"],
            capture_output=True,
            text=True,
            check=True,
        )
        print(f"✅ {result.stdout.strip()}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Docker not found. Install Docker Desktop or Docker Engine.")
        return False


def check_docker_compose():
    """Check if Docker Compose is available."""
    print("\nChecking Docker Compose...")
    
    import subprocess
    
    try:
        result = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
            check=True,
        )
        print(f"✅ {result.stdout.strip()}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Docker Compose not found. Install Docker Compose.")
        return False


def main():
    """Run all verification checks."""
    print("=" * 60)
    print("MusicMind Agent Platform - Setup Verification")
    print("=" * 60)
    
    checks = [
        check_python_version,
        check_project_structure,
        check_git_repository,
        check_env_file,
        check_dependencies,
        check_docker,
        check_docker_compose,
    ]
    
    results = [check() for check in checks]
    
    print("\n" + "=" * 60)
    print("Verification Summary")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    
    print(f"\nPassed: {passed}/{total} checks")
    
    if all(results):
        print("\n✅ All checks passed! Your setup is ready.")
        print("\nNext steps:")
        print("1. Start infrastructure: docker compose up -d")
        print("2. Run the application: uvicorn src.main:app --reload")
        print("3. Visit: http://localhost:8000")
        return 0
    else:
        print("\n❌ Some checks failed. Please fix the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
