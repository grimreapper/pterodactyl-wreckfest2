# Pterodactyl Wreckfest 2 dedicated-server egg

A publication-ready PTDL_v2 egg for running the Wreckfest 2 dedicated server
under Wine. This is an independent corrected packaging project and is not official Bugbear, Pterodactyl, or Pelican support.

The package uses Steam dedicated-server App ID `3519390`, writes `1203190` to
`steam_appid.txt`, runs on `ghcr.io/pelican-eggs/yolks:wine_latest`, and installs
with `ghcr.io/pelican-eggs/installers:debian`.

## Import and setup

1. In the Pterodactyl admin area, import `egg-wreckfest2.json` into the desired
   nest.
2. Create a server from the egg and assign its default allocation. The required
   game port is `30100/UDP`; publish that UDP allocation through the host
   firewall and any upstream network controls.
3. Leave the locked Steam application variables unchanged. No Steam account,
   login credential, or beta password is required.
4. Start the server. The panel considers it ready when the tailed
   `server.log` emits `Server Started`.

The egg maps the game's port to the panel's default allocation port. It does not
embed an address or substitute a fixed live allocation.

## Anonymous installation and updates

Anonymous SteamCMD installation succeeds only after forcing the Windows
platform and installing App 1007 before App 3519390. This exact order was
independently verified against build 26269859. Each SteamCMD invocation must
succeed, and installation remains failed unless both `Wreckfest2.exe` and
`steamapps/appmanifest_3519390.acf` exist afterward. The App 1007 manifest is
also required before the App 3519390 invocation begins.

The release pins the SteamCMD bootstrap archive to SHA-256
`cebf0046bfd08cf45da6bc094ae47aa39ebf4155e5ede41373b579b8f1071e7c` and
caps its download at 10 MiB. That exact archive was retrieved from the existing
HTTPS URL and measured at 2,428,561 bytes on 2026-10-31. The installer restricts
the initial request and redirects to HTTPS, then verifies the pinned digest
before extraction. If Valve changes the archive, maintainers must verify the new archive and release a new hash rather than bypassing the check.

With `AUTO_UPDATE=1`, the Wine runtime image follows the same anonymous update
order: App 1007, then App 3519390. The egg intentionally exposes no account
credentials, beta secrets, arbitrary SteamCMD flags, download URLs, shell
fragments, or startup-command overrides.

## Configuration and data paths

- `/home/container/save/server_config.scnf` is the JSON server configuration
  updated from panel variables before each start. Reinstallation never
  overwrites an existing operator copy.
- `/home/container/save` is the explicit save directory passed to the server.
- `/home/container/server.log` is reset and tailed on every launch so the panel
  can observe readiness and runtime messages.
- `/home/container/steam_appid.txt` is rewritten with `1203190` at install and
  launch time.

The repository contains a deliberately small, generic `server_config.scnf` so
the panel has a valid file to edit before the first launch.

## Panel variables

| Variable | Default | Editable | Purpose and validation |
| --- | --- | --- | --- |
| `SRCDS_APPID` | `3519390` | No, hidden | Locked dedicated-server application ID. |
| `STEAM_APPID_FILE` | `1203190` | No, hidden | Locked application ID written for the game process. |
| `WINDOWS_INSTALL` | `1` | No, hidden | Locks SteamCMD and the runtime to the Windows server payload. |
| `AUTO_UPDATE` | `1` | Yes | Boolean; anonymously updates the SDK redistributable before the game server. |
| `SERVER_NAME` | `Wreckfest 2 Server` | Yes | Required text, at most 32 characters. |
| `SERVER_DESCRIPTION` | `Welcome to Wreckfest 2!` | Yes | Required text, at most 512 characters. |
| `SERVER_PASSWORD` | empty | Yes | Optional server password, at most 32 characters. |
| `EVENT_LOOP_NAME` | `default_loop` | Yes | Required bare filename stem with no extension or path, at most 64 characters; the first character must be alphanumeric and the rest may contain only letters, digits, underscores, or hyphens. |
| `CUP_LIST` | empty | Yes | Optional alternate cup-list filename: a safe basename with an optional `.ccnl` suffix, no slash or `..`, and at most 128 characters. |
| `COUNTDOWN_TIME_MS` | `100000` | Yes | Integer countdown in milliseconds, from 30,000 through 500,000. |
| `VOTING_TIME_MS` | `20000` | Yes | Integer voting window in milliseconds, from 10,000 through 30,000. |
| `SERVER_FLAGS` | empty | Yes | Optional recognized phrases, at most 255 characters: `leader enabled`; `idle kicker disabled`; `race end timer disabled`; `event loop disabled`; `hide default user liveries`; `disable auto-admin`. Unknown tokens are silently ignored. |

## First-start generated files

The game generates `default_loop.becl` on first start. It is deliberately not
included here because it contains bundled rotation data and can change between
game builds. Let the current server build create it, stop the server cleanly,
and then edit the generated operator copy if a custom rotation is needed.

Likewise, maintain cup definitions in the first-start/operator-managed
`server_cup_config.ccnl` rather than shipping a stale generated copy. Gameplay
rotation, bot, track, and lap variables remain file/console-managed after first
start; they are intentionally not presented as stable first-start panel
variables.

## Development and release artifacts

Run the complete validation suite with:

```sh
python3 -m unittest discover -v
```

Build the deterministic release archive and its checksum with:

```sh
python3 build_artifacts.py
(cd dist && sha256sum --check SHA256SUMS)
```

Outputs are written to `dist/wreckfest2-pterodactyl-egg.zip` and
`dist/SHA256SUMS`. The archive contains packaging sources only, never downloaded
or game-generated payloads.

## Source and attribution

The install conventions and preserved MIT notice are derived from the
[pelican-eggs/games-steamcmd](https://github.com/pelican-eggs/games-steamcmd)
community project. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and
[LICENSE](LICENSE). The corrected App 1007 ordering, Wreckfest 2 configuration,
tests, and deterministic packaging in this repository are maintained
independently.
