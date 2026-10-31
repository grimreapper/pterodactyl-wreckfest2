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
