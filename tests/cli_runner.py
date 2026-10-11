"""Run the CLI in-process and capture its exit code and output."""

from bg3_newage.cli import app


def run_cli(args: list[str], capsys) -> tuple[int, str, str]:
    try:
        app(args, exit_on_error=False)
        code = 0
    except SystemExit as exc:
        code = int(exc.code or 0)
    out = capsys.readouterr()
    return code, out.out, out.err
