from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
EGG_PATH = ROOT / "egg-wreckfest2.json"
EXPECTED_FILES = {
    ".gitignore",
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
}
EXPECTED_VARIABLES = {
    "SRCDS_APPID",
    "STEAM_APPID_FILE",
    "WINDOWS_INSTALL",
    "AUTO_UPDATE",
    "SERVER_NAME",
    "SERVER_DESCRIPTION",
    "SERVER_PASSWORD",
    "EVENT_LOOP_NAME",
    "CUP_LIST",
    "COUNTDOWN_TIME_MS",
    "VOTING_TIME_MS",
    "SERVER_FLAGS",
}
EXPECTED_MAPPINGS = {
    "net server config.0.name": "{{server.build.env.SERVER_NAME}}",
    "net server config.0.description": "{{server.build.env.SERVER_DESCRIPTION}}",
    "net server config.0.password": "{{server.build.env.SERVER_PASSWORD}}",
    "net server config.0.game port": "{{server.build.default.port}}",
    "game server config.0.event loop name": "{{server.build.env.EVENT_LOOP_NAME}}",
    "game server config.0.cup list": "{{server.build.env.CUP_LIST}}",
    "game server config.0.countdown time": "{{server.build.env.COUNTDOWN_TIME_MS}}",
    "game server config.0.voting time": "{{server.build.env.VOTING_TIME_MS}}",
    "game server config.0.flags": "{{server.build.env.SERVER_FLAGS}}",
}
RECOGNIZED_SERVER_FLAGS = (
    "leader enabled",
    "idle kicker disabled",
    "race end timer disabled",
    "event loop disabled",
    "hide default user liveries",
    "disable auto-admin",
)
STEAMCMD_ARCHIVE_SHA256 = (
    "cebf0046bfd08cf45da6bc094ae47aa39ebf4155e5ede41373b579b8f1071e7c"
)
ARCHIVE_MEMBERS = {
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
}


def load_egg() -> dict:
    return json.loads(EGG_PATH.read_text(encoding="utf-8"))


def decoded_config(egg: dict, key: str) -> object:
    value = egg["config"][key]
    if not isinstance(value, str):
        raise AssertionError(f"config.{key} must be a JSON-encoded string")
    return json.loads(value)


def variable_map(egg: dict) -> dict[str, dict]:
    return {item["env_variable"]: item for item in egg["variables"]}


def extract_heredoc(script: str, marker: str) -> str:
    pattern = re.compile(
        rf"^cat > \"\$\{{[^}}]+\}}\" <<'{re.escape(marker)}'\n"
        rf"(?P<body>.*?)^\s*{re.escape(marker)}$",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(script)
    if not match:
        raise AssertionError(f"missing quoted {marker} heredoc")
    return match.group("body")


def project_files() -> list[Path]:
    result = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or "dist" in path.parts:
            continue
        result.append(path)
    return sorted(result)


class RequiredFilesTests(unittest.TestCase):
    def test_required_files_exist(self) -> None:
        missing = sorted(name for name in EXPECTED_FILES if not (ROOT / name).is_file())
        self.assertEqual([], missing)


class EggSchemaTests(unittest.TestCase):
    def test_ptdl_v2_schema_essentials(self) -> None:
        egg = load_egg()
        self.assertEqual("PTDL_v2", egg["meta"]["version"])
        self.assertEqual("Wreckfest 2", egg["name"])
        self.assertEqual("community@example.invalid", egg["author"])
        self.assertEqual("2026-10-31T14:09:25+00:00", egg["exported_at"])
        self.assertEqual(
            {"Wine Latest": "ghcr.io/pelican-eggs/yolks:wine_latest"},
            egg["docker_images"],
        )
        self.assertEqual("bash ./start.sh", egg["startup"])
        self.assertEqual("^C", egg["config"]["stop"])

        installation = egg["scripts"]["installation"]
        self.assertEqual("ghcr.io/pelican-eggs/installers:debian", installation["container"])
        self.assertEqual("bash", installation["entrypoint"])

    def test_config_sections_are_json_encoded_strings(self) -> None:
        egg = load_egg()
        for key in ("files", "startup", "logs"):
            with self.subTest(key=key):
                self.assertIsInstance(egg["config"][key], str)
                json.loads(egg["config"][key])

        files = decoded_config(egg, "files")
        self.assertEqual({"save/server_config.scnf"}, set(files))
        self.assertEqual("json", files["save/server_config.scnf"]["parser"])
        self.assertEqual(
            EXPECTED_MAPPINGS, files["save/server_config.scnf"]["find"]
        )
        self.assertNotIn("30100", json.dumps(files))
        self.assertEqual({"done": "Server Started"}, decoded_config(egg, "startup"))
        self.assertEqual(
            {"custom": True, "location": "server.log"}, decoded_config(egg, "logs")
        )

    def test_embedded_sources_are_exact(self) -> None:
        egg = load_egg()
        install_source = (ROOT / "install.sh").read_text(encoding="utf-8")
        start_source = (ROOT / "start.sh").read_text(encoding="utf-8")
        config_source = (ROOT / "server_config.scnf").read_text(encoding="utf-8")
        self.assertEqual(install_source, egg["scripts"]["installation"]["script"])
        self.assertEqual(start_source, extract_heredoc(install_source, "WF2_START_SH"))
        self.assertEqual(config_source, extract_heredoc(install_source, "WF2_SERVER_CONFIG"))


class VariableTests(unittest.TestCase):
    def setUp(self) -> None:
        self.variables = variable_map(load_egg())

    def test_exact_safe_variable_set(self) -> None:
        self.assertEqual(EXPECTED_VARIABLES, set(self.variables))
        joined = " ".join(self.variables).lower()
        for forbidden in ("username", "password_login", "token", "url", "install_flags", "beta"):
            self.assertNotIn(forbidden, joined)

    def test_locked_variables(self) -> None:
        expected = {
            "SRCDS_APPID": ("3519390", "required|string|in:3519390"),
            "STEAM_APPID_FILE": ("1203190", "required|string|in:1203190"),
            "WINDOWS_INSTALL": ("1", "required|string|in:1"),
        }
        for name, (default, rules) in expected.items():
            with self.subTest(name=name):
                item = self.variables[name]
                self.assertEqual(default, item["default_value"])
                self.assertEqual(rules, item["rules"])
                self.assertFalse(item["user_viewable"])
                self.assertFalse(item["user_editable"])

    def test_operator_variable_defaults_and_rules(self) -> None:
        expected = {
            "AUTO_UPDATE": ("1", "required|boolean"),
            "SERVER_NAME": ("Wreckfest 2 Server", "required|string|max:32"),
            "SERVER_DESCRIPTION": ("Welcome to Wreckfest 2!", "required|string|max:512"),
            "SERVER_PASSWORD": ("", "nullable|string|max:32"),
            "EVENT_LOOP_NAME": (
                "default_loop",
                r"required|string|max:64|regex:/\A[a-zA-Z0-9][a-zA-Z0-9_-]*\z/",
            ),
            "CUP_LIST": (
                "",
                r"nullable|string|max:128|regex:/\A[a-zA-Z0-9][a-zA-Z0-9_-]*(?:\.ccnl)?\z/",
            ),
            "COUNTDOWN_TIME_MS": (
                "100000",
                "required|integer|min:30000|max:500000",
            ),
            "VOTING_TIME_MS": (
                "20000",
                "required|integer|min:10000|max:30000",
            ),
            "SERVER_FLAGS": ("", "nullable|string|max:255"),
        }
        for name, (default, rules) in expected.items():
            with self.subTest(name=name):
                item = self.variables[name]
                self.assertEqual(default, item["default_value"])
                self.assertEqual(rules, item["rules"])
                self.assertTrue(item["user_viewable"])
                self.assertTrue(item["user_editable"])

        flags_description = self.variables["SERVER_FLAGS"]["description"]
        for phrase in RECOGNIZED_SERVER_FLAGS:
            self.assertIn(phrase, flags_description)
        self.assertIn("silently ignored", flags_description.lower())

        event_loop_description = self.variables["EVENT_LOOP_NAME"]["description"]
        self.assertIn("bare filename stem", event_loop_description)
        self.assertIn("no extension or path", event_loop_description)

        cup_list_description = self.variables["CUP_LIST"]["description"]
        self.assertIn("alternate cup-list filename", cup_list_description)
        self.assertIn("optional .ccnl suffix", cup_list_description)


class SourceTests(unittest.TestCase):
    def test_sources_are_lf_only_and_shell_is_valid(self) -> None:
        for name in ("install.sh", "start.sh", "server_config.scnf"):
            with self.subTest(name=name):
                data = (ROOT / name).read_bytes()
                self.assertNotIn(b"\r", data)
                self.assertTrue(data.endswith(b"\n"))
        for name in ("install.sh", "start.sh"):
            result = subprocess.run(
                ["bash", "-n", str(ROOT / name)], capture_output=True, text=True, check=False
            )
            self.assertEqual(0, result.returncode, result.stderr)

    def test_executable_source_bits(self) -> None:
        for name in ("install.sh", "start.sh", "build_artifacts.py"):
            with self.subTest(name=name):
                mode = (ROOT / name).stat().st_mode
                self.assertTrue(mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))

                tracked = subprocess.run(
                    ["git", "ls-files", "--stage", "--", name],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout.strip()
                if tracked:
                    self.assertEqual("100755", tracked.split()[0])

    def test_installer_bootstrap_transport_and_integrity(self) -> None:
        source = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertIn("set -Eeuo pipefail", source)
        self.assertRegex(source, r"https://[^\s\"']+steamcmd_linux\.tar\.gz")
        self.assertNotIn("http://", source)
        for option in (
            "--fail",
            "--retry",
            "--retry-all-errors",
            "--retry-delay",
            "--connect-timeout",
            "--max-time",
        ):
            self.assertIn(option, source)
        self.assertRegex(source, r"(?m)^\s*--proto\s+['\"]?=https['\"]?\s*\\$")
        self.assertRegex(
            source, r"(?m)^\s*--proto-redir\s+['\"]?=https['\"]?\s*\\$"
        )
        self.assertRegex(source, r"(?m)^\s*--max-filesize\s+10485760\s*\\$")
        self.assertIn(STEAMCMD_ARCHIVE_SHA256, source)
        self.assertIn("sha256sum --check --status", source)

    def test_installer_verifies_before_safe_extraction_and_execution(self) -> None:
        source = (ROOT / "install.sh").read_text(encoding="utf-8")
        digest_at = source.index(STEAMCMD_ARCHIVE_SHA256)
        verification_at = source.index("sha256sum --check --status")
        extraction_at = source.index("tar ", verification_at)
        first_steamcmd_at = source.index('\n"${STEAMCMD}" \\\n')
        self.assertLess(digest_at, verification_at)
        self.assertLess(verification_at, extraction_at)
        self.assertLess(extraction_at, first_steamcmd_at)

        verification_line = source[verification_at : source.index("\n", verification_at)]
        self.assertNotIn("||", verification_line)
        extraction_command = source[extraction_at : source.index("\n", extraction_at)]
        self.assertIn("--no-same-owner", extraction_command)
        self.assertIn("--no-same-permissions", extraction_command)

    def test_installer_sequence_and_fail_closed_assertions(self) -> None:
        source = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertEqual(2, source.count("+login anonymous"))
        self.assertEqual(2, source.count("+@sSteamCmdForcePlatformType windows"))
        sdk_update = "+app_update 1007 validate"
        game_update = "+app_update 3519390 validate"
        self.assertLess(source.index(sdk_update), source.index(game_update))
        command_opener = '\n"${STEAMCMD}" \\\n'
        first_start = source.index(command_opener) + 1
        second_start = source.index(command_opener, first_start + 1) + 1
        first_command_end = source.index("    +quit\n", first_start) + len(
            "    +quit\n"
        )
        first_command = source[first_start:first_command_end]
        second_command = source[
            second_start : source.index('mkdir -p "${SERVER_DIR}/.steam/sdk32"')
        ]
        self.assertNotIn("||", first_command)
        self.assertNotIn("||", second_command)
        sdk_manifest = (
            '[[ -f "${SERVER_DIR}/steamapps/appmanifest_1007.acf" ]]'
        )
        self.assertIn(sdk_manifest, source)
        sdk_manifest_at = source.index(sdk_manifest)
        self.assertLess(first_command_end, sdk_manifest_at)
        self.assertLess(sdk_manifest_at, second_start)
        sdk_gate = source[sdk_manifest_at:second_start]
        self.assertIn("]] || {", sdk_gate)
        self.assertIn("exit 1", sdk_gate)
        self.assertIn('[[ -f "${SERVER_DIR}/Wreckfest2.exe" ]]', source)
        self.assertIn(
            '[[ -f "${SERVER_DIR}/steamapps/appmanifest_3519390.acf" ]]', source
        )
        self.assertIn(
            'if [[ ! -e "${SERVER_DIR}/save/server_config.scnf" ]]; then', source
        )
        self.assertIn(
            'install -m 0644 "${CONFIG_TMP}" "${SERVER_DIR}/save/server_config.scnf"',
            source,
        )
        self.assertLess(
            source.index('mkdir -p "${SERVER_DIR}/save"'),
            source.index(
                'if [[ ! -e "${SERVER_DIR}/save/server_config.scnf" ]]; then'
            ),
        )
        self.assertIn("steam_appid.txt", source)
        success_at = source.index("Installation complete")
        self.assertGreater(success_at, source.index("appmanifest_3519390.acf"))

    def test_runtime_lifecycle_and_launch(self) -> None:
        source = (ROOT / "start.sh").read_text(encoding="utf-8")
        for fragment in (
            "set -Eeuo pipefail",
            "mkdir -p save",
            ": > server.log",
            "tail -n 0 -F server.log",
            "printf '1203190\\n' > steam_appid.txt",
            "Xvfb :99",
            "export DISPLAY=:99",
            'wine ./Wreckfest2.exe --server --save-dir="$(winepath -w /home/container/save)"',
            "trap cleanup EXIT",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, source)

    def test_generic_config_template(self) -> None:
        config = json.loads((ROOT / "server_config.scnf").read_text(encoding="utf-8"))
        self.assertEqual(
            {
                "net server config": [
                    {
                        "name": "Wreckfest 2 Server",
                        "description": "Welcome to Wreckfest 2!",
                        "password": "",
                        "log file name": "../server.log",
                        "game port": 30100,
                    }
                ],
                "game server config": [
                    {
                        "cup list": "",
                        "event loop name": "default_loop",
                        "countdown time": 100000,
                        "voting time": 20000,
                        "flags": "",
                        "auto ban report limits": [
                            {
                                "censor report limit": 2,
                                "silence report limit": 4,
                                "suspend report limit": 8,
                            }
                        ],
                        "server ban durations": [
                            {
                                "censor duration": 1440,
                                "silence duration": 1440,
                                "suspend duration": 525600,
                            }
                        ],
                        "admin ban durations": [
                            {
                                "censor duration": 1440,
                                "silence duration": 1440,
                                "suspend duration": 525600,
                            }
                        ],
                        "default ban durations": [
                            {
                                "censor duration": 1440,
                                "silence duration": 1440,
                                "suspend duration": 525600,
                            }
                        ],
                    }
                ],
            },
            config,
        )


class DocumentationAndPrivacyTests(unittest.TestCase):
    def test_readme_publication_requirements(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        required_phrases = (
            "PTDL_v2",
            "30100/UDP",
            "App 1007",
            "App 3519390",
            "anonymous",
            "server_config.scnf",
            "default_loop.becl",
            "server_cup_config.ccnl",
            "file/console-managed",
            "build 26269859",
            "independent corrected packaging project",
            "not official Bugbear, Pterodactyl, or Pelican support",
            "pelican-eggs/games-steamcmd",
            "cebf0046bfd08cf45da6bc094ae47aa39ebf4155e5ede41373b579b8f1071e7c",
            "2,428,561 bytes",
            "10 MiB",
            "verify the new archive",
            "release a new hash",
            "rather than bypassing the check",
        )
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, readme)
        for variable in sorted(EXPECTED_VARIABLES):
            self.assertIn(f"`{variable}`", readme)
        self.assertIn("`/home/container/save/server_config.scnf`", readme)
        self.assertIn("at most 32 characters", readme)
        self.assertIn("at most 512 characters", readme)
        self.assertIn("from 30,000 through 500,000", readme)
        self.assertIn("from 10,000 through 30,000", readme)
        self.assertNotIn("5,000", readme)
        self.assertNotIn("600,000", readme)
        self.assertNotIn("300,000", readme)
        self.assertIn("alternate cup-list filename", readme)
        self.assertIn("silently ignored", readme)
        for phrase in RECOGNIZED_SERVER_FLAGS:
            self.assertIn(phrase, readme)
        self.assertIn("(cd dist && sha256sum --check SHA256SUMS)", readme)

    def test_license_and_attribution(self) -> None:
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("MIT License", license_text)
        self.assertIn(
            "Copyright (c) 2024 Michael Parker <parker@parkervcp.com> and Contributors",
            license_text,
        )
        self.assertIn("Permission is hereby granted, free of charge", license_text)
        notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        self.assertIn("pelican-eggs/games-steamcmd", notices)
        self.assertIn("Bugbear", notices)
        self.assertIn("not distributed", notices.lower())

    def test_no_forbidden_payload_files(self) -> None:
        forbidden_suffixes = {
            ".acf",
            ".becl",
            ".cab",
            ".ccnl",
            ".dll",
            ".exe",
            ".log",
            ".sav",
            ".save",
        }
        offenders = [
            path.relative_to(ROOT).as_posix()
            for path in project_files()
            if path.suffix.lower() in forbidden_suffixes
        ]
        self.assertEqual([], offenders)

    def test_generic_privacy_patterns_and_optional_denylist(self) -> None:
        text_files = [
            path
            for path in project_files()
            if path.suffix.lower() in {"", ".json", ".md", ".py", ".scnf", ".sh"}
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in text_files)

        ipv4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
        uuid = re.compile(
            r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
            r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
        )
        emails = set(re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", combined))
        private_domain = re.compile(r"https?://[^\s/)]+\.(?:internal|local|lan)\b", re.I)
        home_paths = {
            match.group(0)
            for match in re.finditer(r"/(?:home|Users)/[A-Za-z0-9._-]+", combined)
        }

        self.assertEqual([], ipv4.findall(combined))
        self.assertIsNone(uuid.search(combined))
        self.assertEqual(
            {"community@example.invalid", "parker@parkervcp.com"}, emails
        )
        self.assertIsNone(private_domain.search(combined))
        self.assertEqual({"/home/container"}, home_paths)

        denylist = [
            item
            for item in os.environ.get("PUBLIC_PRIVACY_DENYLIST", "").split(os.pathsep)
            if item
        ]
        for denied in denylist:
            self.assertNotIn(denied, combined)


class ArtifactTests(unittest.TestCase):
    def build(self, output: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROOT / "build_artifacts.py"), "--output-dir", str(output)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_deterministic_archive_and_checksum_integrity(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as first_raw, tempfile.TemporaryDirectory(
            dir=ROOT
        ) as second_raw:
            first = Path(first_raw)
            second = Path(second_raw)
            first_result = self.build(first)
            second_result = self.build(second)
            self.assertEqual(0, first_result.returncode, first_result.stderr)
            self.assertEqual(0, second_result.returncode, second_result.stderr)

            first_zip = first / "wreckfest2-pterodactyl-egg.zip"
            second_zip = second / "wreckfest2-pterodactyl-egg.zip"
            self.assertEqual(first_zip.read_bytes(), second_zip.read_bytes())
            digest = hashlib.sha256(first_zip.read_bytes()).hexdigest()
            self.assertEqual(
                f"{digest}  {first_zip.name}\n",
                (first / "SHA256SUMS").read_text(encoding="ascii"),
            )

            with zipfile.ZipFile(first_zip) as archive:
                self.assertEqual(ARCHIVE_MEMBERS, set(archive.namelist()))
                self.assertIsNone(archive.testzip())
                for member in archive.infolist():
                    self.assertEqual((2026, 10, 31, 14, 9, 24), member.date_time)
                    self.assertNotIn("\\", member.filename)
                for executable in ("build_artifacts.py", "install.sh", "start.sh"):
                    mode = archive.getinfo(executable).external_attr >> 16
                    self.assertTrue(mode & stat.S_IXUSR)

    def test_builder_rejects_source_drift(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as repo_raw, tempfile.TemporaryDirectory(
            dir=ROOT
        ) as out_raw:
            repo = Path(repo_raw) / "repo"
            shutil.copytree(
                ROOT,
                repo,
                ignore=shutil.ignore_patterns(
                    ".git",
                    "dist",
                    "__pycache__",
                    Path(repo_raw).name,
                    Path(out_raw).name,
                ),
            )
            with (repo / "start.sh").open("a", encoding="utf-8", newline="\n") as handle:
                handle.write("# drift\n")
            result = subprocess.run(
                [sys.executable, str(repo / "build_artifacts.py"), "--output-dir", out_raw],
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("out of sync", result.stderr.lower())


if __name__ == "__main__":
    unittest.main()
