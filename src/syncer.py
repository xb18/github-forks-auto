"""Core logic for scanning and synchronizing all branches of forked repositories."""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from .client import GitHubClient
from .i18n import t

logger = logging.getLogger("syncer")


class BranchSyncStatus(Enum):
    UP_TO_DATE = "UP_TO_DATE"
    SYNCED = "SYNCED"
    CREATED = "CREATED"
    SKIPPED_DIVERGED = "SKIPPED_DIVERGED"
    SKIPPED_FORK_AHEAD = "SKIPPED_FORK_AHEAD"
    SKIPPED_UPSTREAM_MISSING = "SKIPPED_UPSTREAM_MISSING"
    ERROR = "ERROR"


@dataclass
class BranchResult:
    branch_name: str
    status: BranchSyncStatus
    message: str = ""
    fork_sha: Optional[str] = None
    upstream_sha: Optional[str] = None


@dataclass
class RepoSyncResult:
    repo_name: str
    upstream_name: Optional[str] = None
    is_fork: bool = True
    actions_disabled: bool = False
    actions_message: str = ""
    branch_results: List[BranchResult] = field(default_factory=list)
    error_message: Optional[str] = None


def get_repo_branches(client: GitHubClient, repo_full_name: str) -> Dict[str, str]:
    """
    Fetch all branches of a repository using lightweight Git matching-refs API.
    Reduces API calls from multiple paginated pages down to 1 single request.
    Returns: {branch_name: commit_sha}
    """
    resp = client.get(f"/repos/{repo_full_name}/git/matching-refs/heads")
    if resp.status_code == 200:
        refs_data = resp.json()
        if isinstance(refs_data, list) and refs_data:
            branch_map: Dict[str, str] = {}
            for r in refs_data:
                ref_name = r.get("ref", "")
                if ref_name.startswith("refs/heads/"):
                    b_name = ref_name[len("refs/heads/"):]
                    sha = r.get("object", {}).get("sha")
                    if b_name and sha:
                        branch_map[b_name] = sha
            if branch_map:
                return branch_map

    # Fallback to paginated branches API if matching-refs is empty or unsupported
    branches_data = client.get_paginated(f"/repos/{repo_full_name}/branches")
    branch_map: Dict[str, str] = {}
    for b in branches_data:
        name = b.get("name")
        sha = b.get("commit", {}).get("sha")
        if name and sha:
            branch_map[name] = sha
    return branch_map


def sync_single_branch(
    client: GitHubClient,
    fork_full_name: str,
    upstream_full_name: str,
    branch_name: str,
    fork_sha: Optional[str],
    upstream_sha: str,
) -> BranchResult:
    """
    Sync a single branch from upstream to fork with strict safety checks.
    """
    # Case 1: Branch does not exist in Fork -> Create it
    if not fork_sha:
        logger.info(f"[{fork_full_name}] Branch '{branch_name}' not found in fork. Creating from upstream...")
        create_resp = client.post(
            f"/repos/{fork_full_name}/git/refs",
            json_data={
                "ref": f"refs/heads/{branch_name}",
                "sha": upstream_sha,
            },
        )
        if create_resp.status_code in (200, 201):
            logger.info(f"[{fork_full_name}] Successfully created branch '{branch_name}'.")
            return BranchResult(
                branch_name=branch_name,
                status=BranchSyncStatus.CREATED,
                message=t("branch_created"),
                fork_sha=None,
                upstream_sha=upstream_sha,
            )
        else:
            err = t("branch_create_failed", status=create_resp.status_code, detail=create_resp.text)
            logger.warning(f"[{fork_full_name}] {err}")
            return BranchResult(
                branch_name=branch_name,
                status=BranchSyncStatus.ERROR,
                message=err,
                upstream_sha=upstream_sha,
            )

    # Case 2: Both exist and have identical commit SHA
    if fork_sha == upstream_sha:
        logger.debug(f"[{fork_full_name}:{branch_name}] Already identical ({fork_sha[:7]}).")
        return BranchResult(
            branch_name=branch_name,
            status=BranchSyncStatus.UP_TO_DATE,
            message=t("branch_up_to_date"),
            fork_sha=fork_sha,
            upstream_sha=upstream_sha,
        )

    # Case 3: Both exist but have different commit SHAs -> Compare ancestry for safe Fast-Forward
    compare_resp = client.get(f"/repos/{fork_full_name}/compare/{fork_sha}...{upstream_sha}")
    if compare_resp.status_code != 200:
        err = t("branch_compare_failed", status=compare_resp.status_code, detail=compare_resp.text)
        logger.warning(f"[{fork_full_name}:{branch_name}] {err}")
        return BranchResult(
            branch_name=branch_name,
            status=BranchSyncStatus.ERROR,
            message=err,
            fork_sha=fork_sha,
            upstream_sha=upstream_sha,
        )

    compare_data = compare_resp.json()
    compare_status = compare_data.get("status")  # ahead, behind, diverged, identical
    ahead_by = compare_data.get("ahead_by", 0)
    behind_by = compare_data.get("behind_by", 0)

    # If upstream is ahead and behind_by == 0 (fork SHA is an ancestor of upstream SHA)
    # -> Safe Fast-Forward
    if compare_status == "ahead" and behind_by == 0:
        logger.info(
            f"[{fork_full_name}:{branch_name}] Fast-Forward possible (ahead by {ahead_by}). Updating ref..."
        )
        patch_resp = client.patch(
            f"/repos/{fork_full_name}/git/refs/heads/{branch_name}",
            json_data={
                "sha": upstream_sha,
                "force": False,  # Strict: Never force push!
            },
        )
        if patch_resp.status_code == 200:
            logger.info(f"[{fork_full_name}:{branch_name}] Successfully fast-forwarded to {upstream_sha[:7]}.")
            return BranchResult(
                branch_name=branch_name,
                status=BranchSyncStatus.SYNCED,
                message=t("branch_fast_forward", count=ahead_by),
                fork_sha=fork_sha,
                upstream_sha=upstream_sha,
            )
        else:
            err = t("branch_update_failed", status=patch_resp.status_code, detail=patch_resp.text)
            logger.warning(f"[{fork_full_name}:{branch_name}] {err}")
            return BranchResult(
                branch_name=branch_name,
                status=BranchSyncStatus.ERROR,
                message=err,
                fork_sha=fork_sha,
                upstream_sha=upstream_sha,
            )

    # If status is diverged -> Upstream history rewritten or user has custom commits
    elif compare_status == "diverged":
        warn_msg = t("branch_diverged", behind_by=behind_by, ahead_by=ahead_by)
        logger.warning(f"[{fork_full_name}:{branch_name}] 🛡️ {warn_msg}")
        return BranchResult(
            branch_name=branch_name,
            status=BranchSyncStatus.SKIPPED_DIVERGED,
            message=warn_msg,
            fork_sha=fork_sha,
            upstream_sha=upstream_sha,
        )

    # If fork is ahead of upstream
    elif compare_status == "behind":
        msg = t("branch_fork_ahead", behind_by=behind_by)
        logger.info(f"[{fork_full_name}:{branch_name}] {msg}")
        return BranchResult(
            branch_name=branch_name,
            status=BranchSyncStatus.SKIPPED_FORK_AHEAD,
            message=msg,
            fork_sha=fork_sha,
            upstream_sha=upstream_sha,
        )

    else:
        warn_msg = t("branch_unusual_status", compare_status=compare_status, ahead_by=ahead_by, behind_by=behind_by)
        logger.warning(f"[{fork_full_name}:{branch_name}] {warn_msg}")
        return BranchResult(
            branch_name=branch_name,
            status=BranchSyncStatus.SKIPPED_DIVERGED,
            message=warn_msg,
            fork_sha=fork_sha,
            upstream_sha=upstream_sha,
        )


def sync_repository_branches(
    client: GitHubClient,
    repo_data: Dict[str, Any],
    debug_mode: bool = False,
) -> RepoSyncResult:
    """
    Sync all branches of a single forked repository.
    """
    fork_full_name = repo_data.get("full_name", "")
    result = RepoSyncResult(repo_name=fork_full_name)

    # Verify if it's a fork
    if not repo_data.get("fork", False):
        result.is_fork = False
        result.error_message = t("branch_not_a_fork")
        return result

    # Check upstream parent information
    parent = repo_data.get("parent")
    if not parent:
        # If parent details are not in the list response, fetch repo details
        detail_resp = client.get(f"/repos/{fork_full_name}")
        if detail_resp.status_code == 200:
            repo_detail = detail_resp.json()
            parent = repo_detail.get("parent")

    if not parent:
        result.error_message = t("branch_parent_not_found")
        logger.warning(f"[{fork_full_name}] {result.error_message}")
        return result

    upstream_full_name = parent.get("full_name")
    result.upstream_name = upstream_full_name

    if debug_mode:
        logger.info(f"==> Processing fork: {fork_full_name} (Upstream: {upstream_full_name})")

    # Fetch branches from both repositories
    try:
        upstream_branches = get_repo_branches(client, upstream_full_name)
    except Exception as exc:
        result.error_message = t("branch_fetch_failed", detail=f"{upstream_full_name}: {exc}")
        logger.error(f"[{fork_full_name}] {result.error_message}")
        return result

    if not upstream_branches:
        result.error_message = t("branch_upstream_empty", upstream=upstream_full_name)
        logger.warning(f"[{fork_full_name}] {result.error_message}")
        return result

    try:
        fork_branches = get_repo_branches(client, fork_full_name)
    except Exception as exc:
        result.error_message = t("branch_fetch_failed", detail=f"{fork_full_name}: {exc}")
        logger.error(f"[{fork_full_name}] {result.error_message}")
        return result

    # Iterate through all upstream branches and sync
    branch_items = list(upstream_branches.items())
    total_b = len(branch_items)
    for b_idx, (branch_name, upstream_sha) in enumerate(branch_items, start=1):
        fork_sha = fork_branches.get(branch_name)
        if debug_mode:
            logger.info(f"  🌿 [分支 {b_idx}/{total_b}] 处理分支 '{branch_name}'...")
        else:
            logger.info(t("log_comparing_branch"))
        b_res = sync_single_branch(
            client=client,
            fork_full_name=fork_full_name,
            upstream_full_name=upstream_full_name,
            branch_name=branch_name,
            fork_sha=fork_sha,
            upstream_sha=upstream_sha,
        )
        result.branch_results.append(b_res)

    return result
