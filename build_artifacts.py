#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import stat
import sys
import zipfile


ROOT = Path(__file__).resolve().parent
EGG_PATH = ROOT / "egg-wreckfest2.json"
ARCHIVE_NAME = "wreckfest2-pterodactyl-egg.zip"
FIXED_ZIP_TIME = (2026, 10, 31, 14, 9, 24)
ARCHIVE_FILES = (
    "LICENSE",
    "README.md",
    "THIRD_PARTY_NOTICES.md",
    "build_artifacts.py",
    "egg-wreckfest2.json",
    "install.sh",
    "server_config.scnf",
    "start.sh",
    "tests/__init__.py",
    "tests/test_egg.py",
)
EXECUTABLE_FILES = {"build_artifacts.py", "install.sh", "start.sh"}


def read_source(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def variable(
    name: str,
    description: str,
    default: str,
    rules: str,
    *,
    visible: bool = True,
    editable: bool = True,
) -> dict[str, object]:
    return {
        "name": name.replace("_", " ").title(),
        "description": description,
        "env_variable": name,
        "default_value": default,
        "user_viewable": visible,
        "user_editable": editable,
        "rules": rules,
        "field_type": "text",
    }


def egg_document() -> dict[str, object]:
    files_config = {
        "save/server_config.scnf": {
            "parser": "json",
            "find": {
                "net server config.0.name": "{{server.build.env.SERVER_NAME}}",
                "net server config.0.description": "{{server.build.env.SERVER_DESCRIPTION}}",
                "net server config.0.password": "{{server.build.env.SERVER_PASSWORD}}",
                "net server config.0.game port": "{{server.build.default.port}}",
                "game server config.0.event loop name": "{{server.build.env.EVENT_LOOP_NAME}}",
                "game server config.0.cup list": "{{server.build.env.CUP_LIST}}",
                "game server config.0.countdown time": "{{server.build.env.COUNTDOWN_TIME_MS}}",
                "game server config.0.voting time": "{{server.build.env.VOTING_TIME_MS}}",
                "game server config.0.flags": "{{server.build.env.SERVER_FLAGS}}",
            },
        }
    }
    variables = [
        variable(
            "SRCDS_APPID",
            "Locked Wreckfest 2 dedicated-server Steam application ID.",
            "3519390",
            "required|string|in:3519390",
            visible=False,
            editable=False,
        ),
        variable(
            "STEAM_APPID_FILE",
            "Locked Steam application ID written for the game process.",
            "1203190",
            "required|string|in:1203190",
            visible=False,
            editable=False,
        ),
        variable(
            "WINDOWS_INSTALL",
            "Locked switch requiring the Windows server payload for Wine.",
            "1",
            "required|string|in:1",
            visible=False,
            editable=False,
        ),
        variable(
            "AUTO_UPDATE",
            "When enabled, anonymously update App 1007 and then App 3519390 before launch.",
            "1",
            "required|boolean",
        ),
        variable(
            "SERVER_NAME",
            "Public server name; limited to 32 characters.",
            "Wreckfest 2 Server",
            "required|string|max:32",
        ),
        variable(
            "SERVER_DESCRIPTION",
            "Public server description; limited to 512 characters.",
            "Welcome to Wreckfest 2!",
            "required|string|max:512",
        ),
        variable(
            "SERVER_PASSWORD",
            "Optional join password; limited to 32 characters.",
            "",
            "nullable|string|max:32",
        ),
        variable(
            "EVENT_LOOP_NAME",
            "A bare filename stem with no extension or path: start with a letter or digit and use only letters, digits, underscores, or hyphens; maximum 64 characters.",
            "default_loop",
            r"required|string|max:64|regex:/\A[a-zA-Z0-9][a-zA-Z0-9_-]*\z/",
        ),
        variable(
            "CUP_LIST",
            "Optional alternate cup-list filename: a safe basename with an optional .ccnl suffix and no path; maximum 128 characters.",
            "",
            r"nullable|string|max:128|regex:/\A[a-zA-Z0-9][a-zA-Z0-9_-]*(?:\.ccnl)?\z/",
        ),
        variable(
            "COUNTDOWN_TIME_MS",
            "Countdown duration in milliseconds, from 30,000 through 500,000.",
            "100000",
            "required|integer|min:30000|max:500000",
        ),
        variable(
            "VOTING_TIME_MS",
            "Voting duration in milliseconds, from 10,000 through 30,000.",
            "20000",
            "required|integer|min:10000|max:30000",
        ),
        variable(
            "SERVER_FLAGS",
            "Optional recognized phrases: leader enabled; idle kicker disabled; race end timer disabled; event loop disabled; hide default user liveries; disable auto-admin. Unknown tokens are silently ignored. Limited to 255 characters.",
            "",
            "nullable|string|max:255",
        ),
    ]
    return {
        "_comment": "DO NOT EDIT: generated from the readable sources in this repository.",
        "meta": {"version": "PTDL_v2", "update_url": None},
        "exported_at": "2026-10-31T14:09:25+00:00",
        "name": "Wreckfest 2",
        "author": "community@example.invalid",
        "description": "Wreckfest 2 dedicated server under Wine with anonymous SteamCMD installation.",
        "features": None,
        "docker_images": {"Wine Latest": "ghcr.io/pelican-eggs/yolks:wine_latest"},
        "file_denylist": [],
        "startup": "bash ./start.sh",
        "config": {
            "files": json.dumps(files_config, separators=(",", ":")),
            "startup": json.dumps({"done": "Server Started"}, separators=(",", ":")),
            "logs": json.dumps(
                {"custom": True, "location": "server.log"}, separators=(",", ":")
            ),
            "stop": "^C",
        },
        "scripts": {
            "installation": {
                "script": read_source("install.sh"),
                "container": "ghcr.io/pelican-eggs/installers:debian",
                "entrypoint": "bash",
            }
        },
        "variables": variables,
    }


def rendered_egg() -> str:
    return json.dumps(egg_document(), indent=4, ensure_ascii=False) + "\n"


def extract_heredoc(source: str, marker: str) -> str:
    opener = f"<<'{marker}'\n"
    try:
        body_start = source.index(opener) + len(opener)
        body_end = source.index(f"\n{marker}\n", body_start) + 1
    except ValueError as error:
        raise ValueError(f"missing quoted {marker} heredoc") from error
    return source[body_start:body_end]


def validate_sources() -> None:
    expected_egg = rendered_egg()
    if not EGG_PATH.is_file() or EGG_PATH.read_text(encoding="utf-8") != expected_egg:
        raise ValueError("egg-wreckfest2.json is out of sync; run build_artifacts.py --sync-egg")

    install_source = read_source("install.sh")
    if extract_heredoc(install_source, "WF2_START_SH") != read_source("start.sh"):
        raise ValueError("start.sh is out of sync with install.sh")
    if extract_heredoc(install_source, "WF2_SERVER_CONFIG") != read_source(
        "server_config.scnf"
    ):
        raise ValueError("server_config.scnf is out of sync with install.sh")

    for name in ARCHIVE_FILES:
        path = ROOT / name
        if not path.is_file():
            raise ValueError(f"required archive source is missing: {name}")
        if b"\r" in path.read_bytes():
            raise ValueError(f"CRLF content is not permitted: {name}")


def write_egg() -> None:
    EGG_PATH.write_text(rendered_egg(), encoding="utf-8", newline="\n")


def write_archive(output_dir: Path) -> tuple[Path, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / ARCHIVE_NAME
    with zipfile.ZipFile(
        archive_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        strict_timestamps=True,
    ) as archive:
        for name in ARCHIVE_FILES:
            data = (ROOT / name).read_bytes()
            info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_TIME)
            info.create_system = 3
            permissions = 0o755 if name in EXECUTABLE_FILES else 0o644
            info.external_attr = (stat.S_IFREG | permissions) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)

    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    checksum_path = output_dir / "SHA256SUMS"
    checksum_path.write_text(f"{digest}  {ARCHIVE_NAME}\n", encoding="ascii", newline="\n")
    return archive_path, digest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "dist",
        help="artifact output directory (default: ./dist)",
    )
    parser.add_argument(
        "--sync-egg",
        action="store_true",
        help="regenerate egg-wreckfest2.json from the readable source files",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.sync_egg:
            write_egg()
        validate_sources()
        archive_path, digest = write_archive(args.output_dir)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"created {archive_path}")
    print(f"sha256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
