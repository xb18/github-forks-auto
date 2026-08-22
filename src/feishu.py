"""Module to send Feishu (Lark) Bot Webhook notifications with rich interactive cards."""

import base64
import hashlib
import hmac
import logging
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


def format_stats_markdown(stats: Dict[str, int], execution_time_str: str) -> str:
    """
    Format the main statistics section with clear hierarchical layout.
    Modify this function if you want to change the order, icons, or wording of the summary card.
    """
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

    if stats.get("failed", 0) > 0:
        lines.append(f"• ❌ 同步异常失败: **{stats.get('failed', 0)}** 个")

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
) -> bool:
    """
    Send an interactive card notification to Feishu custom bot webhook.
    Automatically splits long reports across multiple cards if necessary.
    """
    if not webhook_url:
        logger.info("Feishu webhook URL not configured, skipping notification.")
        return False

    header_color = "red" if (len(errors) > 0 or stats.get("failed", 0) > 0) else ("orange" if len(warnings) > 0 else "blue")

    # Build structured markdown content for statistics
    stats_md = format_stats_markdown(stats, execution_time_str)

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
