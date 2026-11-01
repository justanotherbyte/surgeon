#!/bin/sh
# Open the demo apps outside T3 Code, with temp settings and data dirs so nothing reaches the
# user's dconf or recent files. Usage: scripts/demo-apps.sh [image] [writer] [terminal] [alacritty]
T=/tmp/surgeon-demo
mkdir -p $T/cfg $T/data $T/state $T/cache $T/docs
[ -f $T/docs/report.odt ] || {
  printf 'Quarterly report\n\nA demo document for Application Surgeon.\n' > $T/docs/report.txt
  soffice -env:UserInstallation=file://$T/lo-cli --headless --convert-to odt --outdir $T/docs $T/docs/report.txt >/dev/null 2>&1
}
run() {
  systemd-run --user --collect --quiet -E DISPLAY -E XAUTHORITY -E DBUS_SESSION_BUS_ADDRESS -E XDG_RUNTIME_DIR \
    -E GSETTINGS_BACKEND=memory -E XDG_CONFIG_HOME=$T/cfg -E XDG_DATA_HOME=$T/data -E XDG_STATE_HOME=$T/state \
    -E XDG_CACHE_HOME=$T/cache sh -c "exec $* >/dev/null 2>&1"
}
for app in ${@:-image writer terminal alacritty}; do
  case $app in
    image) run eog --new-instance "${IMAGE:-$(ls /usr/share/backgrounds/*.jpg | head -1)}" ;;  # never join the user's Image Viewer
    writer) run soffice -env:UserInstallation=file://$T/lo --writer $T/docs/report.odt ;;  # dismiss Tip of the Day once
    terminal) run gnome-terminal --class=SurgeonDemo ;;
    alacritty) run alacritty ;;
  esac
done
