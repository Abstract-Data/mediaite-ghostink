from forensics.cli import build_parser


def test_cli_accepts_all_stage_commands() -> None:
    parser = build_parser()
    for command in ("scrape", "extract", "analyze", "report", "all"):
        parsed = parser.parse_args([command])
        assert parsed.command == command
