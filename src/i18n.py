"""Internationalization (i18n) support for GitHub Forks Auto Sync."""

import os
from typing import Any, Dict, Optional

MESSAGES: Dict[str, Dict[str, str]] = {
    "zh": {
        # General & Status
        "status_all_ok": "全部正常",
        "status_warning": "有跳过提醒",
        "status_error": "发生异常",
        "status_none": "无",
        "status_none_ok": "- ✅ 无 (全部正常)",
        "all_branches_ok": "✅ 所有分支均保持最新或同步成功，无异常与跳过记录。",
        
        # Branch Status Messages
        "branch_created": "从上游新建分支成功",
        "branch_up_to_date": "分支已是最新状态",
        "branch_fast_forward": "安全快进同步 +{count} 个提交",
        "branch_diverged": "Diverged 分叉保护 (Fork 领先 {behind_by}，落后 {ahead_by})：上游可能存在硬回退(Force Push)或本地有独立提交，已跳过防丢失代码",
        "branch_fork_ahead": "Fork 本地领先上游 {behind_by} 个提交 (保留本地独有代码)，已跳过同步",
        "branch_unusual_status": "异常比对状态 '{compare_status}' (领先: {ahead_by}, 落后: {behind_by})，已跳过",
        "branch_create_failed": "新建分支失败 ({status}): {detail}",
        "branch_update_failed": "更新分支失败 ({status}): {detail}",
        "branch_compare_failed": "比对分支祖先关系失败 ({status}): {detail}",
        "branch_not_a_fork": "不是 Fork 仓库",
        "branch_parent_not_found": "未找到上游父仓库（可能上游已被删除或 Fork 关系已解除）",
        "branch_upstream_empty": "上游仓库 '{upstream}' 未检测到可访问的分支",
        "branch_fetch_failed": "获取仓库分支失败: {detail}",
        "branch_no_branches_detected": "未检测到可同步分支",
        
        # Status labels for table
        "status_label_synced": "⚡ 已同步",
        "status_label_created": "🌱 新建分支",
        "status_label_uptodate": "✅ 已最新",
        "status_label_skipped_diverged": "🛡️ 分叉跳过",
        "status_label_skipped_ahead": "🛡️ 本地领先",
        "status_label_error": "❌ 失败",
        "status_label_no_branches": "⚠️ 无分支",
        
        # Actions & Disabler
        "actions_disabled_ok": "Actions 禁用成功",
        "actions_disabled_failed": "Actions 禁用未成功 ({msg})",
        
        # Summary & Actions
        "summary_title": "GitHub Forks 同步报告",
        "summary_workflow_title": "## 🔄 GitHub Fork 仓库全量同步与管理报告",
        "summary_time_header": "**执行时间**: `{time_str}` | **总耗时**: `{duration:.1f}s`",
        "summary_stats_header": "### 📊 同步统计概览",
        "summary_metric_col": "指标",
        "summary_count_col": "数量",
        "summary_total_repos": "📦 扫描 Fork 仓库总数",
        "summary_synced_branches": "⚡ 分支同步成功 (Fast-Forward)",
        "summary_created_branches": "🌱 上游新增分支创建",
        "summary_uptodate_branches": "✅ 已是最新状态分支",
        "summary_skipped_branches": "🛡️ 安全跳过 (分叉/硬回退保护)",
        "summary_disabled_actions": "🚫 Actions 已禁用仓库",
        "summary_failed": "❌ 异常/失败",
        "summary_standard_mode_note": "> ℹ️ **当前为标准日志模式**：仅展示统计总览。如需在 GitHub 页面公开显示每个仓库的详细处理明细表格，请开启 Secret `DEBUG_MODE=true`。详细明细已同步推送至通知渠道。",
        "summary_debug_table_header": "### 📝 仓库处理明细 (Debug Mode)",
        "summary_table_repo": "仓库名称",
        "summary_table_upstream": "上游仓库",
        "summary_table_branch": "分支",
        "summary_table_status": "状态",
        "summary_table_details": "详细信息",
        
        # Feishu
        "feishu_default_title": "🔄 GitHub Fork 仓库同步完成",
        "feishu_alert_title_auth": "🚨 GitHub Fork 同步失败：Token 已过期或失效",
        "feishu_alert_title_missing_pat": "🚨 GitHub Fork 同步失败：未配置 GH_PAT",
        "feishu_warn_section_title": "**🛡️ 安全拦截与提醒事项 (避免代码丢失)**:",
        "feishu_err_section_title": "**❌ 异常失败记录**:",
        "feishu_warn_part_title": "**🛡️ 提醒事项续前页 (第 {current} 部分)**:",
        "feishu_err_part_title": "**❌ 异常失败记录续前页 (第 {current} 部分)**:",
        "feishu_btn_reauth": "🔑 前往 GitHub 重新生成 Token",
        
        # Email
        "email_default_subject": "🔄 GitHub Fork 仓库同步报告 - {status_text}",
        "email_alert_subject_auth": "🚨 GitHub Fork 同步失败：Token 已过期或失效",
        "email_alert_subject_missing_pat": "🚨 GitHub Fork 同步失败：未配置 GH_PAT",
        "email_badge_ok": "全部正常",
        "email_badge_warning": "有跳过提醒",
        "email_badge_error": "发生异常",
        "email_section_stats": "📊 同步统计概览",
        "email_section_warnings": "🛡️ 安全拦截与提醒事项 (避免代码丢失)",
        "email_section_errors": "❌ 异常失败记录",
        "email_footer_text": "本邮件由 GitHub Forks Auto Sync 自动发送",
        "email_btn_view_workflow": "查看 GitHub Actions 运行记录",
        
        # Console / Logs
        "log_authenticated": "已成功鉴权 GitHub 用户: @{username}",
        "log_auth_failed": "❌ **GitHub 身份鉴权失败**: {exc}\n\n⚠️ **原因**: 您的 Personal Access Token (`GH_PAT`) 可能已**过期或被撤销**，导致无法访问 GitHub API。\n\n👉 请尽快重新生成 Token 并更新仓库 Secret。",
        "log_missing_pat": "❌ **错误**: GitHub PAT 密钥 (`GH_PAT`) 未配置，导致同步任务无法执行！",
        "log_fetching_repos": "正在获取用户拥有的全部仓库列表...",
        "log_forks_fetched_std": "已成功获取 Fork 仓库列表，准备开始同步...",
        "log_processing_repo_debug": "🔄 [进度: {idx}/{total} ({percent}%)] 正在处理仓库: {repo}",
        "log_processing_repo_std": "🔄 [进度: {percent}%] 正在处理仓库...",
        "log_repo_done_debug": "✅ [进度: {idx}/{total}] {repo} 处理完毕 | 累计: 同步成功 {synced}, 新建 {created}, 最新 {uptodate}, 跳过 {skipped}, 失败 {failed}",
        "log_repo_done_std": "✅ [进度: {percent}%] 当前仓库处理完毕",
        "log_comparing_branch": "  🌿 正在比对分支...",
        "log_token_expiry": "🔑 Token 有效期: 预计于 `{expiry}` 到期",
        "log_relay_triggered": "⏰ 已达到单次运行时间守护上限 ({max_minutes} 分钟)，剩余 {remaining} 个仓库。正在自动触发接力工作流继续执行...",
        "log_relay_success": "✅ 自动接力工作流触发成功！下一轮任务将立即启动并无缝继续同步。",
        "log_relay_failed": "❌ 触发自动接力工作流失败 ({status}): {detail}",
        "log_job_finished": "Fork 仓库同步与管理任务全部执行完毕。",
        
        # Auto Relay
        "auto_relay_triggered": "⏳ **自动接力已触发**：单次运行已达 {minutes} 分钟安全上限，已自动启动下一轮任务继续同步剩余 {remaining} 个仓库",
    },
    "en": {
        # General & Status
        "status_all_ok": "All Good",
        "status_warning": "Warnings",
        "status_error": "Errors Occurred",
        "status_none": "None",
        "status_none_ok": "- ✅ None (All healthy)",
        "all_branches_ok": "✅ All branches are up-to-date or successfully synced, no issues or skips.",
        
        # Branch Status Messages
        "branch_created": "Successfully created new branch from upstream",
        "branch_up_to_date": "Branch is already up-to-date",
        "branch_fast_forward": "Fast-forwarded +{count} commits",
        "branch_diverged": "Diverged protection (Fork ahead by {behind_by}, behind by {ahead_by}): Upstream may have force-pushed or fork has local commits. Skipped to prevent data loss.",
        "branch_fork_ahead": "Fork is ahead of upstream by {behind_by} commits (preserving local commits), skipped",
        "branch_unusual_status": "Unusual compare status '{compare_status}' (ahead: {ahead_by}, behind: {behind_by}). Skipped.",
        "branch_create_failed": "Failed to create branch ({status}): {detail}",
        "branch_update_failed": "Failed to update branch ref ({status}): {detail}",
        "branch_compare_failed": "Failed to compare branch ancestry ({status}): {detail}",
        "branch_not_a_fork": "Not a fork repository",
        "branch_parent_not_found": "Upstream parent repository not found (it might have been deleted or fork detached)",
        "branch_upstream_empty": "Upstream repository '{upstream}' returned no accessible branches",
        "branch_fetch_failed": "Failed to fetch repository branches: {detail}",
        "branch_no_branches_detected": "No syncable branches detected",
        
        # Status labels for table
        "status_label_synced": "⚡ Synced",
        "status_label_created": "🌱 Created",
        "status_label_uptodate": "✅ Up-to-date",
        "status_label_skipped_diverged": "🛡️ Diverged",
        "status_label_skipped_ahead": "🛡️ Ahead",
        "status_label_error": "❌ Error",
        "status_label_no_branches": "⚠️ No Branches",
        
        # Actions & Disabler
        "actions_disabled_ok": "GitHub Actions successfully disabled",
        "actions_disabled_failed": "Failed to disable Actions ({msg})",
        
        # Summary & Actions
        "summary_title": "GitHub Forks Synchronization Report",
        "summary_workflow_title": "## 🔄 GitHub Forks Full Sync & Management Report",
        "summary_time_header": "**Execution Time**: `{time_str}` | **Total Duration**: `{duration:.1f}s`",
        "summary_stats_header": "### 📊 Synchronization Overview",
        "summary_metric_col": "Metric",
        "summary_count_col": "Count",
        "summary_total_repos": "📦 Total Fork Repositories Scanned",
        "summary_synced_branches": "⚡ Fast-Forward Synced Branches",
        "summary_created_branches": "🌱 New Upstream Branches Created",
        "summary_uptodate_branches": "✅ Up-to-Date Branches",
        "summary_skipped_branches": "🛡️ Safety Skipped (Diverged/Force-Push Protected)",
        "summary_disabled_actions": "🚫 Repositories with Actions Disabled",
        "summary_failed": "❌ Failed / Errors",
        "summary_standard_mode_note": "> ℹ️ **Standard Logging Mode**: Showing summary overview only. To display detailed tables per repository on GitHub Actions, set Secret `DEBUG_MODE=true`. Detailed logs are pushed to notifications.",
        "summary_debug_table_header": "### 📝 Repository Processing Details (Debug Mode)",
        "summary_table_repo": "Repository",
        "summary_table_upstream": "Upstream",
        "summary_table_branch": "Branch",
        "summary_table_status": "Status",
        "summary_table_details": "Details",
        
        # Feishu
        "feishu_default_title": "🔄 GitHub Fork Sync Completed",
        "feishu_alert_title_auth": "🚨 GitHub Fork Sync Failed: Token Expired or Invalid",
        "feishu_alert_title_missing_pat": "🚨 GitHub Fork Sync Failed: GH_PAT Not Configured",
        "feishu_warn_section_title": "**🛡️ Safety Skips & Warnings (Code Loss Prevention)**:",
        "feishu_err_section_title": "**❌ Error & Failure Records**:",
        "feishu_warn_part_title": "**🛡️ Warnings Continued (Part {current})**:",
        "feishu_err_part_title": "**❌ Errors Continued (Part {current})**:",
        "feishu_btn_reauth": "🔑 Go to GitHub to Regenerate Token",
        
        # Email
        "email_default_subject": "🔄 GitHub Forks Sync Report - {status_text}",
        "email_alert_subject_auth": "🚨 GitHub Fork Sync Failed: Token Expired or Invalid",
        "email_alert_subject_missing_pat": "🚨 GitHub Fork Sync Failed: GH_PAT Not Configured",
        "email_badge_ok": "All Good",
        "email_badge_warning": "Warnings",
        "email_badge_error": "Errors Occurred",
        "email_section_stats": "📊 Synchronization Overview",
        "email_section_warnings": "🛡️ Safety Skips & Warnings (Code Loss Prevention)",
        "email_section_errors": "❌ Errors & Failures",
        "email_footer_text": "This email was automatically sent by GitHub Forks Auto Sync",
        "email_btn_view_workflow": "View GitHub Actions Run",
        
        # Console / Logs
        "log_authenticated": "Authenticated as GitHub user: @{username}",
        "log_auth_failed": "❌ **GitHub Authentication Failed**: {exc}\n\n⚠️ **Reason**: Your Personal Access Token (`GH_PAT`) may be **expired or revoked**.\n\n👉 Please regenerate a new token and update your repository Secret.",
        "log_missing_pat": "❌ **Error**: GitHub PAT (`GH_PAT`) is not configured. Synchronization cannot run!",
        "log_fetching_repos": "Fetching all repositories owned by user...",
        "log_forks_fetched_std": "Fork repository list fetched successfully. Ready to sync...",
        "log_processing_repo_debug": "🔄 [Progress: {idx}/{total} ({percent}%)] Processing repository: {repo}",
        "log_processing_repo_std": "🔄 [Progress: {percent}%] Processing repository...",
        "log_repo_done_debug": "✅ [Progress: {idx}/{total}] {repo} finished | Cumulative: Synced {synced}, Created {created}, Up-to-date {uptodate}, Skipped {skipped}, Failed {failed}",
        "log_repo_done_std": "✅ [Progress: {percent}%] Current repository processed",
        "log_comparing_branch": "  🌿 Comparing branch...",
        "log_token_expiry": "🔑 Token Expiration: Expected on `{expiry}`",
        "log_relay_triggered": "⏰ Single run reached time limit ({max_minutes} min), {remaining} repos remaining. Automatically triggering relay workflow...",
        "log_relay_success": "✅ Auto-relay workflow triggered successfully! Next run will start immediately.",
        "log_relay_failed": "❌ Failed to trigger auto-relay workflow ({status}): {detail}",
        "log_job_finished": "Forks synchronization and management job finished.",
        
        # Auto Relay
        "auto_relay_triggered": "⏳ **Auto-Relay Triggered**: Single run reached {minutes} min safety threshold. Next run has been automatically dispatched to sync remaining {remaining} repositories.",
    },
}

_CURRENT_LANG: Optional[str] = None


def set_language(lang: str) -> None:
    """Explicitly set current language ('zh' or 'en')."""
    global _CURRENT_LANG
    lang_clean = (lang or "zh").lower()
    if lang_clean.startswith("en"):
        _CURRENT_LANG = "en"
    else:
        _CURRENT_LANG = "zh"


def get_current_language() -> str:
    """Get current configured language code ('zh' or 'en')."""
    global _CURRENT_LANG
    if _CURRENT_LANG:
        return _CURRENT_LANG
    lang = (
        os.environ.get("LANGUAGE")
        or os.environ.get("LANG")
        or os.environ.get("LOCALE")
        or "zh"
    ).lower()
    if lang.startswith("en"):
        return "en"
    return "zh"


def t(key: str, lang: Optional[str] = None, **kwargs: Any) -> str:
    """Translate key into localized string with keyword formatting support."""
    if not lang:
        lang = get_current_language()
    messages = MESSAGES.get(lang, MESSAGES["zh"])
    template = messages.get(key, MESSAGES["zh"].get(key, key))
    if kwargs:
        try:
            return template.format(**kwargs)
        except Exception:
            return template
    return template
