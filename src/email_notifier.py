"""Module to send email notifications via SMTP with rich responsive HTML styling."""

import logging
import os
import smtplib
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr
from typing import Any, Dict, List, Optional, Tuple

from .feishu import extract_repo_names
from .i18n import get_current_language, t

logger = logging.getLogger("email_notifier")


def is_smtp_configured(config: Dict[str, Any]) -> bool:
    """Check if minimum required SMTP settings are present."""
    host = config.get("smtp_host") or os.environ.get("SMTP_HOST") or os.environ.get("SMTP_SERVER")
    user = config.get("smtp_user") or os.environ.get("SMTP_USER") or os.environ.get("SMTP_USERNAME")
    password = config.get("smtp_pass") or os.environ.get("SMTP_PASS") or os.environ.get("SMTP_PASSWORD") or os.environ.get("SMTP_AUTH_CODE")
    return bool(host and user and password)


def parse_recipients(to_val: Any, default_user: str) -> List[str]:
    """Parse comma/semicolon separated email addresses or list."""
    if isinstance(to_val, list):
        res = [str(x).strip() for x in to_val if str(x).strip()]
        return res if res else [default_user]
    if isinstance(to_val, str) and to_val.strip():
        import re
        recipients = [x.strip() for x in re.split(r'[,;\s]+', to_val) if x.strip() and "@" in x]
        return recipients if recipients else [default_user]
    return [default_user] if default_user else []


def build_html_report(
    title: str,
    stats: Dict[str, int],
    warnings: List[str],
    errors: List[str],
    execution_time_str: str,
    lang: Optional[str] = None,
) -> str:
    """Generate modern, responsive HTML email content."""
    failed_count = stats.get("failed", 0)
    skipped_count = stats.get("skipped_branches", 0)

    if failed_count > 0:
        status_color = "#dc2626"  # Red
        status_bg = "#fef2f2"
        status_badge = t("email_badge_error", lang=lang)
        status_icon = "🔴"
    elif skipped_count > 0:
        status_color = "#d97706"  # Amber
        status_bg = "#fffbeb"
        status_badge = t("email_badge_warning", lang=lang)
        status_icon = "🟡"
    else:
        status_color = "#16a34a"  # Green
        status_bg = "#f0fdf4"
        status_badge = t("email_badge_ok", lang=lang)
        status_icon = "🟢"

    # Repo-only extracted names for warning/error summary
    warn_repos = extract_repo_names(warnings)
    err_repos = extract_repo_names(errors)

    warn_items_html = "".join(f'<li style="margin-bottom: 6px; color: #4b5563;">{w}</li>' for w in warnings)
    err_items_html = "".join(f'<li style="margin-bottom: 6px; color: #991b1b;">{e}</li>' for e in errors)

    warnings_section = ""
    if warnings:
        warnings_section = f"""
        <div style="margin-top: 24px; padding: 16px; background-color: #fffbeb; border: 1px solid #fef3c7; border-radius: 8px;">
            <div style="font-weight: 600; color: #92400e; margin-bottom: 10px; font-size: 15px;">
                {t("email_section_warnings", lang=lang)} ({len(warnings)})
            </div>
            <ul style="margin: 0; padding-left: 20px; font-size: 13px; line-height: 1.6;">
                {warn_items_html}
            </ul>
        </div>
        """

    errors_section = ""
    if errors:
        errors_section = f"""
        <div style="margin-top: 24px; padding: 16px; background-color: #fef2f2; border: 1px solid #fee2e2; border-radius: 8px;">
            <div style="font-weight: 600; color: #991b1b; margin-bottom: 10px; font-size: 15px;">
                {t("email_section_errors", lang=lang)} ({len(errors)})
            </div>
            <ul style="margin: 0; padding-left: 20px; font-size: 13px; line-height: 1.6;">
                {err_items_html}
            </ul>
        </div>
        """

    repo_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com") + "/" + os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID")
    action_url = f"{repo_url}/actions/runs/{run_id}" if run_id else repo_url

    btn_html = ""
    if os.environ.get("GITHUB_REPOSITORY"):
        btn_html = f"""
        <div style="text-align: center; margin-top: 28px; margin-bottom: 10px;">
            <a href="{action_url}" target="_blank" style="display: inline-block; padding: 10px 24px; background-color: #2563eb; color: #ffffff; text-decoration: none; border-radius: 6px; font-weight: 500; font-size: 14px;">
                {t("email_btn_view_workflow", lang=lang)} &rarr;
            </a>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
</head>
<body style="margin: 0; padding: 20px; background-color: #f3f4f6; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1f2937;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width: 640px; margin: 0 auto; background-color: #ffffff; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.08);">
    <!-- Header -->
    <tr>
      <td style="padding: 24px 30px; background-color: #1e293b; color: #ffffff;">
        <div style="font-size: 20px; font-weight: 700; display: flex; align-items: center;">
          {title}
        </div>
        <div style="font-size: 12px; color: #94a3b8; margin-top: 6px;">
          {execution_time_str}
        </div>
      </td>
    </tr>

    <!-- Body -->
    <tr>
      <td style="padding: 24px 30px;">
        <!-- Status Badge -->
        <div style="margin-bottom: 20px; padding: 12px 16px; background-color: {status_bg}; border-left: 4px solid {status_color}; border-radius: 4px; display: flex; align-items: center; justify-content: space-between;">
          <span style="font-weight: 600; color: {status_color}; font-size: 15px;">
            {status_icon} {status_badge}
          </span>
        </div>

        <!-- Stats Grid / Table -->
        <table width="100%" cellspacing="0" cellpadding="0" style="border-collapse: collapse; margin-top: 16px; border: 1px solid #e5e7eb; border-radius: 6px; overflow: hidden;">
          <tr style="background-color: #f8fafc; border-bottom: 1px solid #e5e7eb;">
            <th style="padding: 10px 14px; text-align: left; font-size: 13px; color: #64748b; font-weight: 600;">{t("summary_metric_col", lang=lang)}</th>
            <th style="padding: 10px 14px; text-align: right; font-size: 13px; color: #64748b; font-weight: 600;">{t("summary_count_col", lang=lang)}</th>
          </tr>
          <tr style="border-bottom: 1px solid #f1f5f9;">
            <td style="padding: 10px 14px; font-size: 14px;">{t("summary_total_repos", lang=lang)}</td>
            <td style="padding: 10px 14px; font-size: 14px; text-align: right; font-weight: 600;">{stats.get("total_repos", 0)}</td>
          </tr>
          <tr style="border-bottom: 1px solid #f1f5f9;">
            <td style="padding: 10px 14px; font-size: 14px;">{t("summary_disabled_actions", lang=lang)}</td>
            <td style="padding: 10px 14px; font-size: 14px; text-align: right; font-weight: 600; color: #0284c7;">{stats.get("actions_disabled_repos", 0)}</td>
          </tr>
          <tr style="border-bottom: 1px solid #f1f5f9;">
            <td style="padding: 10px 14px; font-size: 14px;">{t("summary_synced_branches", lang=lang)}</td>
            <td style="padding: 10px 14px; font-size: 14px; text-align: right; font-weight: 600; color: #16a34a;">{stats.get("synced_branches", 0)}</td>
          </tr>
          <tr style="border-bottom: 1px solid #f1f5f9;">
            <td style="padding: 10px 14px; font-size: 14px;">{t("summary_created_branches", lang=lang)}</td>
            <td style="padding: 10px 14px; font-size: 14px; text-align: right; font-weight: 600; color: #059669;">{stats.get("created_branches", 0)}</td>
          </tr>
          <tr style="border-bottom: 1px solid #f1f5f9;">
            <td style="padding: 10px 14px; font-size: 14px;">{t("summary_uptodate_branches", lang=lang)}</td>
            <td style="padding: 10px 14px; font-size: 14px; text-align: right; font-weight: 600; color: #64748b;">{stats.get("uptodate_branches", 0)}</td>
          </tr>
          <tr style="border-bottom: 1px solid #f1f5f9;">
            <td style="padding: 10px 14px; font-size: 14px;">{t("summary_skipped_branches", lang=lang)}</td>
            <td style="padding: 10px 14px; font-size: 14px; text-align: right; font-weight: 600; color: #d97706;">{stats.get("skipped_branches", 0)}</td>
          </tr>
          <tr>
            <td style="padding: 10px 14px; font-size: 14px;">{t("summary_failed", lang=lang)}</td>
            <td style="padding: 10px 14px; font-size: 14px; text-align: right; font-weight: 600; color: {'#dc2626' if failed_count > 0 else '#64748b'};">{failed_count}</td>
          </tr>
        </table>

        {warnings_section}
        {errors_section}
        {btn_html}
      </td>
    </tr>

    <!-- Footer -->
    <tr>
      <td style="padding: 16px 30px; background-color: #f8fafc; border-top: 1px solid #e2e8f0; font-size: 12px; color: #94a3b8; text-align: center;">
        {t("email_footer_text", lang=lang)}
      </td>
    </tr>
  </table>
</body>
</html>
"""
    return html


def build_plain_report(
    title: str,
    stats: Dict[str, int],
    warnings: List[str],
    errors: List[str],
    execution_time_str: str,
    lang: Optional[str] = None,
) -> str:
    """Generate plaintext email content as fallback."""
    lines = [
        f"{title}",
        f"{execution_time_str}",
        "=" * 40,
        f"{t('summary_total_repos', lang=lang)}: {stats.get('total_repos', 0)}",
        f"{t('summary_disabled_actions', lang=lang)}: {stats.get('actions_disabled_repos', 0)}",
        f"{t('summary_synced_branches', lang=lang)}: {stats.get('synced_branches', 0)}",
        f"{t('summary_created_branches', lang=lang)}: {stats.get('created_branches', 0)}",
        f"{t('summary_uptodate_branches', lang=lang)}: {stats.get('uptodate_branches', 0)}",
        f"{t('summary_skipped_branches', lang=lang)}: {stats.get('skipped_branches', 0)}",
        f"{t('summary_failed', lang=lang)}: {stats.get('failed', 0)}",
    ]

    if warnings:
        lines.append("")
        lines.append(f"{t('email_section_warnings', lang=lang)}:")
        for w in warnings:
            lines.append(f"- {w}")

    if errors:
        lines.append("")
        lines.append(f"{t('email_section_errors', lang=lang)}:")
        for e in errors:
            lines.append(f"- {e}")

    lines.append("")
    lines.append(t("email_footer_text", lang=lang))
    return "\n".join(lines)


def _send_smtp_message(
    smtp_config: Dict[str, Any],
    subject: str,
    text_content: str,
    html_content: Optional[str] = None,
) -> bool:
    """Internal helper to dispatch email via SMTP / SMTP_SSL / STARTTLS."""
    host = smtp_config.get("smtp_host") or os.environ.get("SMTP_HOST") or os.environ.get("SMTP_SERVER", "")
    port_val = smtp_config.get("smtp_port") or os.environ.get("SMTP_PORT", "")
    user = smtp_config.get("smtp_user") or os.environ.get("SMTP_USER") or os.environ.get("SMTP_USERNAME", "")
    password = smtp_config.get("smtp_pass") or os.environ.get("SMTP_PASS") or os.environ.get("SMTP_PASSWORD") or os.environ.get("SMTP_AUTH_CODE", "")
    from_name = smtp_config.get("smtp_from_name") or os.environ.get("SMTP_FROM_NAME", "GitHub Forks Auto")
    to_val = smtp_config.get("smtp_to") or os.environ.get("SMTP_TO") or os.environ.get("EMAIL_TO", "")

    if not host or not user or not password:
        logger.warning("SMTP configuration is incomplete. Skipping email notification.")
        return False

    try:
        port = int(port_val) if port_val else (465 if smtp_config.get("smtp_ssl") else 587)
    except Exception:
        port = 465

    use_ssl = smtp_config.get("smtp_ssl")
    if use_ssl is None:
        use_ssl = (port == 465)

    use_tls = smtp_config.get("smtp_tls")
    if use_tls is None:
        use_tls = (port in (587, 25))

    recipients = parse_recipients(to_val, default_user=user)
    if not recipients:
        logger.warning("No valid email recipients specified. Skipping email.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(subject, "utf-8").encode()
    msg["From"] = formataddr((Header(from_name, "utf-8").encode(), user))
    msg["To"] = ", ".join(recipients)

    msg.attach(MIMEText(text_content, "plain", "utf-8"))
    if html_content:
        msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        if use_ssl:
            server = smtplib.SMTP_SSL(host, port, timeout=20)
        else:
            server = smtplib.SMTP(host, port, timeout=20)
            if use_tls:
                server.starttls()

        server.login(user, password)
        server.sendmail(user, recipients, msg.as_string())
        server.quit()
        logger.info(f"Successfully sent email notification to: {', '.join(recipients)}")
        return True
    except Exception as exc:
        logger.error(f"Failed to send email via SMTP ({host}:{port}): {exc}")
        return False


def send_email_notification(
    smtp_config: Dict[str, Any],
    title: str,
    stats: Dict[str, int],
    warnings: List[str],
    errors: List[str],
    execution_time_str: str,
    lang: Optional[str] = None,
) -> bool:
    """Send summary report email to configured recipient(s)."""
    if not is_smtp_configured(smtp_config):
        return False

    failed_count = stats.get("failed", 0)
    skipped_count = stats.get("skipped_branches", 0)
    status_text = (
        t("status_error", lang=lang)
        if failed_count > 0
        else (t("status_warning", lang=lang) if skipped_count > 0 else t("status_all_ok", lang=lang))
    )

    subject = t("email_default_subject", lang=lang, status_text=status_text)
    html_body = build_html_report(title, stats, warnings, errors, execution_time_str, lang=lang)
    text_body = build_plain_report(title, stats, warnings, errors, execution_time_str, lang=lang)

    return _send_smtp_message(smtp_config, subject, text_body, html_body)


def send_email_alert(
    smtp_config: Dict[str, Any],
    title: str,
    message: str,
    action_url: str = "https://github.com/settings/tokens",
    lang: Optional[str] = None,
) -> bool:
    """Send urgent alert email (e.g. for PAT expired or missing)."""
    if not is_smtp_configured(smtp_config):
        return False

    html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: sans-serif; padding: 20px; background-color: #f9fafb;">
  <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 8px; overflow: hidden; border: 1px solid #fee2e2;">
    <div style="background: #dc2626; color: #ffffff; padding: 18px 24px; font-size: 18px; font-weight: bold;">
      {title}
    </div>
    <div style="padding: 24px; color: #374151; font-size: 14px; line-height: 1.6;">
      <p style="white-space: pre-wrap;">{message}</p>
      <div style="margin-top: 24px; text-align: center;">
        <a href="{action_url}" target="_blank" style="background: #dc2626; color: #ffffff; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: 500; display: inline-block;">
          {t("feishu_btn_reauth", lang=lang)}
        </a>
      </div>
    </div>
  </div>
</body>
</html>
"""
    return _send_smtp_message(smtp_config, title, message, html_content)
