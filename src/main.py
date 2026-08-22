"""Main entry point for GitHub Forks Auto Sync tool."""

import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Set

from .action_disabler import disable_repo_actions
from .client import GitHubClient
from .email_notifier import send_email_alert, send_email_notification
from .feishu import send_feishu_alert, send_feishu_card
from .i18n import get_current_language, set_language, t
from .syncer import BranchSyncStatus, RepoSyncResult, sync_repository_branches

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


class StandardLogFilter(logging.Filter):
    """Filter that sanitizes verbose names in standard non-debug logging mode."""

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


def parse_repo_list(val: Any) -> List[str]:
    """Parse comma/semicolon/space/newline separated string or list of repository names."""
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str):
        return [x.strip() for x in re.split(r'[,;\s]+', val) if x.strip()]
    return []


def load_config() -> Dict[str, Any]:
    """Load configuration from config.json if present, then override with environment variables."""
    config: Dict[str, Any] = {
        "gh_pat": os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN", ""),
        "feishu_webhook_url": os.environ.get("FEISHU_WEBHOOK_URL", ""),
        "feishu_secret": os.environ.get("FEISHU_SECRET", ""),
        "smtp_host": os.environ.get("SMTP_HOST") or os.environ.get("SMTP_SERVER", ""),
        "smtp_port": os.environ.get("SMTP_PORT", ""),
        "smtp_user": os.environ.get("SMTP_USER") or os.environ.get("SMTP_USERNAME", ""),
        "smtp_pass": os.environ.get("SMTP_PASS") or os.environ.get("SMTP_PASSWORD") or os.environ.get("SMTP_AUTH_CODE", ""),
        "smtp_to": os.environ.get("SMTP_TO") or os.environ.get("EMAIL_TO", ""),
        "smtp_from_name": os.environ.get("SMTP_FROM_NAME", "GitHub Forks Auto"),
        "smtp_ssl": None,
        "smtp_tls": None,
        "language": os.environ.get("LANGUAGE") or os.environ.get("LANG") or os.environ.get("LOCALE") or "zh",
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
    if os.environ.get("LANGUAGE"):
        config["language"] = os.environ.get("LANGUAGE")
    elif os.environ.get("LOCALE"):
        config["language"] = os.environ.get("LOCALE")

    set_language(config.get("language", "zh"))

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
    lang: str = "zh",
) -> str:
    """Generate GitHub Step Summary Markdown string."""
    duration = (end_time - start_time).total_seconds()
    time_str = start_time.strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        t("summary_workflow_title", lang=lang),
        t("summary_time_header", lang=lang, time_str=time_str, duration=duration),
        "",
        t("summary_stats_header", lang=lang),
        f"| {t('summary_metric_col', lang=lang)} | {t('summary_count_col', lang=lang)} |",
        "| :--- | :--- |",
        f"| {t('summary_total_repos', lang=lang)} | **{stats.get('total_repos', 0)}** |",
        f"| {t('summary_synced_branches', lang=lang)} | **{stats.get('synced_branches', 0)}** |",
        f"| {t('summary_created_branches', lang=lang)} | **{stats.get('created_branches', 0)}** |",
        f"| {t('summary_uptodate_branches', lang=lang)} | **{stats.get('uptodate_branches', 0)}** |",
        f"| {t('summary_skipped_branches', lang=lang)} | **{stats.get('skipped_branches', 0)}** |",
        f"| {t('summary_disabled_actions', lang=lang)} | **{stats.get('actions_disabled_repos', 0)}** |",
        f"| {t('summary_failed', lang=lang)} | **{stats.get('failed', 0)}** |",
        "",
    ]

    if not debug_mode:
        lines.append(t("summary_standard_mode_note", lang=lang))
        lines.append("")
        return "\n".join(lines)

    lines.extend([
        t("summary_debug_table_header", lang=lang),
        f"| {t('summary_table_repo', lang=lang)} | {t('summary_table_upstream', lang=lang)} | {t('summary_table_branch', lang=lang)} | {t('summary_table_status', lang=lang)} | {t('summary_table_details', lang=lang)} |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ])

    for r in results:
        upstream_display = r.upstream_name or "N/A"
        if r.error_message:
            lines.append(f"| `{r.repo_name}` | `{upstream_display}` | `-` | {t('status_label_error', lang=lang)} | {r.error_message} |")
            continue

        if not r.branch_results:
            lines.append(f"| `{r.repo_name}` | `{upstream_display}` | `-` | {t('status_label_no_branches', lang=lang)} | {t('branch_no_branches_detected', lang=lang)} |")
            continue

        for b in r.branch_results:
            status_icon = {
                BranchSyncStatus.SYNCED: t("status_label_synced", lang=lang),
                BranchSyncStatus.CREATED: t("status_label_created", lang=lang),
                BranchSyncStatus.UP_TO_DATE: t("status_label_uptodate", lang=lang),
                BranchSyncStatus.SKIPPED_DIVERGED: t("status_label_skipped_diverged", lang=lang),
                BranchSyncStatus.SKIPPED_FORK_AHEAD: t("status_label_skipped_ahead", lang=lang),
                BranchSyncStatus.ERROR: t("status_label_error", lang=lang),
            }.get(b.status, str(b.status.value))

            msg_clean = b.message.replace("|", "/")
            lines.append(f"| `{r.repo_name}` | `{upstream_display}` | `{b.branch_name}` | {status_icon} | {msg_clean} |")

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    start_time = datetime.now(timezone.utc)
    config = load_config()
    current_lang = get_current_language()
    debug_mode = config.get("debug_mode", False)

    log_filter = None
    if not debug_mode:
        log_filter = StandardLogFilter()
        for handler in logging.root.handlers:
            handler.addFilter(log_filter)

    feishu_webhook = config.get("feishu_webhook_url")
    feishu_secret = config.get("feishu_secret")

    token = config.get("gh_pat", "")
    if not token:
        err_msg = t("log_missing_pat", lang=current_lang)
        logger.error(err_msg)
        if feishu_webhook:
            send_feishu_alert(
                webhook_url=feishu_webhook,
                secret=feishu_secret,
                title=t("feishu_alert_title_missing_pat", lang=current_lang),
                message=err_msg,
                lang=current_lang,
            )
        send_email_alert(
            smtp_config=config,
            title=t("email_alert_subject_missing_pat", lang=current_lang),
            message=err_msg,
            lang=current_lang,
        )
        return 1

    client = GitHubClient(token=token)

    try:
        user_info = client.get_authenticated_user()
        username = user_info.get("login", "Unknown")
        if log_filter:
            log_filter.add_term(username)
        logger.info(t("log_authenticated", lang=current_lang, username=username))
    except Exception as exc:
        err_msg = t("log_auth_failed", lang=current_lang, exc=str(exc))
        logger.error(f"GitHub authentication error: {exc}")
        if feishu_webhook:
            send_feishu_alert(
                webhook_url=feishu_webhook,
                secret=feishu_secret,
                title=t("feishu_alert_title_auth", lang=current_lang),
                message=err_msg,
                lang=current_lang,
            )
        send_email_alert(
            smtp_config=config,
            title=t("email_alert_subject_auth", lang=current_lang),
            message=err_msg,
            lang=current_lang,
        )
        return 1

    logger.info(t("log_fetching_repos", lang=current_lang))
    repos = client.get_paginated("/user/repos", params={"type": "owner", "sort": "full_name"})
    
    if log_filter:
        for r in repos:
            if r.get("name"):
                log_filter.add_term(r.get("name"))
            if r.get("full_name"):
                log_filter.add_term(r.get("full_name"))

    fork_repos = [r for r in repos if r.get("fork") is True]

    exclude_set: Set[str] = {r.lower() for r in config.get("exclude_repos", [])}
    include_set: Set[str] = {r.lower() for r in config.get("include_only", [])}

    filtered_forks: List[Dict[str, Any]] = []
    for r in fork_repos:
        name = r.get("name", "")
        full_name = r.get("full_name", "")
        name_lower = name.lower()
        full_name_lower = full_name.lower()

        if include_set and (name_lower not in include_set and full_name_lower not in include_set):
            if debug_mode:
                logger.info(f"Skipping {full_name} (not in include_only list)")
            continue
        if name_lower in exclude_set or full_name_lower in exclude_set:
            if debug_mode:
                logger.info(f"Skipping {full_name} (matches exclude_repos)")
            continue
        filtered_forks.append(r)

    if debug_mode:
        logger.info(f"Found {len(repos)} total owned repos, {len(fork_repos)} are forked repositories.")
        logger.info(f"Total forked repos to process: {len(filtered_forks)}")
    else:
        logger.info(t("log_forks_fetched_std", lang=current_lang))

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

    total_repos_count = len(filtered_forks)
    max_runtime_minutes = int(os.environ.get("MAX_RUNTIME_MINUTES", "320"))

    for idx, repo_data in enumerate(filtered_forks, start=1):
        # Check runtime before processing next repo
        elapsed_min = (datetime.now(timezone.utc) - start_time).total_seconds() / 60
        if elapsed_min >= max_runtime_minutes and idx <= total_repos_count:
            remaining_repos = total_repos_count - idx + 1
            logger.warning(
                t("log_relay_triggered", lang=current_lang, max_minutes=max_runtime_minutes, remaining=remaining_repos)
            )
            current_repo = os.environ.get("GITHUB_REPOSITORY")
            current_ref = os.environ.get("GITHUB_REF_NAME", "main")
            if current_repo:
                relay_resp = client.post(
                    f"/repos/{current_repo}/actions/workflows/sync_forks.yml/dispatches",
                    json_data={"ref": current_ref},
                )
                if relay_resp.status_code in (200, 204):
                    logger.info(t("log_relay_success", lang=current_lang))
                    warnings_list.append(
                        t("auto_relay_triggered", lang=current_lang, minutes=int(elapsed_min), remaining=remaining_repos)
                    )
                else:
                    logger.error(t("log_relay_failed", lang=current_lang, status=relay_resp.status_code, detail=relay_resp.text))
            break

        repo_full_name = repo_data.get("full_name", "")
        progress_pct = int((idx / total_repos_count) * 100) if total_repos_count > 0 else 100

        logger.info(f"\n" + "-" * 60)
        if debug_mode:
            logger.info(t("log_processing_repo_debug", lang=current_lang, idx=idx, total=total_repos_count, percent=progress_pct, repo=repo_full_name))
        else:
            logger.info(t("log_processing_repo_std", lang=current_lang, percent=progress_pct))
        logger.info("-" * 60)

        if log_filter and repo_data.get("parent"):
            log_filter.add_term(repo_data["parent"].get("full_name", ""))
            log_filter.add_term(repo_data["parent"].get("name", ""))

        # 1. Disable GitHub Actions if enabled in config
        if config.get("disable_actions", True):
            ok, msg = disable_repo_actions(client, repo_full_name)
            if ok:
                stats["actions_disabled_repos"] += 1
            else:
                warnings_list.append(f"`{repo_full_name}`: {t('actions_disabled_failed', lang=current_lang, msg=msg)}")

        # 2. Sync all branches
        try:
            repo_res = sync_repository_branches(client, repo_data, debug_mode=debug_mode)
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

        if debug_mode:
            logger.info(
                t(
                    "log_repo_done_debug",
                    lang=current_lang,
                    idx=idx,
                    total=total_repos_count,
                    repo=repo_full_name,
                    synced=stats["synced_branches"],
                    created=stats["created_branches"],
                    uptodate=stats["uptodate_branches"],
                    skipped=stats["skipped_branches"],
                    failed=stats["failed"],
                )
            )
        else:
            logger.info(t("log_repo_done_std", lang=current_lang, percent=progress_pct))

    end_time = datetime.now(timezone.utc)

    if getattr(client, "token_expiration", None):
        warnings_list.append(t("log_token_expiry", lang=current_lang, expiry=client.token_expiration))

    # Output GitHub Step Summary
    debug_mode = config.get("debug_mode", False)
    summary_md = generate_step_summary(results, stats, start_time, end_time, debug_mode=debug_mode, lang=current_lang)
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
    if feishu_webhook:
        logger.info("Sending Feishu notification card...")
        send_feishu_card(
            webhook_url=feishu_webhook,
            secret=feishu_secret,
            title=t("feishu_default_title", lang=current_lang),
            stats=stats,
            warnings=warnings_list,
            errors=errors_list,
            execution_time_str=start_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
            lang=current_lang,
        )

    # Send Email Notification
    send_email_notification(
        smtp_config=config,
        title=t("summary_title", lang=current_lang),
        stats=stats,
        warnings=warnings_list,
        errors=errors_list,
        execution_time_str=start_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
        lang=current_lang,
    )

    logger.info(t("log_job_finished", lang=current_lang))
    return 0


if __name__ == "__main__":
    sys.exit(main())
