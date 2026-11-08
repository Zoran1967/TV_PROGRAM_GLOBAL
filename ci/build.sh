#!/usr/bin/env bash
# Izgradnja debug APK-a. Pokrece ga GitHub Actions (radni tok "Izgradnja APK").
# Sistemski paketi i verzije se menjaju OVDE, ne u .yml fajlu.
set -uo pipefail

echo "=== Sistemski paketi ==="
sudo apt-get update
sudo apt-get install -y git zip unzip autoconf automake libtool \
  pkg-config zlib1g-dev libncurses-dev cmake libffi-dev libssl-dev \
  libltdl-dev build-essential || exit 1

echo "=== Buildozer ==="
python -m pip install buildozer==1.6.0 || exit 1

echo "=== Izgradnja APK-a ==="
# Preuzimanja biblioteka sa GitHub-a povremeno padnu (npr. HTTP 504); tada se pokusava ponovo.
for pokusaj in 1 2 3; do
  buildozer -v android debug 2>&1 | tee build.log
  status=${PIPESTATUS[0]}
  if [ "$status" -eq 0 ]; then
    break
  fi
  if [ "$pokusaj" -lt 3 ] && grep -qE "Gateway Time-out|Download failed|Connection (reset|aborted)|timed out|Temporary failure" build.log; then
    echo "Greska pri preuzimanju (pokusaj $pokusaj od 3). Ponovo za 30 s..."
    sleep 30
  else
    break
  fi
done

if [ "$status" -ne 0 ]; then
  echo
  echo "=================================================="
  echo "IZGRADNJA NIJE USPELA (kod $status)"
  echo "Redovi sa greskom:"
  sed -E 's/\x1b\[[0-9;]*m//g' build.log \
    | grep -nE "error:|Error:|ERROR|FAILED|fatal|Command failed" \
    | cut -c1-220 | tail -n 15
  echo "--------------------------------------------------"
  echo "Poslednjih 60 redova:"
  sed -E 's/\x1b\[[0-9;]*m//g' build.log | tail -n 60 | cut -c1-220
  echo "=================================================="
  exit "$status"
fi

echo "=== Gotovo ==="
ls -la bin/
