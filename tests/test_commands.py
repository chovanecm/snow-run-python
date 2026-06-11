import io
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

keyring_stub = types.SimpleNamespace(
    get_password=lambda *args, **kwargs: None,
    set_password=lambda *args, **kwargs: None,
    delete_password=lambda *args, **kwargs: None,
)

sys.modules.setdefault(
    "keyring",
    keyring_stub,
)

from click.testing import CliRunner

from snow_cli import cli as cli_module
from snow_cli.commands import _parse_and_display_output, _parse_output_lines, _wrap_script_with_output_markers, run_script
from snow_cli.session import ScriptTokenError


class DummyConfig:
    def __init__(self, tmp_path):
        self.instance = "dev1234.service-now.com"
        self._tmp_dir = Path(tmp_path)

    def ensure_instance_set(self):
        return None

    @property
    def tmp_dir(self):
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        return self._tmp_dir

    @property
    def cookie_file(self):
        return self.tmp_dir / "cookies.txt"


class CliAliasParity(unittest.TestCase):
    """Verify that record/r aliases are functionally identical."""

    def test_r_search_forwards_all_options(self):
        runner = CliRunner()
        fake_search = Mock(return_value=0)
        with patch.dict(sys.modules, {"keyring": keyring_stub}), \
             patch("snow_cli.cli.search_records", fake_search), \
             patch.object(cli_module.sys, "exit", side_effect=SystemExit):
            result = runner.invoke(
                cli_module.main,
                ["r", "search", "-q", "active=true", "-f", "sys_id,number",
                 "-l", "5", "incident"],
            )
        self.assertEqual(result.exit_code, 0)
        kw = fake_search.call_args.kwargs
        self.assertEqual(kw["query"], "active=true")
        self.assertEqual(kw["fields"], "sys_id,number")
        self.assertEqual(kw["limit"], 5)
        self.assertEqual(kw["table"], "incident")

    def test_r_count_forwards_query(self):
        runner = CliRunner()
        fake_count = Mock(return_value=0)
        with patch.dict(sys.modules, {"keyring": keyring_stub}), \
             patch("snow_cli.cli.count_records", fake_count), \
             patch.object(cli_module.sys, "exit", side_effect=SystemExit):
            result = runner.invoke(
                cli_module.main,
                ["r", "count", "-q", "active=true", "incident"],
            )
        self.assertEqual(result.exit_code, 0)
        # count_records is called as: count_records(config, table, query=query)
        self.assertEqual(fake_count.call_args.args[1], "incident")
        self.assertEqual(fake_count.call_args.kwargs.get("query"), "active=true")


class ParseOutputLinesTests(unittest.TestCase):
    def test_marker_bounded_stdout_routes_outer_noise_to_stderr(self):
        start_marker = "__SNOW_RUN_START_token__"
        end_marker = "__SNOW_RUN_END_token__"
        html_response = (
            "<PRE>"
            "*** Script: bootstrap debug<BR/>"
            f"*** Script: {start_marker}<BR/>"
            "*** Script: hello<BR/>"
            "*** Script: world<BR/>"
            f"*** Script: {end_marker}<BR/>"
            "*** Script: trailing debug<BR/>"
            "JavaException: boom"
            "</PRE>"
        )

        stdout_lines, stderr_lines = _parse_output_lines(
            html_response,
            start_marker=start_marker,
            end_marker=end_marker,
        )

        self.assertEqual(stdout_lines, ["hello", "world"])
        self.assertEqual(
            stderr_lines,
            ["bootstrap debug", "trailing debug", "JavaException: boom"],
        )

    def test_missing_end_marker_keeps_best_effort_stdout_and_warns(self):
        start_marker = "__SNOW_RUN_START_token__"
        end_marker = "__SNOW_RUN_END_token__"
        html_response = (
            "<PRE>"
            "*** Script: setup noise<BR/>"
            f"*** Script: {start_marker}<BR/>"
            "*** Script: useful output<BR/>"
            "Script execution failed"
            "</PRE>"
        )

        stdout_lines, stderr_lines = _parse_output_lines(
            html_response,
            start_marker=start_marker,
            end_marker=end_marker,
        )

        self.assertEqual(stdout_lines, ["useful output"])
        self.assertEqual(
            stderr_lines,
            [
                "setup noise",
                "Script execution failed",
                "Warning: ServiceNow output end marker was not found; showing best-effort stdout.",
            ],
        )

    def test_without_markers_parser_preserves_best_effort_stdout(self):
        html_response = "<PRE>*** Script: plain output<BR/>Some warning</PRE>"

        stdout_lines, stderr_lines = _parse_output_lines(html_response)

        self.assertEqual(stdout_lines, ["plain output"])
        self.assertEqual(stderr_lines, ["Some warning"])

    def test_parse_and_display_output_sends_streams_to_matching_destinations(self):
        start_marker = "__SNOW_RUN_START_token__"
        end_marker = "__SNOW_RUN_END_token__"
        html_response = (
            "<PRE>"
            "*** Script: preface<BR/>"
            f"*** Script: {start_marker}<BR/>"
            "*** Script: final output<BR/>"
            f"*** Script: {end_marker}<BR/>"
            "stacktrace line"
            "</PRE>"
        )

        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()

        with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
            _parse_and_display_output(
                html_response,
                start_marker=start_marker,
                end_marker=end_marker,
            )

        self.assertEqual(stdout_buffer.getvalue(), "final output\n")
        self.assertEqual(stderr_buffer.getvalue(), "preface\nstacktrace line\n")


class WrapScriptWithMarkersTests(unittest.TestCase):
    def test_wrapper_surrounds_script_with_both_markers(self):
        wrapped_script = _wrap_script_with_output_markers(
            "gs.print('hello');",
            "__SNOW_RUN_START_token__",
            "__SNOW_RUN_END_token__",
        )

        self.assertIn('gs.print("__SNOW_RUN_START_token__");', wrapped_script)
        self.assertIn("gs.print('hello');", wrapped_script)
        self.assertIn('gs.print("__SNOW_RUN_END_token__");', wrapped_script)


class RunScriptAutoLoginTests(unittest.TestCase):
    def test_auto_login_retries_token_failure_once(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = DummyConfig(tmp_dir)
            first_session = Mock()
            second_session = Mock()
            first_session.get_script_token.side_effect = ScriptTokenError(
                "Cannot get security token for dev1234.service-now.com. Try logging in again (snow login)"
            )
            second_session.get_script_token.return_value = "token-123"
            second_session.post.return_value = types.SimpleNamespace(status_code=200, text="<PRE></PRE>")

            login_mock = Mock(side_effect=lambda cfg: print(f"Successfully logged in to {cfg.instance}") or 0)
            elevate_mock = Mock(side_effect=lambda cfg: print(f"Successfully elevated privileges on {cfg.instance}") or 0)
            parse_mock = Mock()

            stdout_buffer = io.StringIO()
            stderr_buffer = io.StringIO()

            with patch("snow_cli.commands.SnowSession", side_effect=[first_session, second_session]), \
                 patch("snow_cli.commands.login", login_mock), \
                 patch("snow_cli.commands.elevate", elevate_mock), \
                 patch("snow_cli.commands._generate_output_markers", return_value=("START", "END")), \
                 patch("snow_cli.commands._parse_and_display_output", parse_mock):
                with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                    exit_code = run_script(config, script_content="gs.print('Hello');", auto_login=True)

            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout_buffer.getvalue(), "")
            self.assertIn("Cannot get security token for dev1234.service-now.com.", stderr_buffer.getvalue())
            self.assertIn("Successfully logged in to dev1234.service-now.com", stderr_buffer.getvalue())
            self.assertIn("Successfully elevated privileges on dev1234.service-now.com", stderr_buffer.getvalue())
            self.assertEqual(login_mock.call_count, 1)
            self.assertEqual(elevate_mock.call_count, 1)
            self.assertEqual(parse_mock.call_count, 1)
            self.assertEqual(second_session.post.call_count, 1)
            self.assertIn('gs.print("START");', second_session.post.call_args.kwargs["data"]["script"])
            self.assertIn("gs.print('Hello');", second_session.post.call_args.kwargs["data"]["script"])
            self.assertIn('gs.print("END");', second_session.post.call_args.kwargs["data"]["script"])

    def test_auto_login_reports_second_token_failure(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = DummyConfig(tmp_dir)
            first_session = Mock()
            second_session = Mock()
            token_error = ScriptTokenError(
                "Cannot get security token for dev1234.service-now.com. Try logging in again (snow login)"
            )
            first_session.get_script_token.side_effect = token_error
            second_session.get_script_token.side_effect = token_error

            login_mock = Mock(side_effect=lambda cfg: print(f"Successfully logged in to {cfg.instance}") or 0)
            elevate_mock = Mock(side_effect=lambda cfg: print(f"Successfully elevated privileges on {cfg.instance}") or 0)
            parse_mock = Mock()

            stdout_buffer = io.StringIO()
            stderr_buffer = io.StringIO()

            with patch("snow_cli.commands.SnowSession", side_effect=[first_session, second_session]), \
                 patch("snow_cli.commands.login", login_mock), \
                 patch("snow_cli.commands.elevate", elevate_mock), \
                 patch("snow_cli.commands._parse_and_display_output", parse_mock):
                with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                    exit_code = run_script(config, script_content="gs.print('Hello');", auto_login=True)

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout_buffer.getvalue(), "")
            self.assertEqual(login_mock.call_count, 1)
            self.assertEqual(elevate_mock.call_count, 1)
            self.assertEqual(parse_mock.call_count, 0)
            self.assertIn("Cannot get security token for dev1234.service-now.com.", stderr_buffer.getvalue())
            self.assertIn("Script execution error: Cannot get security token for dev1234.service-now.com.", stderr_buffer.getvalue())

    def test_auto_login_stops_when_login_fails(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = DummyConfig(tmp_dir)
            first_session = Mock()
            first_session.get_script_token.side_effect = ScriptTokenError(
                "Cannot get security token for dev1234.service-now.com. Try logging in again (snow login)"
            )

            login_mock = Mock(side_effect=lambda cfg: print("Login failed with status code: 401") or 1)
            elevate_mock = Mock()

            stdout_buffer = io.StringIO()
            stderr_buffer = io.StringIO()

            with patch("snow_cli.commands.SnowSession", return_value=first_session), \
                 patch("snow_cli.commands.login", login_mock), \
                 patch("snow_cli.commands.elevate", elevate_mock):
                with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                    exit_code = run_script(config, script_content="gs.print('Hello');", auto_login=True)

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout_buffer.getvalue(), "")
            self.assertEqual(login_mock.call_count, 1)
            self.assertEqual(elevate_mock.call_count, 0)
            self.assertIn("Login failed with status code: 401", stderr_buffer.getvalue())


class CliRunCommandTests(unittest.TestCase):
    def test_run_command_passes_auto_login_flag(self):
        runner = CliRunner()
        fake_run_script = Mock(return_value=0)

        with patch.dict(sys.modules, {"keyring": keyring_stub}), \
             patch("snow_cli.cli.run_script", fake_run_script), \
             patch.object(cli_module.sys, "exit", side_effect=SystemExit) as exit_mock:
            result = runner.invoke(cli_module.main, ["run", "--auto-login", "-"], input="gs.print('Hello');")

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(fake_run_script.call_count, 1)
        self.assertEqual(fake_run_script.call_args.args[1], "-")
        self.assertTrue(fake_run_script.call_args.kwargs["auto_login"])
        self.assertEqual(exit_mock.call_count, 1)


class FetchAggregateRecordsTests(unittest.TestCase):
    """Tests for _fetch_aggregate_records result-flattening logic."""

    def _mock_response(self, payload, status=200):
        resp = Mock()
        resp.status_code = status
        resp.json.return_value = payload
        resp.text = str(payload)
        return resp

    def test_count_only_no_groupby_returns_single_row(self):
        from snow_cli.commands import _fetch_aggregate_records

        payload = {"result": {"stats": {"count": "42"}}}
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = DummyConfig(tmp_dir)
            config.user = "u"
            config.password = "p"
            with patch("requests.get", return_value=self._mock_response(payload)):
                rows = _fetch_aggregate_records(config, "incident", count=True)
        self.assertEqual(rows, [{"count": "42"}])

    def test_groupby_results_are_flattened(self):
        from snow_cli.commands import _fetch_aggregate_records

        payload = {
            "result": [
                {
                    "groupby_fields": [
                        {"field": "priority", "value": "1", "display_value": "1 - Critical"}
                    ],
                    "stats": {"count": "5"},
                },
                {
                    "groupby_fields": [
                        {"field": "priority", "value": "2", "display_value": "2 - High"}
                    ],
                    "stats": {"count": "12"},
                },
            ]
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = DummyConfig(tmp_dir)
            config.user = "u"
            config.password = "p"
            with patch("requests.get", return_value=self._mock_response(payload)):
                rows = _fetch_aggregate_records(config, "incident", count=True, group_by=["priority"])
        self.assertEqual(len(rows), 2)
        self.assertIn("priority", rows[0])
        self.assertIn("count", rows[0])
        # display_values="both" default: show "display (value)" when they differ
        self.assertEqual(rows[0]["priority"], "1 - Critical (1)")
        self.assertEqual(rows[0]["count"], "5")

    def test_http_error_raises_runtime_error(self):
        from snow_cli.commands import _fetch_aggregate_records

        with tempfile.TemporaryDirectory() as tmp_dir:
            config = DummyConfig(tmp_dir)
            config.user = "u"
            config.password = "p"
            with patch("requests.get", return_value=self._mock_response({}, status=403)):
                with self.assertRaises(RuntimeError) as ctx:
                    _fetch_aggregate_records(config, "incident", count=True)
        self.assertIn("403", str(ctx.exception))


class AggregateRecordsCliTests(unittest.TestCase):
    """Tests for aggregate_records() function (CLI entry point)."""

    def _make_config(self, tmp_dir):
        config = DummyConfig(tmp_dir)
        config.user = "u"
        config.password = "p"
        config.ensure_credentials_set = lambda: None
        return config

    def test_no_aggregate_function_returns_exit_1(self):
        from snow_cli.commands import aggregate_records

        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self._make_config(tmp_dir)
            buf = io.StringIO()
            with redirect_stderr(buf):
                code = aggregate_records(config, "incident")
        self.assertEqual(code, 1)
        self.assertIn("At least one aggregate function", buf.getvalue())

    def test_count_with_groupby_prints_table(self):
        from snow_cli.commands import aggregate_records

        payload = {
            "result": [
                {
                    "groupby_fields": [{"field": "state", "value": "1", "display_value": "New"}],
                    "stats": {"count": "7"},
                }
            ]
        }
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = payload

        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self._make_config(tmp_dir)
            out = io.StringIO()
            with patch("requests.get", return_value=mock_resp):
                with redirect_stdout(out):
                    code = aggregate_records(
                        config, "incident", count=True, group_by=["state"], fmt="json"
                    )
        self.assertEqual(code, 0)
        import json as _json
        data = _json.loads(out.getvalue())
        self.assertEqual(len(data), 1)
        self.assertIn("state", data[0])
        self.assertIn("count", data[0])
        self.assertEqual(data[0]["count"], "7")

    def test_json_format_outputs_valid_json(self):
        from snow_cli.commands import aggregate_records
        import json as _json

        payload = {"result": {"stats": {"count": "99"}}}
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = payload

        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self._make_config(tmp_dir)
            out = io.StringIO()
            with patch("requests.get", return_value=mock_resp):
                with redirect_stdout(out):
                    code = aggregate_records(config, "incident", count=True, fmt="json")
        self.assertEqual(code, 0)
        data = _json.loads(out.getvalue())
        self.assertIsInstance(data, list)
        self.assertEqual(data[0]["count"], "99")


class CliAggregateCommandTests(unittest.TestCase):
    """Integration tests for the CLI aggregate commands via CliRunner."""

    def test_record_aggregate_count_groupby(self):
        runner = CliRunner()
        fake_aggregate = Mock(return_value=0)

        with patch.dict(sys.modules, {"keyring": keyring_stub}), \
             patch("snow_cli.cli.aggregate_records", fake_aggregate), \
             patch.object(cli_module.sys, "exit", side_effect=SystemExit) as exit_mock:
            result = runner.invoke(
                cli_module.main,
                ["record", "aggregate", "--count", "-g", "priority", "incident"],
            )

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(fake_aggregate.call_count, 1)
        call_kwargs = fake_aggregate.call_args.kwargs
        self.assertTrue(call_kwargs["count"])
        self.assertEqual(call_kwargs["group_by"], ["priority"])
        self.assertEqual(call_kwargs["table"], "incident")

    def test_r_a_alias_works(self):
        runner = CliRunner()
        fake_aggregate = Mock(return_value=0)

        with patch.dict(sys.modules, {"keyring": keyring_stub}), \
             patch("snow_cli.cli.aggregate_records", fake_aggregate), \
             patch.object(cli_module.sys, "exit", side_effect=SystemExit):
            result = runner.invoke(
                cli_module.main,
                ["r", "a", "--count", "incident"],
            )

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(fake_aggregate.call_count, 1)
        self.assertTrue(fake_aggregate.call_args.kwargs["count"])

    def test_avg_sum_min_max_options_forwarded(self):
        runner = CliRunner()
        fake_aggregate = Mock(return_value=0)

        with patch.dict(sys.modules, {"keyring": keyring_stub}), \
             patch("snow_cli.cli.aggregate_records", fake_aggregate), \
             patch.object(cli_module.sys, "exit", side_effect=SystemExit):
            result = runner.invoke(
                cli_module.main,
                [
                    "record", "aggregate",
                    "--avg", "reassignment_count",
                    "--sum", "business_duration",
                    "--min", "opened_at",
                    "--max", "closed_at",
                    "incident",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        kw = fake_aggregate.call_args.kwargs
        self.assertEqual(kw["avg"], ["reassignment_count"])
        self.assertEqual(kw["sum_fields"], ["business_duration"])
        self.assertEqual(kw["min_fields"], ["opened_at"])
        self.assertEqual(kw["max_fields"], ["closed_at"])

    def test_missing_aggregate_function_exits_1(self):
        runner = CliRunner()

        with patch.dict(sys.modules, {"keyring": keyring_stub}), \
             patch("snow_cli.cli.aggregate_records") as fake_aggregate:
            # aggregate_records returns 1 (validation error) when no agg fn given
            fake_aggregate.return_value = 1
            result = runner.invoke(
                cli_module.main,
                ["record", "aggregate", "incident"],
            )

        self.assertEqual(result.exit_code, 1)


class FetchRecordsPaginationTests(unittest.TestCase):
    """Unit tests for _fetch_records() pagination logic."""

    def _make_config(self, tmp_dir):
        config = DummyConfig(tmp_dir)
        config.user = "u"
        config.password = "p"
        return config

    def _mock_get(self, pages, link_next_on_pages=None):
        """Return mock responses for successive page fetches.

        *link_next_on_pages* is an optional set of 0-based page indices that
        should include a ``Link: rel="next"`` header. All other pages get an
        empty Link header (signals last page).
        """
        link_next_on_pages = set(link_next_on_pages or [])
        responses = []
        for idx, page_records in enumerate(pages):
            mock = Mock()
            mock.status_code = 200
            mock.json.return_value = {"result": page_records}
            if idx in link_next_on_pages:
                mock.headers.get.return_value = '<...>;rel="next"'
            else:
                mock.headers.get.return_value = ""
            responses.append(mock)
        return responses

    def test_single_page_no_pagination_needed(self):
        """When the result fits in one page, only one request is made."""
        from snow_cli.commands import _fetch_records

        records = [{"sys_id": {"value": str(i), "display_value": str(i)}} for i in range(10)]
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self._make_config(tmp_dir)
            with patch("requests.get", side_effect=self._mock_get([records])) as mock_get:
                result = _fetch_records(config, "incident")

        self.assertEqual(len(result), 10)
        self.assertEqual(mock_get.call_count, 1)

    def test_two_pages_are_combined(self):
        """When the first page is full, a second request is made for the remainder."""
        from snow_cli.commands import _fetch_records, _DEFAULT_PAGE_SIZE

        page1 = [{"sys_id": {"value": str(i)}} for i in range(_DEFAULT_PAGE_SIZE)]
        page2 = [{"sys_id": {"value": str(i)}} for i in range(5)]
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self._make_config(tmp_dir)
            with patch("requests.get", side_effect=self._mock_get([page1, page2])) as mock_get:
                result = _fetch_records(config, "incident")

        self.assertEqual(len(result), _DEFAULT_PAGE_SIZE + 5)
        self.assertEqual(mock_get.call_count, 2)

    def test_limit_within_first_page(self):
        """When limit <= page_size, only one request is made."""
        from snow_cli.commands import _fetch_records

        page1 = [{"sys_id": {"value": str(i)}} for i in range(50)]
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self._make_config(tmp_dir)
            with patch("requests.get", side_effect=self._mock_get([page1])) as mock_get:
                result = _fetch_records(config, "incident", limit=50)

        self.assertEqual(len(result), 50)
        self.assertEqual(mock_get.call_count, 1)

    def test_zero_limit_returns_empty_without_request(self):
        """When limit is zero, no request is made."""
        from snow_cli.commands import _fetch_records

        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self._make_config(tmp_dir)
            with patch("requests.get") as mock_get:
                result = _fetch_records(config, "incident", limit=0)

        self.assertEqual(result, [])
        self.assertEqual(mock_get.call_count, 0)

    def test_limit_spanning_two_pages(self):
        """When limit > page_size, two requests are made and result is capped at limit."""
        from snow_cli.commands import _fetch_records, _DEFAULT_PAGE_SIZE

        limit = _DEFAULT_PAGE_SIZE + 200
        page1 = [{"sys_id": {"value": str(i)}} for i in range(_DEFAULT_PAGE_SIZE)]
        page2 = [{"sys_id": {"value": str(i)}} for i in range(200)]
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self._make_config(tmp_dir)
            with patch("requests.get", side_effect=self._mock_get([page1, page2])) as mock_get:
                result = _fetch_records(config, "incident", limit=limit)

        self.assertEqual(len(result), limit)
        self.assertEqual(mock_get.call_count, 2)

    def test_empty_table_returns_empty_list(self):
        """An empty result on the first page returns an empty list."""
        from snow_cli.commands import _fetch_records

        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self._make_config(tmp_dir)
            with patch("requests.get", side_effect=self._mock_get([[]])) as mock_get:
                result = _fetch_records(config, "incident")

        self.assertEqual(result, [])
        self.assertEqual(mock_get.call_count, 1)

    def test_http_error_raises_runtime_error(self):
        """A non-200 response raises RuntimeError with the status code."""
        from snow_cli.commands import _fetch_records

        mock_resp = Mock()
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden"
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self._make_config(tmp_dir)
            with patch("requests.get", return_value=mock_resp):
                with self.assertRaises(RuntimeError) as ctx:
                    _fetch_records(config, "incident")

        self.assertIn("403", str(ctx.exception))

    def test_offset_increments_correctly(self):
        """Verify sysparm_offset is incremented by page_size on subsequent requests."""
        from snow_cli.commands import _fetch_records, _DEFAULT_PAGE_SIZE

        page1 = [{"sys_id": {"value": str(i)}} for i in range(_DEFAULT_PAGE_SIZE)]
        page2 = [{"sys_id": {"value": str(i)}} for i in range(3)]
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self._make_config(tmp_dir)
            with patch("requests.get", side_effect=self._mock_get([page1, page2])) as mock_get:
                _fetch_records(config, "incident")

        first_call_params = mock_get.call_args_list[0].kwargs["params"]
        second_call_params = mock_get.call_args_list[1].kwargs["params"]
        self.assertEqual(first_call_params["sysparm_offset"], "0")
        self.assertEqual(second_call_params["sysparm_offset"], str(_DEFAULT_PAGE_SIZE))

    def test_link_next_header_overrides_size_heuristic(self):
        """When ACL filtering returns fewer records than page_size but Link header
        says rel=next, pagination continues to the next page."""
        from snow_cli.commands import _fetch_records, _DEFAULT_PAGE_SIZE

        # Simulate ACL-filtered pages: each returns fewer than page_size records,
        # but Link header says there are more pages.
        page1 = [{"sys_id": {"value": str(i)}} for i in range(996)]   # < 1000, but has next
        page2 = [{"sys_id": {"value": str(i)}} for i in range(200)]   # last page (no next)
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = self._make_config(tmp_dir)
            # Only page index 0 gets rel=next; page 1 does not.
            mocks = self._mock_get([page1, page2], link_next_on_pages={0})
            with patch("requests.get", side_effect=mocks) as mock_get:
                result = _fetch_records(config, "incident")

        self.assertEqual(len(result), 996 + 200)
        self.assertEqual(mock_get.call_count, 2)


class OutputFormatterRegistryTests(unittest.TestCase):
    def test_formatters_dict_exists_and_covers_all_format_choices(self):
        from snow_cli.commands import FORMAT_CHOICES, _FORMATTERS
        self.assertEqual(set(FORMAT_CHOICES), set(_FORMATTERS.keys()))

    def test_format_choices_contains_all_expected_formats(self):
        from snow_cli.commands import FORMAT_CHOICES
        for fmt in ("table", "tsv", "csv", "json", "xml", "excel"):
            self.assertIn(fmt, FORMAT_CHOICES)


if __name__ == "__main__":
    unittest.main()
