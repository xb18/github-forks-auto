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


def send_feishu_card(
    webhook_url: str,
    secret: Optional[str],
    title: str,
    stats: Dict[str, int],
    warnings: List[str],
    errors: List[str],
    execution_time_str: str,
) -> bool:
    """
    Send an interactive card notification to Feishu custom bot webhook.
    """
    if not webhook_url:
        logger.info("Feishu webhook URL not configured, skipping notification.")
        return False

    timestamp = int(time.time())
    headers = {"Content-Type": "application/json"}

    has_issues = len(warnings) > 0 or len(errors) > 0 or stats.get("failed", 0) > 0
    header_color = "red" if (len(errors) > 0 or stats.get("failed", 0) > 0) else ("orange" if len(warnings) > 0 else "blue")

    # Build markdown content for statistics
    stats_md = (
        f"**⏰ 执行时间**: {execution_time_str}\n"
        f"**📦 扫描 Fork 仓库**: {stats.get('total_repos', 0)} 个\n"
        f"**⚡ 分支同步成功 (Fast-Forward)**: {stats.get('synced_branches', 0)} 个\n"
        f"**🌱 上游新增分支创建**: {stats.get('created_branches', 0)} 个\n"
        f"**✅ 已是最新分支**: {stats.get('uptodate_branches', 0)} 个\n"
        f"**🛡️ 安全跳过 (分叉/硬回退保护)**: {stats.get('skipped_branches', 0)} 个\n"
        f"**🚫 Actions 已禁用仓库**: {stats.get('actions_disabled_repos', 0)} 个"
    )
    if stats.get("failed", 0) > 0:
        stats_md += f"\n**❌ 失败/异常**: {stats.get('failed', 0)} 个"

    elements: List[Dict[str, Any]] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": stats_md,
            },
        }
    ]

    # Add warnings section if any
    if warnings:
        warn_content = "**🛡️ 安全拦截与提醒事项 (避免代码丢失)**:\n" + "\n".join(f"- {w}" for w in warnings[:15])
        if len(warnings) > 15:
            warn_content += f"\n- ... 另有 {len(warnings) - 15} 条跳过记录，详见 GitHub Actions 日志"
        elements.extend([
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": warn_content,
                },
            },
        ])

    # Add errors section if any
    if errors:
        err_content = "**❌ 异常失败记录**:\n" + "\n".join(f"- {e}" for e in errors[:10])
        elements.extend([
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": err_content,
                },
            },
        ])

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
                "template": header_color,
            },
            "elements": elements,
        },
    }

    if secret:
        card_payload["timestamp"] = str(timestamp)
        card_payload["sign"] = generate_feishu_sign(secret, timestamp)

    try:
        resp = requests.post(webhook_url, json=card_payload, headers=headers, timeout=15)
        resp_data = resp.json() if resp.status_code == 200 else {}
        if resp.status_code == 200 and resp_data.get("code") == 0:
            logger.info("Feishu notification sent successfully.")
            return True
        else:
            logger.error(f"Failed to send Feishu notification: {resp.status_code} {resp.text}")
            return False
    except Exception as exc:
        logger.error(f"Exception sending Feishu notification: {exc}")
        return False


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
