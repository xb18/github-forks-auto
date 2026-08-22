"""GitHub REST API Client wrapper with authentication, pagination, and retry support."""

import logging
import time
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger("github_client")


class GitHubClient:
    """Wrapper around GitHub REST API."""

    def __init__(self, token: str, base_url: str = "https://api.github.com"):
        self.token = token.strip()
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "GitHub-Forks-Auto-Sync",
        })

    def request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        max_retries: int = 5,
    ) -> requests.Response:
        """Perform an HTTP request with rate-limit detection and exponential retry logic."""
        url = path if path.startswith("http") else f"{self.base_url}/{path.lstrip('/')}"
        
        # Add gentle rate limiting on write operations to avoid secondary abuse limits
        if method.upper() in ("POST", "PATCH", "PUT", "DELETE"):
            time.sleep(0.2)

        for attempt in range(1, max_retries + 1):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                    timeout=30,
                )

                # 1. Detect 403/429 Rate Limit Exceeded
                is_rate_limited = (
                    response.status_code == 429
                    or (
                        response.status_code == 403
                        and (
                            "rate limit" in response.text.lower()
                            or response.headers.get("x-ratelimit-remaining") == "0"
                        )
                    )
                )

                if is_rate_limited:
                    reset_time = int(response.headers.get("x-ratelimit-reset", 0))
                    retry_after = response.headers.get("Retry-After")
                    if retry_after:
                        wait_seconds = int(retry_after)
                    elif reset_time > 0:
                        wait_seconds = max(reset_time - int(time.time()) + 1, 5)
                    else:
                        wait_seconds = 60

                    if attempt < max_retries:
                        logger.warning(
                            f"GitHub API Rate Limit exceeded ({response.status_code}). "
                            f"Waiting {wait_seconds}s until reset (attempt {attempt}/{max_retries})..."
                        )
                        time.sleep(wait_seconds)
                        continue
                    else:
                        logger.error(f"GitHub API Rate Limit still exceeded after {max_retries} retries.")
                        return response

                # 2. Pre-emptive check if rate limit is nearly exhausted
                remaining = response.headers.get("x-ratelimit-remaining")
                if remaining is not None and int(remaining) < 5:
                    reset_time = int(response.headers.get("x-ratelimit-reset", 0))
                    wait_seconds = max(reset_time - int(time.time()), 5)
                    logger.warning(
                        f"GitHub API rate limit nearly exhausted (remaining: {remaining}). "
                        f"Waiting {wait_seconds}s until reset."
                    )
                    time.sleep(min(wait_seconds, 60))

                if response.status_code >= 500 and attempt < max_retries:
                    logger.warning(
                        f"Server error ({response.status_code}) from {url}, "
                        f"attempt {attempt}/{max_retries}. Retrying in {2 ** attempt}s..."
                    )
                    time.sleep(2 ** attempt)
                    continue

                return response
            except requests.RequestException as exc:
                if attempt == max_retries:
                    raise
                logger.warning(
                    f"Request exception {exc} for {url}, attempt {attempt}/{max_retries}. Retrying..."
                )
                time.sleep(2 ** attempt)

        raise RuntimeError(f"Failed to execute request {method} {url} after {max_retries} retries.")

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> requests.Response:
        return self.request("GET", path, params=params)

    def post(self, path: str, json_data: Optional[Dict[str, Any]] = None) -> requests.Response:
        return self.request("POST", path, json_data=json_data)

    def patch(self, path: str, json_data: Optional[Dict[str, Any]] = None) -> requests.Response:
        return self.request("PATCH", path, json_data=json_data)

    def put(self, path: str, json_data: Optional[Dict[str, Any]] = None) -> requests.Response:
        return self.request("PUT", path, json_data=json_data)

    def get_paginated(
        self, path: str, params: Optional[Dict[str, Any]] = None, per_page: int = 100
    ) -> List[Dict[str, Any]]:
        """Fetch all pages for a paginated API endpoint."""
        items: List[Dict[str, Any]] = []
        page = 1
        req_params = dict(params or {})
        req_params["per_page"] = per_page

        while True:
            req_params["page"] = page
            resp = self.get(path, params=req_params)
            if resp.status_code != 200:
                logger.error(f"Failed to fetch paginated data from {path}: {resp.status_code} {resp.text}")
                break

            data = resp.json()
            if not isinstance(data, list):
                logger.warning(f"Unexpected non-list response for paginated endpoint {path}")
                break

            if not data:
                break

            items.extend(data)
            if len(data) < per_page:
                break
            page += 1

        return items

    def get_authenticated_user(self) -> Dict[str, Any]:
        """Fetch current authenticated user profile and check token status."""
        resp = self.get("/user")
        if resp.status_code == 401:
            raise PermissionError("GitHub PAT Token 已失效或已过期 (401 Bad credentials)。请重新生成 Token 并更新 Secret。")
        if resp.status_code != 200:
            raise RuntimeError(f"Authentication failed ({resp.status_code}): {resp.text}")

        self.token_expiration = resp.headers.get("github-authentication-token-expiration")
        return resp.json()
