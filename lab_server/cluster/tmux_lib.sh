# Helpers to run a server in its own tmux session. Sourced by serve_*.sh and stop_*.sh.

# start_session NAME LOG COMMAND
# Same steps as by hand (lab rule: tmux first, then set_slot, then venv):
#   1. tmux new-session NAME
#   2. type "$SLOT_CMD; exit": set_slot opens a new login shell inside the slot (CPU/RAM cgroup);
#      the "; exit" closes the tmux session as soon as that shell ends.
#   3. type COMMAND into the slot shell, after checking it really is in a slot (/proc/self/cgroup),
#      with its output appended to LOG. COMMAND must end with "exec <server>", so the slot shell,
#      and therefore the session, ends when the server exits or is killed.
# set_slot does not pass environment variables through: COMMAND has to export everything it needs.
start_session() {
    local name=$1 log=$2 cmd=$3
    tmux new-session -d -s "$name"
    tmux send-keys -t "$name" "$SLOT_CMD; exit" Enter
    sleep 3   # let set_slot start its shell; keys sent earlier would still wait in the terminal
    tmux has-session -t "$name" 2>/dev/null || { echo "'$SLOT_CMD' failed, tmux session closed"; return 1; }
    tmux send-keys -t "$name" "exec > >(tee -a $log) 2>&1; \
grep -q '^0::/ml.slice' /proc/self/cgroup || { echo 'not inside a set_slot slot, aborting'; exit 1; }; $cmd" Enter
}

# stop_session NAME PROCESS_PATTERN
# Ctrl+C, then kill the session, then kill any of our processes still matching PROCESS_PATTERN
# (pkill -f). The slot shell lives in its own cgroup, so killing the tmux session alone is not
# guaranteed to take the server down with it.
stop_session() {
    local name=$1 pattern=$2 i
    if tmux has-session -t "$name" 2>/dev/null; then
        tmux send-keys -t "$name" C-c
        for i in $(seq 1 30); do
            tmux has-session -t "$name" 2>/dev/null || break
            sleep 1
        done
        tmux kill-session -t "$name" 2>/dev/null && echo "tmux session '$name' killed"
    fi
    if pgrep -u "$USER" -f "$pattern" >/dev/null; then
        echo "leftover processes, killing:"; pgrep -a -u "$USER" -f "$pattern" | sed 's/^/  /'
        pkill -u "$USER" -f "$pattern"
        for i in $(seq 1 15); do pgrep -u "$USER" -f "$pattern" >/dev/null || break; sleep 1; done
        pkill -9 -u "$USER" -f "$pattern" 2>/dev/null || true
    fi
}
