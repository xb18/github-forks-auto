"""Unit tests for GitHub Forks Auto Sync logic."""

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from src.client import GitHubClient
from src.feishu import generate_feishu_sign, send_feishu_alert, send_feishu_card, format_stats_markdown
from src.action_disabler import disable_repo_actions
from src.syncer import (
    BranchSyncStatus,
    RepoSyncResult,
    sync_single_branch,
    sync_repository_branches,
)
from src.main import generate_step_summary, StandardLogFilter, parse_repo_list
import logging


class TestSyncLogic(unittest.TestCase):

    def setUp(self):
        self.mock_client = MagicMock(spec=GitHubClient)

    def test_feishu_signature_generation(self):
        secret = "test_secret"
        timestamp = 1600000000
        sign = generate_feishu_sign(secret, timestamp)
        self.assertTrue(isinstance(sign, str))
        self.assertTrue(len(sign) > 0)

    def test_new_branch_creation(self):
        """When branch exists in upstream but not in fork, create it."""
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        self.mock_client.post.return_value = mock_resp

        res = sync_single_branch(
            client=self.mock_client,
            fork_full_name="user/fork-repo",
            upstream_full_name="upstream/fork-repo",
            branch_name="feature-new",
            fork_sha=None,
            upstream_sha="abc1234",
        )

        self.assertEqual(res.status, BranchSyncStatus.CREATED)
        self.mock_client.post.assert_called_once_with(
            "/repos/user/fork-repo/git/refs",
            json_data={"ref": "refs/heads/feature-new", "sha": "abc1234"},
        )

    def test_up_to_date_branch(self):
        """When both fork and upstream have identical SHA, skip."""
        res = sync_single_branch(
            client=self.mock_client,
            fork_full_name="user/fork-repo",
            upstream_full_name="upstream/fork-repo",
            branch_name="main",
            fork_sha="same_sha_123",
            upstream_sha="same_sha_123",
        )

        self.assertEqual(res.status, BranchSyncStatus.UP_TO_DATE)
        self.mock_client.patch.assert_not_called()

    def test_safe_fast_forward_sync(self):
        """When upstream is ahead and behind_by == 0 (Fast-Forward), sync safely."""
        compare_resp = MagicMock()
        compare_resp.status_code = 200
        compare_resp.json.return_value = {
            "status": "ahead",
            "ahead_by": 5,
            "behind_by": 0,
        }
        self.mock_client.get.return_value = compare_resp

        patch_resp = MagicMock()
        patch_resp.status_code = 200
        self.mock_client.patch.return_value = patch_resp

        res = sync_single_branch(
            client=self.mock_client,
            fork_full_name="user/fork-repo",
            upstream_full_name="upstream/fork-repo",
            branch_name="main",
            fork_sha="old_fork_sha",
            upstream_sha="new_upstream_sha",
        )

        self.assertEqual(res.status, BranchSyncStatus.SYNCED)
        self.mock_client.patch.assert_called_once_with(
            "/repos/user/fork-repo/git/refs/heads/main",
            json_data={"sha": "new_upstream_sha", "force": False},
        )

    def test_diverged_or_force_push_prevention(self):
        """When commits diverged (e.g. upstream force-push / hard reset), DO NOT sync."""
        compare_resp = MagicMock()
        compare_resp.status_code = 200
        compare_resp.json.return_value = {
            "status": "diverged",
            "ahead_by": 3,
            "behind_by": 2,
        }
        self.mock_client.get.return_value = compare_resp

        res = sync_single_branch(
            client=self.mock_client,
            fork_full_name="user/fork-repo",
            upstream_full_name="upstream/fork-repo",
            branch_name="main",
            fork_sha="fork_sha_1",
            upstream_sha="upstream_sha_2",
        )

        self.assertEqual(res.status, BranchSyncStatus.SKIPPED_DIVERGED)
        self.mock_client.patch.assert_not_called()

    def test_fork_ahead_preservation(self):
        """When fork has local commits ahead of upstream, keep local commits."""
        compare_resp = MagicMock()
        compare_resp.status_code = 200
        compare_resp.json.return_value = {
            "status": "behind",
            "ahead_by": 0,
            "behind_by": 3,
        }
        self.mock_client.get.return_value = compare_resp

        res = sync_single_branch(
            client=self.mock_client,
            fork_full_name="user/fork-repo",
            upstream_full_name="upstream/fork-repo",
            branch_name="dev",
            fork_sha="fork_dev_sha",
            upstream_sha="upstream_dev_sha",
        )

        self.assertEqual(res.status, BranchSyncStatus.SKIPPED_FORK_AHEAD)
        self.mock_client.patch.assert_not_called()

    def test_disable_actions(self):
        """Test disabling actions on a repo."""
        # 1. First get check returns enabled: True
        get_resp = MagicMock()
        get_resp.status_code = 200
        get_resp.json.return_value = {"enabled": True}
        self.mock_client.get.return_value = get_resp

        # 2. Put response succeeds
        put_resp = MagicMock()
        put_resp.status_code = 204
        self.mock_client.put.return_value = put_resp

        ok, msg = disable_repo_actions(self.mock_client, "user/test-repo")
        self.assertTrue(ok)
        self.mock_client.put.assert_called_once_with(
            "/repos/user/test-repo/actions/permissions",
            json_data={"enabled": False},
        )

    def test_generate_step_summary_standard_mode(self):
        """Test generating markdown step summary in standard non-debug mode."""
        results = [
            RepoSyncResult(
                repo_name="user/secret-repo",
                upstream_name="upstream/secret-repo",
                actions_disabled=True,
            )
        ]
        stats = {
            "total_repos": 1,
            "synced_branches": 1,
            "created_branches": 0,
            "uptodate_branches": 0,
            "skipped_branches": 0,
            "actions_disabled_repos": 1,
            "failed": 0,
        }
        start = datetime.now(timezone.utc)
        end = datetime.now(timezone.utc)
        # Default debug_mode=False
        summary_standard = generate_step_summary(results, stats, start, end, debug_mode=False)
        self.assertIn("标准日志模式", summary_standard)
        self.assertNotIn("secret-repo", summary_standard)

        # debug_mode=True
        summary_debug = generate_step_summary(results, stats, start, end, debug_mode=True)
        self.assertIn("Debug Mode", summary_debug)
        self.assertIn("user/secret-repo", summary_debug)

    def test_standard_log_filter(self):
        """Test StandardLogFilter sanitizing names in standard mode."""
        filter_inst = StandardLogFilter()
        filter_inst.add_term("my-secret-repo")
        filter_inst.add_term("alice_user")

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="User alice_user is processing my-secret-repo now",
            args=(),
            exc_info=None,
        )

        filter_inst.filter(record)
        self.assertEqual(record.msg, "User *** is processing *** now")

    @patch("requests.post")
    def test_send_feishu_alert(self, mock_post):
        """Test sending urgent alert card to Feishu."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 0}
        mock_post.return_value = mock_resp

        ok = send_feishu_alert(
            webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/xxx",
            secret="test_secret",
            title="🚨 Test Alert",
            message="Token has expired",
        )
        self.assertTrue(ok)
        mock_post.assert_called_once()

    def test_token_expiration_401(self):
        """Test GitHubClient raising PermissionError on 401."""
        client = GitHubClient(token="expired_token")
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        client.get = MagicMock(return_value=mock_resp)

        with self.assertRaises(PermissionError) as ctx:
            client.get_authenticated_user()
        self.assertIn("已失效或已过期", str(ctx.exception))

    def test_parse_repo_list(self):
        """Test parsing comma, semicolon, space, newline delimited repo strings."""
        val = "repo1, owner/repo2; repo3\nrepo4\r\nrepo5 repo6"
        res = parse_repo_list(val)
        self.assertEqual(res, ["repo1", "owner/repo2", "repo3", "repo4", "repo5", "repo6"])

    @patch("requests.post")
    def test_send_feishu_card_pagination(self, mock_post):
        """Test splitting large warnings list across multiple Feishu cards."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 0}
        mock_post.return_value = mock_resp

        # Create 25 warning messages with batch_size=10 -> should send 3 cards (10 + 10 + 5)
        warnings = [f"Warning item #{i}" for i in range(1, 26)]
        stats = {"total_repos": 25, "synced_branches": 0, "created_branches": 0, "uptodate_branches": 0, "skipped_branches": 25}

        ok = send_feishu_card(
            webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/xxx",
            secret=None,
            title="🔄 GitHub Fork 同步完成",
            stats=stats,
            warnings=warnings,
            errors=[],
            execution_time_str="2026-08-22 10:00:00 UTC",
            batch_size=10,
        )

        self.assertTrue(ok)
        self.assertEqual(mock_post.call_count, 3)

    def test_format_stats_markdown_custom_template(self):
        """Test customizing report template by adding/removing fields."""
        custom_tpl = "**精简同步快报**\n状态: {status_emoji} {status_text}\n时间: {execution_time}\n成功: {synced_branches}\n新建: {created_branches}"
        stats = {
            "total_repos": 10,
            "synced_branches": 3,
            "created_branches": 2,
            "uptodate_branches": 5,
            "skipped_branches": 0,
            "actions_disabled_repos": 10,
            "failed": 0,
        }
        res = format_stats_markdown(stats, "2026-08-22 10:00:00 UTC", template_str=custom_tpl)
        self.assertIn("精简同步快报", res)
        self.assertIn("状态: 🟢 全部正常", res)
        self.assertIn("成功: 3", res)
        self.assertIn("新建: 2", res)
        self.assertNotIn("扫描 Fork 仓库总数", res)  # User removed this field from their custom template


if __name__ == "__main__":
    unittest.main()
