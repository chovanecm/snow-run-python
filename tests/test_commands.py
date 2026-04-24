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


if __name__ == "__main__":
    unittest.main()
