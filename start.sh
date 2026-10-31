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
