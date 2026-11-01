#!/bin/sh
# Launch Surgeon outside T3 Code's environment: systemd-run starts from the user manager's env,
# so ELECTRON_RUN_AS_NODE, NO_AT_BRIDGE and T3's AppArmor label don't carry over.
cd "$(dirname "$0")/.." || exit 1
systemctl --user stop surgeon-dev 2>/dev/null
exec systemd-run --user --collect --unit=surgeon-dev --working-directory="$PWD" \
  -E DISPLAY -E XAUTHORITY -E DBUS_SESSION_BUS_ADDRESS -E XDG_RUNTIME_DIR -E PATH -E HOME \
  "$PWD/node_modules/.bin/electron" . --no-sandbox  # Ubuntu 24.04 blocks the SUID sandbox without root setup
