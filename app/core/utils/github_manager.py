"""
GitHub Integration Manager
==========================

Secure GitHub integration using Personal Access Tokens from environment variables.
Handles repository creation, initialization, and version release management.

Version: 1.0
"""

__version__ = "1.0"

import os
import subprocess
from pathlib import Path

import requests
from pydantic import BaseModel, Field


class GitHubConfig(BaseModel):
    """GitHub configuration from environment variables"""

    token: str = Field(description="GitHub Personal Access Token")
    username: str = Field(description="GitHub username")
    email: str = Field(description="Git commit email")
    repo_name: str | None = Field(default="skuel0", description="Repository name")
    repo_description: str | None = Field(
        default="SKUEL - Personal Knowledge Management System", description="Repository description"
    )
    private: bool = Field(default=False, description="Create private repository")
    default_branch: str = Field(default="main", description="Default branch name")

    @classmethod
    def from_env(cls) -> "GitHubConfig":
        """Load configuration from environment variables"""
        return cls(
            token=os.getenv("GITHUB_TOKEN", ""),
            username=os.getenv("GITHUB_USERNAME", ""),
            email=os.getenv("GITHUB_EMAIL", "git@example.com"),
            repo_name=os.getenv("GITHUB_REPO_NAME", "skuel0"),
            repo_description=os.getenv(
                "GITHUB_REPO_DESCRIPTION", "SKUEL - Personal Knowledge Management System"
            ),
            private=os.getenv("GITHUB_PRIVATE", "false").lower() == "true",
            default_branch=os.getenv("GITHUB_DEFAULT_BRANCH", "main"),
        )


class GitHubManager:
    """Manages GitHub operations securely using PAT from environment"""

    def __init__(self, config: GitHubConfig | None = None) -> None:
        self.config = config or GitHubConfig.from_env()
        self.api_base = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {self.config.token}",
            "Accept": "application/vnd.github.v3+json",
        }
        self.root_path = Path.cwd()

    def validate_credentials(self) -> tuple[bool, str]:
        """Validate GitHub credentials"""
        if not self.config.token:
            return False, "GitHub token not configured in environment"

        if not self.config.username:
            return False, "GitHub username not configured in environment"

        # Test API access
        response = requests.get(f"{self.api_base}/user", headers=self.headers)
        if response.status_code == 200:
            user_data = response.json()
            return True, f"Authenticated as {user_data.get('login', 'unknown')}"
        elif response.status_code == 401:
            return False, "Invalid GitHub token"
        else:
            return False, f"GitHub API error: {response.status_code}"

    def init_git_repo(self) -> tuple[bool, str]:
        """Initialize local git repository"""
        try:
            # Check if already initialized
            result = subprocess.run(
                ["git", "status"], capture_output=True, text=True, cwd=self.root_path
            )

            if result.returncode != 0:
                # Initialize repository
                subprocess.run(
                    ["git", "init", "-b", self.config.default_branch],
                    check=True,
                    capture_output=True,
                    cwd=self.root_path,
                )

                # Configure git user
                subprocess.run(
                    ["git", "config", "user.name", self.config.username],
                    check=True,
                    cwd=self.root_path,
                )
                subprocess.run(
                    ["git", "config", "user.email", self.config.email],
                    check=True,
                    cwd=self.root_path,
                )

                return True, f"Initialized git repository with branch {self.config.default_branch}"
            else:
                return True, "Git repository already initialized"

        except subprocess.CalledProcessError as e:
            return False, f"Failed to initialize git repository: {e}"
        except FileNotFoundError:
            return False, "Git is not installed. Please install git first."

    def create_github_repo(self) -> tuple[bool, dict]:
        """Create GitHub repository via API"""
        create_url = f"{self.api_base}/user/repos"

        data = {
            "name": self.config.repo_name,
            "description": self.config.repo_description,
            "private": self.config.private,
            "auto_init": False,  # We'll push our own initial commit
            "default_branch": self.config.default_branch,
        }

        response = requests.post(create_url, json=data, headers=self.headers)

        if response.status_code == 201:
            repo_data = response.json()
            return True, {
                "clone_url": repo_data["clone_url"],
                "ssh_url": repo_data["ssh_url"],
                "html_url": repo_data["html_url"],
                "full_name": repo_data["full_name"],
            }
        elif response.status_code == 422:
            # Repository already exists
            repo_url = f"{self.api_base}/repos/{self.config.username}/{self.config.repo_name}"
            check_response = requests.get(repo_url, headers=self.headers)
            if check_response.status_code == 200:
                repo_data = check_response.json()
                return True, {
                    "clone_url": repo_data["clone_url"],
                    "ssh_url": repo_data["ssh_url"],
                    "html_url": repo_data["html_url"],
                    "full_name": repo_data["full_name"],
                    "existing": True,
                }
            else:
                return False, {"error": "Repository name already taken"}
        else:
            return False, {"error": f"Failed to create repository: {response.json()}"}

    def add_remote(self, remote_url: str) -> tuple[bool, str]:
        """Add GitHub remote to local repository"""
        try:
            # Check if remote already exists
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                cwd=self.root_path,
            )

            if result.returncode == 0:
                # Update existing remote
                subprocess.run(
                    ["git", "remote", "set-url", "origin", remote_url],
                    check=True,
                    cwd=self.root_path,
                )
                return True, f"Updated remote origin to {remote_url}"
            else:
                # Add new remote
                subprocess.run(
                    ["git", "remote", "add", "origin", remote_url], check=True, cwd=self.root_path
                )
                return True, f"Added remote origin: {remote_url}"

        except subprocess.CalledProcessError as e:
            return False, f"Failed to add remote: {e}"

    def create_initial_commit(self) -> tuple[bool, str]:
        """Create initial commit with all files"""
        try:
            # Add all files
            subprocess.run(["git", "add", "-A"], check=True, cwd=self.root_path)

            # Create commit
            commit_message = "Initial commit - Version 1.0\n\nInitialized SKUEL repository with version management system"
            subprocess.run(["git", "commit", "-m", commit_message], check=True, cwd=self.root_path)

            return True, "Created initial commit"

        except subprocess.CalledProcessError as e:
            # Check if there are changes to commit
            result = subprocess.run(
                ["git", "status", "--porcelain"], capture_output=True, text=True, cwd=self.root_path
            )
            if not result.stdout.strip():
                return True, "No changes to commit"
            return False, f"Failed to create commit: {e}"

    def push_to_github(self, force: bool = False) -> tuple[bool, str]:
        """Push local repository to GitHub"""
        try:
            # Build remote URL with token for authentication
            remote_url = f"https://{self.config.username}:{self.config.token}@github.com/{self.config.username}/{self.config.repo_name}.git"

            # Update remote URL with authentication
            self.add_remote(remote_url)

            # Push to GitHub
            push_cmd = ["git", "push", "-u", "origin", self.config.default_branch]
            if force:
                push_cmd.insert(2, "--force")

            result = subprocess.run(push_cmd, capture_output=True, text=True, cwd=self.root_path)

            if result.returncode == 0:
                return True, "Successfully pushed to GitHub"
            else:
                return False, f"Push failed: {result.stderr}"

        except subprocess.CalledProcessError as e:
            return False, f"Failed to push: {e}"

    def create_release(self, version: str, notes: str = "") -> tuple[bool, dict]:
        """Create a GitHub release with version tag"""
        # First create the tag locally
        try:
            subprocess.run(
                ["git", "tag", "-a", f"v{version}", "-m", f"Version {version}"],
                check=True,
                cwd=self.root_path,
            )

            # Push the tag
            subprocess.run(["git", "push", "origin", f"v{version}"], check=True, cwd=self.root_path)
        except subprocess.CalledProcessError:
            pass  # Tag might already exist

        # Create release via API
        release_url = (
            f"{self.api_base}/repos/{self.config.username}/{self.config.repo_name}/releases"
        )

        release_data = {
            "tag_name": f"v{version}",
            "name": f"Version {version}",
            "body": notes
            or f"Release version {version}\n\nGenerated by SKUEL Version Management System",
            "draft": False,
            "prerelease": False,
        }

        response = requests.post(release_url, json=release_data, headers=self.headers)

        if response.status_code == 201:
            release_info = response.json()
            return True, {
                "html_url": release_info["html_url"],
                "tag_name": release_info["tag_name"],
                "created_at": release_info["created_at"],
            }
        else:
            return False, {"error": f"Failed to create release: {response.json()}"}

    def setup_github_repo(self) -> tuple[bool, dict]:
        """Complete GitHub setup process"""
        results = {}

        # Validate credentials
        valid, msg = self.validate_credentials()
        if not valid:
            return False, {"error": msg}
        results["auth"] = msg

        # Initialize git
        success, msg = self.init_git_repo()
        if not success:
            return False, {"error": msg}
        results["git_init"] = msg

        # Create GitHub repo
        success, repo_info = self.create_github_repo()
        if not success:
            return False, repo_info
        results["repo"] = repo_info

        # Add remote
        success, msg = self.add_remote(repo_info["clone_url"])
        if not success:
            return False, {"error": msg}
        results["remote"] = msg

        # Create initial commit
        success, msg = self.create_initial_commit()
        if not success:
            return False, {"error": msg}
        results["commit"] = msg

        # Push to GitHub
        success, msg = self.push_to_github()
        if not success:
            return False, {"error": msg}
        results["push"] = msg

        # Create initial release
        success, release_info = self.create_release(
            "1.0", "Initial release with version management system"
        )
        if success:
            results["release"] = release_info

        return True, results


def main():
    """CLI for GitHub management"""
    import argparse

    parser = argparse.ArgumentParser(description="GitHub Repository Manager")
    parser.add_argument(
        "command", choices=["setup", "validate", "push", "release"], help="Command to execute"
    )
    parser.add_argument("--version", help="Version for release")
    parser.add_argument("--notes", help="Release notes")
    parser.add_argument("--force", action="store_true", help="Force push")

    args = parser.parse_args()

    manager = GitHubManager()

    if args.command == "validate":
        valid, msg = manager.validate_credentials()
        print(f"✅ {msg}" if valid else f"❌ {msg}")

    elif args.command == "setup":
        print("Setting up GitHub repository...")
        success, results = manager.setup_github_repo()

        if success:
            print("\n✅ GitHub setup completed successfully!")
            print(f"\n📦 Repository: {results['repo']['html_url']}")
            if "release" in results:
                print(f"🏷️  Release: {results['release']['html_url']}")
        else:
            print(f"\n❌ Setup failed: {results.get('error', 'Unknown error')}")

    elif args.command == "push":
        success, msg = manager.push_to_github(force=args.force)
        print(f"✅ {msg}" if success else f"❌ {msg}")

    elif args.command == "release" and args.version:
        success, info = manager.create_release(args.version, args.notes or "")
        if success:
            print(f"✅ Created release: {info['html_url']}")
        else:
            print(f"❌ Failed: {info.get('error', 'Unknown error')}")


if __name__ == "__main__":
    main()
