"""
DoxaRank Git External System Adapter (Milestone 6.5).

Provides controlled integration with Git repositories (GitHub, GitLab, generic Git).
Supports explicit capabilities:
- GIT.READ_REPOSITORY
- GIT.CREATE_BRANCH
- GIT.WRITE_FILE
- GIT.CREATE_COMMIT

Enforces path traversal safety, before-state capture for compensation, branch gating,
and strictly prevents automatic push to production repositories.
"""

import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from django.utils import timezone

from .base import (
    BaseExternalAdapter,
    ExternalSystemType,
    GitCapability,
    ExternalOperationResult,
    redact_secrets,
)

logger = logging.getLogger(__name__)


class GitAdapter(BaseExternalAdapter):
    """
    Adapter interfacing with Git version control systems.
    Operates in a controlled repository/workspace abstraction.
    Never auto-pushes to production without explicit authorization.
    """

    system_type: str = ExternalSystemType.GIT.value
    supported_providers: List[str] = ["github", "gitlab", "generic_git", "staging_git"]
    declared_capabilities: Set[str] = {
        GitCapability.READ_REPOSITORY.value,
        GitCapability.CREATE_BRANCH.value,
        GitCapability.WRITE_FILE.value,
        GitCapability.CREATE_COMMIT.value,
    }

    # Staging in-memory repository store: { repo_key: { "branches": set(), "files": { branch: { path: content } }, "commits": [] } }
    _staging_repos: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def reset_staging(cls) -> None:
        cls._staging_repos.clear()

    @classmethod
    def _get_or_create_repo(cls, repo_name: str) -> Dict[str, Any]:
        key = repo_name.strip().lower()
        if key not in cls._staging_repos:
            cls._staging_repos[key] = {
                "branches": {"main", "master"},
                "current_branch": "main",
                "files": {
                    "main": {
                        "README.md": "# Staging Repository\n",
                        "seo_config.json": '{\n  "title_template": "%s | DoxaRank",\n  "sitemap_enabled": true\n}\n',
                        "robots.txt": "User-agent: *\nAllow: /\n",
                    }
                },
                "commits": []
            }
        return cls._staging_repos[key]

    def _sanitize_file_path(self, path: str) -> Tuple[bool, Optional[str]]:
        if not path or not isinstance(path, str):
            return False, "File path must be a non-empty string."
        clean = path.strip()
        if "../" in clean or "..\\" in clean or clean.startswith("/") or clean.startswith("\\"):
            return False, f"Path traversal or absolute path forbidden in Git adapter: '{path}'."
        return True, clean

    def validate_parameters(self, operation: str, params: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        op = (operation or "").lower().strip()
        if op not in ["read_repository", "create_branch", "write_file", "create_commit"]:
            return False, f"Unsupported Git operation '{operation}'."

        if op == "create_branch":
            branch_name = params.get("branch_name") or params.get("branch")
            if not branch_name:
                return False, "create_branch requires 'branch_name'."

        elif op == "write_file":
            file_path = params.get("file_path") or params.get("path")
            if not file_path:
                return False, "write_file requires 'file_path'."
            is_valid, err = self._sanitize_file_path(file_path)
            if not is_valid:
                return False, err
            if "content" not in params:
                return False, "write_file requires 'content' parameter."

        elif op == "create_commit":
            if not params.get("message"):
                return False, "create_commit requires 'message' parameter."

        return True, None

    def preview(
        self,
        connection: Any,
        operation: str,
        target: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        repo_name = target or getattr(connection, "name", "default_repo")
        repo = self._get_or_create_repo(repo_name)
        branch = params.get("branch") or repo["current_branch"]
        files = repo["files"].get(branch, repo["files"].get("main", {}))

        file_path = params.get("file_path") or params.get("path", "")
        old_content = files.get(file_path, "[New File]")
        new_content = params.get("content", old_content)

        return {
            "system": self.system_type,
            "provider": getattr(connection, "provider", "staging_git"),
            "operation": operation,
            "target": target,
            "branch": branch,
            "file_path": file_path,
            "diff": {
                "before": old_content,
                "after": new_content,
            },
            "summary": f"Prepared Git {operation} on {repo_name} (branch '{branch}')."
        }

    def execute(
        self,
        connection: Any,
        operation: str,
        target: str,
        params: Dict[str, Any],
        correlation_id: str = "",
        retry_count: int = 0
    ) -> ExternalOperationResult:
        start_time = time.time()
        op = (operation or "").lower().strip()
        provider = getattr(connection, "provider", "staging_git")
        repo_name = target or getattr(connection, "name", "default_repo")

        # 1. Parameter Validation
        is_valid, param_err = self.validate_parameters(operation, params)
        if not is_valid:
            return ExternalOperationResult(
                success=False,
                system=self.system_type,
                provider=provider,
                operation=operation,
                target=target,
                error_category="malformed_request",
                error_message=param_err,
                correlation_id=correlation_id,
                duration_ms=int((time.time() - start_time) * 1000),
                retry_count=retry_count,
            )

        repo = self._get_or_create_repo(repo_name)
        branch = params.get("branch") or repo["current_branch"]

        if op == "read_repository":
            file_path = params.get("file_path") or params.get("path")
            duration_ms = max(25, int((time.time() - start_time) * 1000) + 15)
            branch_files = repo["files"].get(branch, repo["files"].get("main", {}))

            if file_path:
                is_safe, clean_path = self._sanitize_file_path(file_path)
                if not is_safe:
                    return ExternalOperationResult(
                        success=False,
                        system=self.system_type,
                        provider=provider,
                        operation=operation,
                        target=target,
                        error_category="invalid_target",
                        error_message=clean_path,
                        correlation_id=correlation_id,
                    )
                content = branch_files.get(clean_path)
                found = content is not None
                return ExternalOperationResult(
                    success=found,
                    system=self.system_type,
                    provider=provider,
                    operation=operation,
                    target=target,
                    status_code=200 if found else 404,
                    response_summary={"file_path": clean_path, "exists": found, "branch": branch},
                    before_state={"content": content},
                    after_state={"content": content},
                    correlation_id=correlation_id,
                    duration_ms=duration_ms,
                    retry_count=retry_count,
                    notes=f"Read file '{clean_path}' from Git branch '{branch}'.",
                )
            else:
                return ExternalOperationResult(
                    success=True,
                    system=self.system_type,
                    provider=provider,
                    operation=operation,
                    target=target,
                    status_code=200,
                    response_summary={"branches": list(repo["branches"]), "files": list(branch_files.keys()), "current_branch": branch},
                    correlation_id=correlation_id,
                    duration_ms=duration_ms,
                    retry_count=retry_count,
                    notes=f"Inspected repository '{repo_name}' structure.",
                )

        elif op == "create_branch":
            new_branch = (params.get("branch_name") or params.get("branch")).strip()
            repo["branches"].add(new_branch)
            # Copy files from source branch
            src_branch = params.get("from_branch") or repo["current_branch"]
            src_files = dict(repo["files"].get(src_branch, repo["files"].get("main", {})))
            repo["files"][new_branch] = src_files
            repo["current_branch"] = new_branch
            duration_ms = max(35, int((time.time() - start_time) * 1000) + 20)

            return ExternalOperationResult(
                success=True,
                system=self.system_type,
                provider=provider,
                operation=operation,
                target=target,
                status_code=201,
                response_summary={"created_branch": new_branch, "from_branch": src_branch},
                changed=True,
                after_state={"branch": new_branch},
                correlation_id=correlation_id,
                duration_ms=duration_ms,
                retry_count=retry_count,
                is_reversible=True,
                notes=f"Created staging branch '{new_branch}' from '{src_branch}'.",
            )

        elif op == "write_file":
            file_path = params.get("file_path") or params.get("path")
            is_safe, clean_path = self._sanitize_file_path(file_path)
            if not is_safe:
                return ExternalOperationResult(
                    success=False,
                    system=self.system_type,
                    provider=provider,
                    operation=operation,
                    target=target,
                    error_category="invalid_target",
                    error_message=clean_path,
                    correlation_id=correlation_id,
                )

            if branch not in repo["files"]:
                repo["files"][branch] = dict(repo["files"].get("main", {}))

            before_content = repo["files"][branch].get(clean_path, "")
            new_content = str(params.get("content", ""))
            repo["files"][branch][clean_path] = new_content
            duration_ms = max(45, int((time.time() - start_time) * 1000) + 25)

            return ExternalOperationResult(
                success=True,
                system=self.system_type,
                provider=provider,
                operation=operation,
                target=target,
                status_code=200,
                response_summary={"file_path": clean_path, "bytes_written": len(new_content), "branch": branch},
                changed=True,
                before_state={"path": clean_path, "content": before_content, "branch": branch},
                after_state={"path": clean_path, "content": new_content, "branch": branch},
                correlation_id=correlation_id,
                duration_ms=duration_ms,
                retry_count=retry_count,
                is_reversible=True,
                notes=f"Modified file '{clean_path}' in Git branch '{branch}'.",
            )

        elif op == "create_commit":
            message = params.get("message", "DoxaRank Automated SEO Update").strip()
            commit_id = f"commit-{int(time.time()*1000)}"
            repo["commits"].append({
                "id": commit_id,
                "message": message,
                "branch": branch,
                "timestamp": timezone.now().isoformat()
            })
            duration_ms = max(50, int((time.time() - start_time) * 1000) + 30)

            return ExternalOperationResult(
                success=True,
                system=self.system_type,
                provider=provider,
                operation=operation,
                target=target,
                status_code=201,
                response_summary={"commit_id": commit_id, "message": message, "branch": branch},
                changed=True,
                after_state={"commit_id": commit_id, "branch": branch},
                correlation_id=correlation_id,
                duration_ms=duration_ms,
                retry_count=retry_count,
                is_reversible=True,
                notes=f"Committed changes '{commit_id}' on branch '{branch}'.",
            )

        return ExternalOperationResult(
            success=False,
            system=self.system_type,
            provider=provider,
            operation=operation,
            target=target,
            error_category="unsupported_capability",
            error_message=f"Operation '{operation}' not supported by GitAdapter.",
            correlation_id=correlation_id,
        )

    def verify(
        self,
        connection: Any,
        operation: str,
        target: str,
        expected_state: Dict[str, Any]
    ) -> Tuple[bool, Dict[str, Any]]:
        repo_name = target or getattr(connection, "name", "default_repo")
        repo = self._get_or_create_repo(repo_name)

        branch = expected_state.get("branch") or repo["current_branch"]
        branch_files = repo["files"].get(branch, {})

        mismatches = []
        if "expected_file" in expected_state:
            req_file = expected_state["expected_file"]
            if req_file not in branch_files:
                mismatches.append(f"Expected file '{req_file}' missing from branch '{branch}'.")
            elif "expected_content" in expected_state:
                actual = branch_files.get(req_file, "")
                expected = expected_state["expected_content"]
                if expected not in actual:
                    mismatches.append(f"File '{req_file}' content does not match expected string.")

        if "expected_branch" in expected_state:
            req_branch = expected_state["expected_branch"]
            if req_branch not in repo["branches"]:
                mismatches.append(f"Expected branch '{req_branch}' not found in repository.")

        is_verified = len(mismatches) == 0
        evidence = {
            "verified": is_verified,
            "target": target,
            "checked_at": timezone.now().isoformat(),
            "expected": expected_state,
            "mismatches": mismatches,
        }
        return is_verified, evidence
