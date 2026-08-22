"""Module to send Feishu (Lark) Bot Webhook notifications with rich interactive cards."""

import base64
import hashlib
import hmac
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger("feishu_notifier")


def generate_feishu_sign(secret: str, timestamp: int) -> str:
    """Generate Feishu webhook signature using HMAC-SHA256."""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    sign = base64.b64encode(hmac_code).decode("utf-8")
    return sign


def send_single_feishu_payload(
    webhook_url: str,
    secret: Optional[str],
    card_dict: Dict[str, Any],
) -> bool:
    """Send a single interactive card payload to Feishu webhook."""
    timestamp = int(time.time())
    headers = {"Content-Type": "application/json"}

    card_payload: Dict[str, Any] = {
        "msg_type": "interactive",
        "card": card_dict,
    }

    if secret:
        card_payload["timestamp"] = str(timestamp)
        card_payload["sign"] = generate_feishu_sign(secret, timestamp)

    try:
        resp = requests.post(webhook_url, json=card_payload, headers=headers, timeout=15)
        resp_data = resp.json() if resp.status_code == 200 else {}
        if resp.status_code == 200 and resp_data.get("code") == 0:
            return True
        else:
            logger.error(f"Failed to send Feishu card: {resp.status_code} {resp.text}")
            return False
    except Exception as exc:
        logger.error(f"Exception sending Feishu card: {exc}")
        return False


def chunk_list(items: List[Any], chunk_size: int) -> List[List[Any]]:
    """Split a list into smaller chunks."""
    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]


import os

def extract_repo_names(items: List[str]) -> List[str]:
    """Extract and deduplicate repository names from warning/error logs."""
    repos: List[str] = []
    for item in items:
        m = re.search(r'`([^`]+)`', item)
        if m:
            name = m.group(1)
            if name not in repos:
                repos.append(name)
        else:
            first_part = item.split()[0].rstrip(":")
            if first_part and first_part not in repos:
                repos.append(first_part)
    return repos


def format_stats_markdown(
    stats: Dict[str, int],
    execution_time_str: str,
    template_str: Optional[str] = None,
    template_file: str = "report_template.md",
    warnings: Optional[List[str]] = None,
    errors: Optional[List[str]] = None,
) -> str:
    """
    Format the main statistics section using a template file or template string.
    Placeholders:
      {execution_time}, {total_repos}, {actions_disabled_repos},
      {synced_branches}, {created_branches}, {uptodate_branches},
      {skipped_branches}, {failed}, {status_emoji}, {status_text},
      {issues}, {warnings}, {errors},
      {issue_repos}, {issue_repos_inline},
      {warning_repos}, {warning_repos_inline},
      {error_repos}, {error_repos_inline}
    """
    warnings = warnings or []
    errors = errors or []

    raw_template = template_str
    if not raw_template and os.path.exists(template_file):
        try:
            with open(template_file, "r", encoding="utf-8") as f:
                raw_template = f.read().strip()
        except Exception as exc:
            logger.warning(f"Failed to read template file {template_file}: {exc}")

    failed_count = stats.get("failed", 0)
    skipped_count = stats.get("skipped_branches", 0)
    status_text = "发生异常" if failed_count > 0 else ("有跳过提醒" if skipped_count > 0 else "全部正常")
    status_emoji = "🔴" if failed_count > 0 else ("🟡" if skipped_count > 0 else "🟢")

    # Build issue strings (full detail with branch and reason)
    warn_text = "\n".join(f"- {w}" for w in warnings) if warnings else "无"
    err_text = "\n".join(f"- {e}" for e in errors) if errors else "无"

    issues_list = []
    if warnings:
        issues_list.append("**🛡️ 安全拦截与提醒事项 (避免代码丢失)**:\n" + warn_text)
    if errors:
        issues_list.append("**❌ 异常失败记录**:\n" + err_text)
    issues_text = "\n\n".join(issues_list) if issues_list else "✅ 所有分支均保持最新或同步成功，无异常与跳过记录。"

    # Build repo-only strings (pure repository names without branch or verbose messages)
    warn_repos = extract_repo_names(warnings)
    err_repos = extract_repo_names(errors)
    all_issue_repos = list(dict.fromkeys(warn_repos + err_repos))

    issue_repos_text = "\n".join(f"- `{r}`" for r in all_issue_repos) if all_issue_repos else "✅ 无"
    issue_repos_inline_text = ", ".join(f"`{r}`" for r in all_issue_repos) if all_issue_repos else "✅ 无"
    warning_repos_text = "\n".join(f"- `{r}`" for r in warn_repos) if warn_repos else "✅ 无"
    warning_repos_inline_text = ", ".join(f"`{r}`" for r in warn_repos) if warn_repos else "✅ 无"
    error_repos_text = "\n".join(f"- `{r}`" for r in err_repos) if err_repos else "✅ 无"
    error_repos_inline_text = ", ".join(f"`{r}`" for r in err_repos) if err_repos else "✅ 无"

    if raw_template:
        replacements = {
            "execution_time": execution_time_str,
            "total_repos": str(stats.get("total_repos", 0)),
            "actions_disabled_repos": str(stats.get("actions_disabled_repos", 0)),
            "synced_branches": str(stats.get("synced_branches", 0)),
            "created_branches": str(stats.get("created_branches", 0)),
            "uptodate_branches": str(stats.get("uptodate_branches", 0)),
            "skipped_branches": str(stats.get("skipped_branches", 0)),
            "failed": str(failed_count),
            "status_text": status_text,
            "status_emoji": status_emoji,
            "issues": issues_text,
            "warnings": warn_text,
            "errors": err_text,
            "issue_repos": issue_repos_text,
            "issue_repos_inline": issue_repos_inline_text,
            "warning_repos": warning_repos_text,
            "warning_repos_inline": warning_repos_inline_text,
            "error_repos": error_repos_text,
            "error_repos_inline": error_repos_inline_text,
        }
        res = raw_template
        for key, val in replacements.items():
            res = res.replace(f"{{{key}}}", val)
        return res

    # Default fallback layout
    lines = [
        f"**⏰ 执行时间**: {execution_time_str}",
        "",
        "**📦 仓库处理概览**",
        f"• 扫描 Fork 仓库总数: **{stats.get('total_repos', 0)}** 个",
        f"• Actions 已禁用仓库: **{stats.get('actions_disabled_repos', 0)}** 个",
        "",
        "**🌿 分支变动明细**",
        f"• ⚡ 安全快进同步: **{stats.get('synced_branches', 0)}** 个分支",
        f"• 🌱 上游新建分支: **{stats.get('created_branches', 0)}** 个分支",
        f"• ✅ 保持最新状态: **{stats.get('uptodate_branches', 0)}** 个分支",
        f"• 🛡️ 安全跳过保护: **{stats.get('skipped_branches', 0)}** 个分支",
    ]

    if failed_count > 0:
        lines.append(f"• ❌ 同步异常失败: **{failed_count}** 个")

    return "\n".join(lines)


def send_feishu_card(
    webhook_url: str,
    secret: Optional[str],
    title: str,
    stats: Dict[str, int],
    warnings: List[str],
    errors: List[str],
    execution_time_str: str,
    batch_size: int = 15,
    template_str: Optional[str] = None,
) -> bool:
    """
    Send an interactive card notification to Feishu custom bot webhook.
    Automatically splits long reports across multiple cards if necessary.
    """
    if not webhook_url:
        logger.info("Feishu webhook URL not configured, skipping notification.")
        return False

    header_color = "red" if (len(errors) > 0 or stats.get("failed", 0) > 0) else ("orange" if len(warnings) > 0 else "blue")

    # Read template if exists to check if user already embedded {issues}, {warnings}, or {errors}
    raw_template = template_str
    if not raw_template and os.path.exists("report_template.md"):
        try:
            with open("report_template.md", "r", encoding="utf-8") as f:
                raw_template = f.read()
        except Exception:
            pass

    template_has_issues = raw_template and any(k in raw_template for k in ("{issues}", "{warnings}", "{errors}"))

    # Chunk warnings and errors for multi-card if needed
    warn_chunks = chunk_list(warnings, batch_size) if warnings else []
    err_chunks = chunk_list(errors, batch_size) if errors else []

    # Build structured markdown content for statistics
    first_warn = warn_chunks[0] if warn_chunks else []
    first_err = err_chunks[0] if err_chunks else []
    stats_md = format_stats_markdown(
        stats,
        execution_time_str,
        template_str=template_str,
        warnings=first_warn if template_has_issues else [],
        errors=first_err if template_has_issues else [],
    )

    # Chunk warnings and errors
    warn_chunks = chunk_list(warnings, batch_size) if warnings else []
    err_chunks = chunk_list(errors, batch_size) if errors else []

    # Calculate total cards needed
    total_parts = 1 + max(0, len(warn_chunks) - 1) + max(0, len(err_chunks) - 1)
    if len(warn_chunks) > 1 and len(err_chunks) > 1:
        total_parts = 1 + (len(warn_chunks) - 1) + (len(err_chunks) - 1)
    elif len(warn_chunks) > 1:
        total_parts = len(warn_chunks)
    elif len(err_chunks) > 1:
        total_parts = len(err_chunks)

    # 1. First Card (Overview + First batch of warnings/errors)
    first_elements: List[Dict[str, Any]] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": stats_md,
            },
        }
    ]

    if warn_chunks:
        warn_text = "**🛡️ 安全拦截与提醒事项 (避免代码丢失)**:\n" + "\n".join(f"- {w}" for w in warn_chunks[0])
        first_elements.extend([
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": warn_text}},
        ])

    if err_chunks:
        err_text = "**❌ 异常失败记录**:\n" + "\n".join(f"- {e}" for e in err_chunks[0])
        first_elements.extend([
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": err_text}},
        ])

    first_title = f"{title} (1/{total_parts})" if total_parts > 1 else title
    first_card = {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": first_title}, "template": header_color},
        "elements": first_elements,
    }

    all_success = send_single_feishu_payload(webhook_url, secret, first_card)

    # 2. Subsequent Cards for remaining warnings
    current_part = 2
    for w_chunk in warn_chunks[1:]:
        time.sleep(0.5)
        w_text = f"**🛡️ 提醒事项续前页 (第 {current_part} 部分)**:\n" + "\n".join(f"- {w}" for w in w_chunk)
        sub_card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"{title} (续 {current_part}/{total_parts})"},
                "template": header_color,
            },
            "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": w_text}}],
        }
        ok = send_single_feishu_payload(webhook_url, secret, sub_card)
        all_success = all_success and ok
        current_part += 1

    # 3. Subsequent Cards for remaining errors
    for e_chunk in err_chunks[1:]:
        time.sleep(0.5)
        e_text = f"**❌ 异常失败记录续前页 (第 {current_part} 部分)**:\n" + "\n".join(f"- {e}" for e in e_chunk)
        sub_card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"{title} (续 {current_part}/{total_parts})"},
                "template": "red",
            },
            "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": e_text}}],
        }
        ok = send_single_feishu_payload(webhook_url, secret, sub_card)
        all_success = all_success and ok
        current_part += 1

    return all_success


def send_feishu_alert(
    webhook_url: str,
    secret: Optional[str],
    title: str,
    message: str,
    action_url: str = "https://github.com/settings/tokens",
) -> bool:
    """
    Send an urgent alert card to Feishu webhook (e.g. for Token expired / Auth failure).
    """
    if not webhook_url:
        return False

    timestamp = int(time.time())
    headers = {"Content-Type": "application/json"}

    card_payload: Dict[str, Any] = {
        "msg_type": "interactive",
        "card": {
            "config": {
                "wide_screen_mode": True,
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title,
                },
                "template": "red",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": message,
                    },
                },
                {"tag": "hr"},
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "🔑 前往 GitHub 重新生成 Token",
                            },
                            "type": "danger",
                            "url": action_url,
                        }
                    ],
                },
            ],
        },
    }

    if secret:
        card_payload["timestamp"] = str(timestamp)
        card_payload["sign"] = generate_feishu_sign(secret, timestamp)

    try:
        resp = requests.post(webhook_url, json=card_payload, headers=headers, timeout=15)
        return resp.status_code == 200 and resp.json().get("code") == 0
    except Exception as exc:
        logger.error(f"Exception sending Feishu alert: {exc}")
        return False
