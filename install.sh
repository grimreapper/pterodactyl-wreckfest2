#!/bin/bash
set -Eeuo pipefail

SERVER_DIR=/mnt/server
WORK_DIR=""
STEAMCMD_ARCHIVE_SHA256="cebf0046bfd08cf45da6bc094ae47aa39ebf4155e5ede41373b579b8f1071e7c"
STEAMCMD_ARCHIVE_SIZE="2428561"

cleanup() {
    if [[ -n "${WORK_DIR}" ]]; then
        rm -rf -- "${WORK_DIR}"
    fi
}

ensure_real_directory() {
    local path="$1"

    if [[ -L "${path}" ]]; then
        echo "Refusing symlinked directory path: ${path}" >&2
        return 1
    fi
    if [[ ! -e "${path}" ]]; then
        mkdir -- "${path}"
    fi
    [[ -d "${path}" && ! -L "${path}" ]] || {
        echo "Required directory path is unsafe: ${path}" >&2
        return 1
    }
}

prepare_regular_destination() {
    local path="$1"

    if [[ -L "${path}" || ( -e "${path}" && ! -f "${path}" ) ]]; then
        echo "Refusing unsafe file destination: ${path}" >&2
        return 1
    fi
}

require_regular_file() {
    local path="$1"
    local description="$2"

    [[ -f "${path}" && ! -L "${path}" && -s "${path}" && -r "${path}" ]] || {
        echo "${description} is missing, empty, unreadable, or unsafe." >&2
        return 1
    }
}

require_complete_manifest() {
    local manifest_path="$1"
    local expected_app_id="$2"

    require_regular_file "${manifest_path}" "Required Steam manifest for App ${expected_app_id}"

    LC_ALL=C awk -v expected_app_id="${expected_app_id}" '
        function record_key(key, value, normalized) {
            normalized = tolower(key)
            if (normalized == "appid") {
                app_id_total++
                if (depth == 1) {
                    app_id_top++
                    app_id_value = value
                }
            } else if (normalized == "stateflags") {
                state_flags_total++
                if (depth == 1) {
                    state_flags_top++
                    state_flags_value = value
                }
            }
        }
        function string_token(value, key) {
            if (finished || invalid) {
                invalid = 1
                return
            }
            if (!pending) {
                pending_key = value
                pending = 1
                return
            }
            key = pending_key
            pending_key = ""
            pending = 0
            if (depth == 0) {
                invalid = 1
                return
            }
            record_key(key, value)
        }
        function open_object(key) {
            if (finished || invalid || !pending) {
                invalid = 1
                return
            }
            key = pending_key
            pending_key = ""
            pending = 0
            record_key(key, "")
            if (depth == 0) {
                if (root_seen || tolower(key) != "appstate") {
                    invalid = 1
                    return
                }
                root_seen = 1
            }
            depth++
        }
        function close_object() {
            if (invalid || pending || depth <= 0) {
                invalid = 1
                return
            }
            depth--
            if (depth == 0) finished = 1
        }
        BEGIN {
            depth = 0
            pending_key = ""
            pending = 0
            root_seen = 0
            finished = 0
            invalid = 0
            app_id_total = 0
            app_id_top = 0
            app_id_value = ""
            state_flags_total = 0
            state_flags_top = 0
            state_flags_value = ""
        }
        {
            line = $0
            line_length = length(line)
            line_index = 1
            while (line_index <= line_length && !invalid) {
                character = substr(line, line_index, 1)
                next_character = substr(line, line_index + 1, 1)
                if (character ~ /[[:space:]]/) {
                    line_index++
                } else if (character == "/" && next_character == "/") {
                    break
                } else if (character == "{") {
                    open_object()
                    line_index++
                } else if (character == "}") {
                    close_object()
                    line_index++
                } else if (character == "\"") {
                    value = ""
                    closed_quote = 0
                    line_index++
                    while (line_index <= line_length) {
                        character = substr(line, line_index, 1)
                        if (character == "\\") {
                            line_index++
                            if (line_index > line_length) {
                                invalid = 1
                                break
                            }
                            escaped = substr(line, line_index, 1)
                            if (escaped == "\"" || escaped == "\\") {
                                value = value escaped
                            } else if (escaped == "n") {
                                value = value "\n"
                            } else if (escaped == "t") {
                                value = value "\t"
                            } else {
                                invalid = 1
                                break
                            }
                            line_index++
                        } else if (character == "\"") {
                            closed_quote = 1
                            line_index++
                            break
                        } else {
                            value = value character
                            line_index++
                        }
                    }
                    if (!closed_quote) invalid = 1
                    if (!invalid) string_token(value)
                } else {
                    invalid = 1
                }
            }
        }
        END {
            exit !(invalid == 0 && root_seen == 1 && finished == 1 && depth == 0 && pending == 0 && app_id_total == 1 && app_id_top == 1 && app_id_value == expected_app_id && state_flags_total == 1 && state_flags_top == 1 && state_flags_value == "4")
        }
    ' "${manifest_path}" || {
        echo "Steam manifest for App ${expected_app_id} is malformed, mismatched, or incomplete." >&2
        return 1
    }
}

require_json_object() {
    local path="$1"

    [[ -f "${path}" && ! -L "${path}" && -s "${path}" && -r "${path}" ]] || {
        echo "Required server configuration is not a non-empty regular file." >&2
        return 1
    }
    jq -e -s 'length == 1 and (.[0] | type == "object")' "${path}" >/dev/null || {
        echo "Required server configuration is not a valid JSON object." >&2
        return 1
    }
}

trap cleanup EXIT

ensure_real_directory "${SERVER_DIR}"
WORK_DIR="$(mktemp -d "${SERVER_DIR}/.wreckfest2-install.XXXXXX")"
STEAMCMD_DIR="${WORK_DIR}/steamcmd"
START_TMP="${WORK_DIR}/start.sh"
CONFIG_TMP="${WORK_DIR}/server_config.scnf"
STEAMCMD_ARCHIVE="${WORK_DIR}/steamcmd_linux.tar.gz"
ensure_real_directory "${SERVER_DIR}/steamapps"
prepare_regular_destination "${SERVER_DIR}/steamapps/appmanifest_1007.acf"
prepare_regular_destination "${SERVER_DIR}/steamapps/appmanifest_3519390.acf"
prepare_regular_destination "${SERVER_DIR}/Wreckfest2.exe"
mkdir -- "${STEAMCMD_DIR}"
command -v jq >/dev/null || {
    echo "The installer image does not provide jq for configuration validation." >&2
    exit 1
}

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
    https://media.steampowered.com/client/steamcmd_linux.tar.gz

steamcmd_archive_size="$(stat -c '%s' "${STEAMCMD_ARCHIVE}")"
[[ "${steamcmd_archive_size}" == "${STEAMCMD_ARCHIVE_SIZE}" ]] || {
    echo "SteamCMD archive size mismatch." >&2
    exit 1
}
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

require_complete_manifest "${SERVER_DIR}/steamapps/appmanifest_1007.acf" "1007"

"${STEAMCMD}" \
    +@sSteamCmdForcePlatformType windows \
    +force_install_dir "${SERVER_DIR}" \
    +login anonymous \
    +app_update 3519390 validate \
    +quit

require_complete_manifest "${SERVER_DIR}/steamapps/appmanifest_3519390.acf" "3519390"

ensure_real_directory "${SERVER_DIR}/.steam"
ensure_real_directory "${SERVER_DIR}/.steam/sdk32"
ensure_real_directory "${SERVER_DIR}/.steam/sdk64"
if [[ -f "${STEAMCMD_DIR}/linux32/steamclient.so" ]]; then
    prepare_regular_destination "${SERVER_DIR}/.steam/sdk32/steamclient.so"
    install -m 0644 "${STEAMCMD_DIR}/linux32/steamclient.so" \
        "${SERVER_DIR}/.steam/sdk32/steamclient.so"
fi
if [[ -f "${STEAMCMD_DIR}/linux64/steamclient.so" ]]; then
    prepare_regular_destination "${SERVER_DIR}/.steam/sdk64/steamclient.so"
    install -m 0644 "${STEAMCMD_DIR}/linux64/steamclient.so" \
        "${SERVER_DIR}/.steam/sdk64/steamclient.so"
fi

cat > "${START_TMP}" <<'WF2_START_SH'
#!/bin/bash
set -Eeuo pipefail

cd /home/container
[[ -d /home/container && ! -L /home/container ]] || {
    echo "Container root is not a real directory." >&2
    exit 1
}
if [[ ! -e save && ! -L save ]]; then
    mkdir -- save
fi
[[ -d save && ! -L save ]] || {
    echo "Save path is not a real directory." >&2
    exit 1
}
[[ -f ./Wreckfest2.exe && ! -L ./Wreckfest2.exe && -s ./Wreckfest2.exe ]] || {
    echo "Required server executable is missing or empty." >&2
    exit 1
}
[[ -f save/server_config.scnf && ! -L save/server_config.scnf && -s save/server_config.scnf ]] || {
    echo "Required server configuration is missing or empty." >&2
    exit 1
}
for destination in server.log steam_appid.txt; do
    if [[ -L "${destination}" || ( -e "${destination}" && ! -f "${destination}" ) ]]; then
        echo "Refusing unsafe runtime file destination: ${destination}" >&2
        exit 1
    fi
done
printf '1203190\n' > steam_appid.txt

: > server.log
tail -n 0 -F server.log &
tail_pid=$!
xvfb_pid=""
wine_pid=""
stop_requested=0
xvfb_log="$(mktemp /tmp/wreckfest2-xvfb.XXXXXX.log)"

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
    rm -f -- "${xvfb_log}"
    exit "${exit_status}"
}

forward_signal() {
    stop_requested=1
    if [[ -n "${wine_pid}" ]] && kill -0 "${wine_pid}" 2>/dev/null; then
        kill -TERM "${wine_pid}" 2>/dev/null || true
    fi
}

trap cleanup EXIT
trap forward_signal INT TERM

Xvfb :99 -screen 0 1024x768x24 -nolisten tcp > "${xvfb_log}" 2>&1 &
xvfb_pid=$!
export DISPLAY=:99
sleep 1 || true
if (( stop_requested != 0 )); then
    exit 0
fi
if ! kill -0 "${xvfb_pid}" 2>/dev/null; then
    echo "Xvfb failed to start." >&2
    exit 1
fi

wine ./Wreckfest2.exe --server --save-dir="$(winepath -w /home/container/save)" &
wine_pid=$!
if (( stop_requested != 0 )) && kill -0 "${wine_pid}" 2>/dev/null; then
    kill -TERM "${wine_pid}" 2>/dev/null || true
fi
wine_status=0
while true; do
    set +e
    wait "${wine_pid}"
    wine_status=$?
    set -e
    if ! kill -0 "${wine_pid}" 2>/dev/null; then
        break
    fi
done
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

prepare_regular_destination "${SERVER_DIR}/start.sh"
install -m 0755 "${START_TMP}" "${SERVER_DIR}/start.sh"
ensure_real_directory "${SERVER_DIR}/save"
prepare_regular_destination "${SERVER_DIR}/save/server_config.scnf"
if [[ ! -e "${SERVER_DIR}/save/server_config.scnf" ]]; then
    install -m 0644 "${CONFIG_TMP}" "${SERVER_DIR}/save/server_config.scnf"
fi
require_json_object "${SERVER_DIR}/save/server_config.scnf"
prepare_regular_destination "${SERVER_DIR}/steam_appid.txt"
printf '1203190\n' > "${SERVER_DIR}/steam_appid.txt"

require_regular_file "${SERVER_DIR}/Wreckfest2.exe" "Required server executable"
require_regular_file "${SERVER_DIR}/start.sh" "Runtime start script"
[[ -x "${SERVER_DIR}/start.sh" ]] || {
    echo "Runtime start script is missing or not executable." >&2
    exit 1
}
require_regular_file "${SERVER_DIR}/steam_appid.txt" "Steam application ID file"

echo "Installation complete: Wreckfest 2 dedicated server is ready."
