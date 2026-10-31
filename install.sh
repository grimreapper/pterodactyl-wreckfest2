#!/bin/bash
set -Eeuo pipefail

SERVER_DIR=/mnt/server
STEAMCMD_DIR="${SERVER_DIR}/steamcmd"
WORK_DIR="$(mktemp -d)"
START_TMP="${WORK_DIR}/start.sh"
CONFIG_TMP="${WORK_DIR}/server_config.scnf"
STEAMCMD_ARCHIVE="${WORK_DIR}/steamcmd_linux.tar.gz"
STEAMCMD_ARCHIVE_SHA256="cebf0046bfd08cf45da6bc094ae47aa39ebf4155e5ede41373b579b8f1071e7c"

cleanup() {
    rm -rf -- "${WORK_DIR}"
}
trap cleanup EXIT

mkdir -p "${SERVER_DIR}" "${STEAMCMD_DIR}"

curl \
    --fail \
    --location \
    --proto '=https' \
    --proto-redir '=https' \
    --show-error \
    --silent \
    --retry 5 \
    --retry-all-errors \
    --retry-delay 2 \
    --connect-timeout 20 \
    --max-time 300 \
    --max-filesize 10485760 \
    --output "${STEAMCMD_ARCHIVE}" \
    https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz

printf '%s  %s\n' "${STEAMCMD_ARCHIVE_SHA256}" "${STEAMCMD_ARCHIVE}" | sha256sum --check --status
tar --extract --gzip --file "${STEAMCMD_ARCHIVE}" --directory "${STEAMCMD_DIR}" --no-same-owner --no-same-permissions
STEAMCMD="${STEAMCMD_DIR}/steamcmd.sh"
[[ -x "${STEAMCMD}" ]] || {
    echo "SteamCMD was not installed correctly." >&2
    exit 1
}

"${STEAMCMD}" \
    +@sSteamCmdForcePlatformType windows \
    +force_install_dir "${SERVER_DIR}" \
    +login anonymous \
    +app_update 1007 validate \
    +quit

[[ -f "${SERVER_DIR}/steamapps/appmanifest_1007.acf" ]] || {
    echo "Required Steamworks SDK redistributable manifest is missing." >&2
    exit 1
}

"${STEAMCMD}" \
    +@sSteamCmdForcePlatformType windows \
    +force_install_dir "${SERVER_DIR}" \
    +login anonymous \
    +app_update 3519390 validate \
    +quit

mkdir -p "${SERVER_DIR}/.steam/sdk32" "${SERVER_DIR}/.steam/sdk64"
if [[ -f "${STEAMCMD_DIR}/linux32/steamclient.so" ]]; then
    install -m 0644 "${STEAMCMD_DIR}/linux32/steamclient.so" \
        "${SERVER_DIR}/.steam/sdk32/steamclient.so"
fi
if [[ -f "${STEAMCMD_DIR}/linux64/steamclient.so" ]]; then
    install -m 0644 "${STEAMCMD_DIR}/linux64/steamclient.so" \
        "${SERVER_DIR}/.steam/sdk64/steamclient.so"
fi

cat > "${START_TMP}" <<'WF2_START_SH'
#!/bin/bash
set -Eeuo pipefail

cd /home/container
mkdir -p save
printf '1203190\n' > steam_appid.txt

: > server.log
tail -n 0 -F server.log &
tail_pid=$!
xvfb_pid=""
wine_pid=""

cleanup() {
    local exit_status=$?
    trap - EXIT INT TERM

    for helper_pid in "${tail_pid}" "${xvfb_pid}"; do
        if [[ -n "${helper_pid}" ]] && kill -0 "${helper_pid}" 2>/dev/null; then
            kill "${helper_pid}" 2>/dev/null || true
        fi
    done
    wait "${tail_pid}" 2>/dev/null || true
    if [[ -n "${xvfb_pid}" ]]; then
        wait "${xvfb_pid}" 2>/dev/null || true
    fi
    exit "${exit_status}"
}

forward_signal() {
    if [[ -n "${wine_pid}" ]] && kill -0 "${wine_pid}" 2>/dev/null; then
        kill -TERM "${wine_pid}" 2>/dev/null || true
    fi
}

trap cleanup EXIT
trap forward_signal INT TERM

Xvfb :99 -screen 0 1024x768x24 -nolisten tcp > /tmp/wreckfest2-xvfb.log 2>&1 &
xvfb_pid=$!
export DISPLAY=:99
sleep 1
if ! kill -0 "${xvfb_pid}" 2>/dev/null; then
    echo "Xvfb failed to start." >&2
    exit 1
fi

wine ./Wreckfest2.exe --server --save-dir="$(winepath -w /home/container/save)" &
wine_pid=$!
set +e
wait "${wine_pid}"
wine_status=$?
set -e
exit "${wine_status}"
WF2_START_SH

cat > "${CONFIG_TMP}" <<'WF2_SERVER_CONFIG'
{
  "net server config": [
    {
      "name": "Wreckfest 2 Server",
      "description": "Welcome to Wreckfest 2!",
      "password": "",
      "log file name": "../server.log",
      "game port": 30100
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
          "suspend report limit": 8
        }
      ],
      "server ban durations": [
        {
          "censor duration": 1440,
          "silence duration": 1440,
          "suspend duration": 525600
        }
      ],
      "admin ban durations": [
        {
          "censor duration": 1440,
          "silence duration": 1440,
          "suspend duration": 525600
        }
      ],
      "default ban durations": [
        {
          "censor duration": 1440,
          "silence duration": 1440,
          "suspend duration": 525600
        }
      ]
    }
  ]
}
WF2_SERVER_CONFIG

install -m 0755 "${START_TMP}" "${SERVER_DIR}/start.sh"
mkdir -p "${SERVER_DIR}/save"
if [[ ! -e "${SERVER_DIR}/save/server_config.scnf" ]]; then
    install -m 0644 "${CONFIG_TMP}" "${SERVER_DIR}/save/server_config.scnf"
fi
printf '1203190\n' > "${SERVER_DIR}/steam_appid.txt"

[[ -f "${SERVER_DIR}/Wreckfest2.exe" ]] || {
    echo "Required server executable is missing." >&2
    exit 1
}
[[ -f "${SERVER_DIR}/steamapps/appmanifest_3519390.acf" ]] || {
    echo "Required Steam application manifest is missing." >&2
    exit 1
}
[[ -x "${SERVER_DIR}/start.sh" ]] || {
    echo "Runtime start script is missing or not executable." >&2
    exit 1
}
[[ -s "${SERVER_DIR}/steam_appid.txt" ]] || {
    echo "Steam application ID file is missing." >&2
    exit 1
}

echo "Installation complete: Wreckfest 2 dedicated server is ready."
