"""Module to manage and disable GitHub Actions for forked repositories."""

import logging
from typing import Dict, Any, Tuple
from .client import GitHubClient

logger = logging.getLogger("action_disabler")


def disable_repo_actions(client: GitHubClient, repo_full_name: str) -> Tuple[bool, str]:
    """
    Disable GitHub Actions at the repository level.
    Endpoint: PUT /repos/{owner}/{repo}/actions/permissions
    Body: {"enabled": false}

    Returns:
        (success: bool, message: str)
    """
    try:
        # Check current actions permissions first to avoid redundant updates
        get_resp = client.get(f"/repos/{repo_full_name}/actions/permissions")
        if get_resp.status_code == 200:
            current_perms = get_resp.json()
            if current_perms.get("enabled") is False:
                logger.info(f"[{repo_full_name}] GitHub Actions already disabled.")
                return True, "Already disabled"

        # Set enabled = False
        put_resp = client.put(
            f"/repos/{repo_full_name}/actions/permissions",
            json_data={"enabled": False},
        )

        if put_resp.status_code in (200, 204):
            logger.info(f"[{repo_full_name}] Successfully disabled GitHub Actions.")
            return True, "Disabled successfully"
        elif put_resp.status_code == 403:
            msg = f"Permission denied (403). Ensure PAT has 'Administration: Write' or 'repo' scope."
            logger.warning(f"[{repo_full_name}] {msg}")
            return False, msg
        elif put_resp.status_code == 404:
            msg = "Actions permissions endpoint not found (404) or repo inaccessible."
            logger.warning(f"[{repo_full_name}] {msg}")
            return False, msg
        else:
            msg = f"Failed ({put_resp.status_code}): {put_resp.text}"
            logger.warning(f"[{repo_full_name}] {msg}")
            return False, msg

    except Exception as exc:
        msg = f"Exception while disabling actions: {str(exc)}"
        logger.error(f"[{repo_full_name}] {msg}")
        return False, msg
