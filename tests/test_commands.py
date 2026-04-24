import io
import sys
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.modules.setdefault(
    "keyring",
    types.SimpleNamespace(
        get_password=lambda *args, **kwargs: None,
        set_password=lambda *args, **kwargs: None,
        delete_password=lambda *args, **kwargs: None,
    ),
)

from snow_cli.commands import _parse_and_display_output, _parse_output_lines, _wrap_script_with_output_markers


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


if __name__ == "__main__":
    unittest.main()
