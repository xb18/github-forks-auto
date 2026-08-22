"""Main entry point for GitHub Forks Auto Sync tool."""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Set

from .action_disabler import disable_repo_actions
from .client import GitHubClient
from .feishu import send_feishu_card, send_feishu_alert
from .syncer import BranchSyncStatus, RepoSyncResult, sync_repository_branches

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


class PrivacyLogFilter(logging.Filter):
    """Filter that masks sensitive repository and user names from stdout logs in non-debug mode."""

    def __init__(self):
        super().__init__()
        self.masked_terms: Set[str] = set()

    def add_term(self, term: str):
        if term and len(term) >= 2:
            self.masked_terms.add(term)

    def filter(self, record: logging.LogRecord) -> bool:
        if self.masked_terms and isinstance(record.msg, str):
            msg = record.msg
            for term in sorted(self.masked_terms, key=len, reverse=True):
                if term in msg:
                    msg = msg.replace(term, "***")
            record.msg = msg
        return True


import re

def parse_repo_list(val: Any) -> List[str]:
    """Parse comma/semicolon/newline separated string or list of repository names."""
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str):
        return [x.strip() for x in re.split(r'[,;\n\r]+', val) if x.strip()]
    return []


def load_config() -> Dict[str, Any]:
    """Load configuration from config.json if present, then override with environment variables."""
    config: Dict[str, Any] = {
        "gh_pat": os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN", ""),
        "feishu_webhook_url": os.environ.get("FEISHU_WEBHOOK_URL", ""),
        "feishu_secret": os.environ.get("FEISHU_SECRET", ""),
        "exclude_repos": [],
        "include_only": [],
        "disable_actions": os.environ.get("DISABLE_ACTIONS", "true").lower() in ("true", "1", "yes"),
        "dry_run": os.environ.get("DRY_RUN", "false").lower() in ("true", "1", "yes"),
        "debug_mode": os.environ.get("DEBUG_MODE", "false").lower() in ("true", "1", "yes"),
    }

    # Check local config file
    config_file = os.environ.get("CONFIG_FILE", "config.json")
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                file_cfg = json.load(f)
                config.update(file_cfg)
        except Exception as exc:
            logger.warning(f"Failed to read {config_file}: {exc}")

    # Environment variables override
    env_exclude = os.environ.get("EXCLUDE_REPOS")
    if env_exclude:
        config["exclude_repos"] = parse_repo_list(env_exclude)
    elif config.get("exclude_repos"):
        config["exclude_repos"] = parse_repo_list(config["exclude_repos"])

    env_include = os.environ.get("INCLUDE_ONLY")
    if env_include:
        config["include_only"] = parse_repo_list(env_include)
    elif config.get("include_only"):
        config["include_only"] = parse_repo_list(config["include_only"])

    return config


def generate_step_summary(
    results: List[RepoSyncResult],
    stats: Dict[str, int],
    start_time: datetime,
    end_time: datetime,
    debug_mode: bool = False,
) -> str:
    """Generate GitHub Step Summary Markdown string."""
    duration = (end_time - start_time).total_seconds()
    time_str = start_time.strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "## 🔄 GitHub Fork 仓库全量同步与管理报告",
        f"**执行时间**: `{time_str}` | **总耗时**: `{duration:.1f}s`",
        "",
        "### 📊 同步概况统计",
        "| 指标 | 数量 |",
        "| :--- | :--- |",
        f"| 📦 扫描 Fork 仓库总数 | **{stats.get('total_repos', 0)}** |",
        f"| ⚡ 分支同步成功 (Fast-Forward) | **{stats.get('synced_branches', 0)}** |",
        f"| 🌱 上游新增分支创建 | **{stats.get('created_branches', 0)}** |",
        f"| ✅ 已是最新状态分支 | **{stats.get('uptodate_branches', 0)}** |",
        f"| 🛡️ 安全跳过 (分叉/硬回退保护) | **{stats.get('skipped_branches', 0)}** |",
        f"| 🚫 Actions 已禁用仓库 | **{stats.get('actions_disabled_repos', 0)}** |",
        f"| ❌ 异常/失败 | **{stats.get('failed', 0)}** |",
        "",
    ]

    if not debug_mode:
        lines.append("> 🔒 **隐私保护模式已生效**：当前为非 Debug 模式，已隐藏所有具体仓库名称与分支明细，确保公有仓库运行安全。完整变更明细已私密推送至飞书。如需在 GitHub 页面公开显示详细表格，可设置 Secret `DEBUG_MODE=true`。")
        lines.append("")
        return "\n".join(lines)

    lines.extend([
        "### 📝 仓库处理明细 (Debug Mode)",
        "| 仓库名称 | 上游仓库 | 分支 | 状态 | 详细信息 |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ])

    for r in results:
        upstream_display = r.upstream_name or "N/A"
        if r.error_message:
            lines.append(f"| `{r.repo_name}` | `{upstream_display}` | `-` | ❌ 错误 | {r.error_message} |")
            continue

        if not r.branch_results:
            lines.append(f"| `{r.repo_name}` | `{upstream_display}` | `-` | ⚠️ 无分支 | 未检测到可同步分支 |")
            continue

        for b in r.branch_results:
            status_icon = {
                BranchSyncStatus.SYNCED: "⚡ 已同步",
                BranchSyncStatus.CREATED: "🌱 新建分支",
                BranchSyncStatus.UP_TO_DATE: "✅ 已最新",
                BranchSyncStatus.SKIPPED_DIVERGED: "🛡️ 分叉跳过",
                BranchSyncStatus.SKIPPED_FORK_AHEAD: "🛡️ 本地领先",
                BranchSyncStatus.ERROR: "❌ 失败",
            }.get(b.status, str(b.status.value))

            msg_clean = b.message.replace("|", "/")
            lines.append(f"| `{r.repo_name}` | `{upstream_display}` | `{b.branch_name}` | {status_icon} | {msg_clean} |")

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    start_time = datetime.now(timezone.utc)
    config = load_config()
    debug_mode = config.get("debug_mode", False)

    privacy_filter = None
    if not debug_mode:
        privacy_filter = PrivacyLogFilter()
        for handler in logging.root.handlers:
            handler.addFilter(privacy_filter)

    feishu_webhook = config.get("feishu_webhook_url")
    feishu_secret = config.get("feishu_secret")

    token = config.get("gh_pat", "")
    if not token:
        err_msg = "❌ **错误**: GitHub PAT 密钥 (`GH_PAT`) 未配置，导致同步任务无法执行！"
        logger.error(err_msg)
        if feishu_webhook:
            send_feishu_alert(
                webhook_url=feishu_webhook,
                secret=feishu_secret,
                title="🚨 GitHub Fork 同步失败：未配置 GH_PAT",
                message=err_msg,
            )
        return 1

    client = GitHubClient(token=token)

    try:
        user_info = client.get_authenticated_user()
        username = user_info.get("login", "Unknown")
        if privacy_filter:
            privacy_filter.add_term(username)
        logger.info(f"Authenticated as GitHub user: @{username}")
    except Exception as exc:
        err_msg = f"❌ **GitHub 身份鉴权失败**: {str(exc)}\n\n⚠️ **原因**: 您的 Personal Access Token (`GH_PAT`) 可能已**过期或被撤销**，导致无法访问 GitHub API。\n\n👉 请尽快重新生成 Token 并更新仓库 Secret。"
        logger.error(f"GitHub authentication error: {exc}")
        if feishu_webhook:
            send_feishu_alert(
                webhook_url=feishu_webhook,
                secret=feishu_secret,
                title="🚨 GitHub Fork 同步失败：Token 已过期或失效",
                message=err_msg,
            )
        return 1

    logger.info("Fetching all repositories owned by user...")
    repos = client.get_paginated("/user/repos", params={"type": "owner", "sort": "full_name"})
    
    if privacy_filter:
        for r in repos:
            if r.get("name"):
                privacy_filter.add_term(r.get("name"))
            if r.get("full_name"):
                privacy_filter.add_term(r.get("full_name"))

    fork_repos = [r for r in repos if r.get("fork") is True]

    logger.info(f"Found {len(repos)} total owned repos, {len(fork_repos)} are forked repositories.")

    exclude_set: Set[str] = {r.lower() for r in config.get("exclude_repos", [])}
    include_set: Set[str] = {r.lower() for r in config.get("include_only", [])}

    filtered_forks: List[Dict[str, Any]] = []
    for r in fork_repos:
        name = r.get("name", "")
        full_name = r.get("full_name", "")
        name_lower = name.lower()
        full_name_lower = full_name.lower()

        if include_set and (name_lower not in include_set and full_name_lower not in include_set):
            logger.info(f"Skipping {full_name} (not in include_only list)")
            continue
        if name_lower in exclude_set or full_name_lower in exclude_set:
            logger.info(f"Skipping {full_name} (matches exclude_repos)")
            continue
        filtered_forks.append(r)

    logger.info(f"Total forked repos to process: {len(filtered_forks)}")

    results: List[RepoSyncResult] = []
    warnings_list: List[str] = []
    errors_list: List[str] = []

    stats = {
        "total_repos": len(filtered_forks),
        "synced_branches": 0,
        "created_branches": 0,
        "uptodate_branches": 0,
        "skipped_branches": 0,
        "actions_disabled_repos": 0,
        "failed": 0,
    }

    for idx, repo_data in enumerate(filtered_forks, start=1):
        repo_full_name = repo_data.get("full_name", "")
        logger.info(f"\n[{idx}/{len(filtered_forks)}] Processing repository: {repo_full_name}")

        if privacy_filter and repo_data.get("parent"):
            privacy_filter.add_term(repo_data["parent"].get("full_name", ""))
            privacy_filter.add_term(repo_data["parent"].get("name", ""))

        # 1. Disable GitHub Actions if enabled in config
        if config.get("disable_actions", True):
            ok, msg = disable_repo_actions(client, repo_full_name)
            if ok:
                stats["actions_disabled_repos"] += 1
            else:
                warnings_list.append(f"`{repo_full_name}`: Actions 禁用未成功 ({msg})")

        # 2. Sync all branches
        try:
            repo_res = sync_repository_branches(client, repo_data)
            results.append(repo_res)

            if repo_res.error_message:
                stats["failed"] += 1
                errors_list.append(f"`{repo_full_name}`: {repo_res.error_message}")
                continue

            for b in repo_res.branch_results:
                if b.status == BranchSyncStatus.SYNCED:
                    stats["synced_branches"] += 1
                elif b.status == BranchSyncStatus.CREATED:
                    stats["created_branches"] += 1
                elif b.status == BranchSyncStatus.UP_TO_DATE:
                    stats["uptodate_branches"] += 1
                elif b.status in (BranchSyncStatus.SKIPPED_DIVERGED, BranchSyncStatus.SKIPPED_FORK_AHEAD):
                    stats["skipped_branches"] += 1
                    warnings_list.append(f"`{repo_full_name}` [{b.branch_name}]: {b.message}")
                elif b.status == BranchSyncStatus.ERROR:
                    stats["failed"] += 1
                    errors_list.append(f"`{repo_full_name}` [{b.branch_name}]: {b.message}")

        except Exception as exc:
            logger.error(f"Unexpected error processing {repo_full_name}: {exc}")
            stats["failed"] += 1
            err_msg = f"Unexpected exception: {str(exc)}"
            results.append(RepoSyncResult(repo_name=repo_full_name, error_message=err_msg))
            errors_list.append(f"`{repo_full_name}`: {err_msg}")

    end_time = datetime.now(timezone.utc)

    if getattr(client, "token_expiration", None):
        warnings_list.append(f"🔑 Token 有效期: 预计于 `{client.token_expiration}` 到期")

    # Output GitHub Step Summary
    debug_mode = config.get("debug_mode", False)
    summary_md = generate_step_summary(results, stats, start_time, end_time, debug_mode=debug_mode)
    print("\n" + "=" * 50)
    print(summary_md)
    print("=" * 50 + "\n")

    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        try:
            with open(summary_file, "a", encoding="utf-8") as f:
                f.write(summary_md + "\n")
            logger.info("Successfully wrote GitHub Step Summary.")
        except Exception as exc:
            logger.warning(f"Could not write to GITHUB_STEP_SUMMARY: {exc}")

    # Send Feishu Notification
    feishu_webhook = config.get("feishu_webhook_url")
    feishu_secret = config.get("feishu_secret")
    if feishu_webhook:
        logger.info("Sending Feishu notification card...")
        send_feishu_card(
            webhook_url=feishu_webhook,
            secret=feishu_secret,
            title="🔄 GitHub Fork 仓库同步完成",
            stats=stats,
            warnings=warnings_list,
            errors=errors_list,
            execution_time_str=start_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
        )

    logger.info("Forks synchronization and management job finished.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
