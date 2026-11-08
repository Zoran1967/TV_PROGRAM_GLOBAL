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

echo "=== FreeType (rezervni izvori) ==="
# python-for-android preuzima FreeType sa download.savannah.gnu.org, koji cesto vraca 502/504.
# Ovde se isti fajl preuzima unapred (sa vise izvora), pa p4a koristi gotov folder (P4A_FREETYPE_DIR)
# i ne preuzima nista sam. Ako nijedan izvor ne radi, izgradnja ide po starom (sama preuzima).
FREETYPE_VERZIJA="2.14.1"
FREETYPE_IZVORI=${FREETYPE_IZVORI:-"https://download.savannah.gnu.org/releases/freetype/freetype-$FREETYPE_VERZIJA.tar.gz https://download-mirror.savannah.gnu.org/releases/freetype/freetype-$FREETYPE_VERZIJA.tar.gz https://downloads.sourceforge.net/project/freetype/freetype2/$FREETYPE_VERZIJA/freetype-$FREETYPE_VERZIJA.tar.gz"}
mkdir -p vendor
for izvor in $FREETYPE_IZVORI; do
  echo "Pokusavam: $izvor"
  rm -f vendor/freetype.tar.gz
  if curl -fL --retry 3 --retry-delay 5 --connect-timeout 20 --max-time 180 -o vendor/freetype.tar.gz "$izvor" \
      && tar -tzf vendor/freetype.tar.gz > /dev/null 2>&1; then
    rm -rf "vendor/freetype-$FREETYPE_VERZIJA"
    tar -xzf vendor/freetype.tar.gz -C vendor
    if [ -d "vendor/freetype-$FREETYPE_VERZIJA" ]; then
      export P4A_FREETYPE_DIR="$PWD/vendor/freetype-$FREETYPE_VERZIJA"
      echo "FreeType preuzet; koristi se $P4A_FREETYPE_DIR"
      break
    fi
  fi
  echo "Ovaj izvor ne radi."
done
if [ -z "${P4A_FREETYPE_DIR:-}" ]; then
  echo "UPOZORENJE: FreeType nije preuzet unapred; p4a pokusava sam."
fi

echo "=== Izgradnja APK-a ==="
# Preuzimanja biblioteka sa GitHub-a povremeno padnu (npr. HTTP 504); tada se pokusava ponovo.
for pokusaj in 1 2 3 4 5 6 7 8 9 10; do
  buildozer -v android debug 2>&1 | tee build.log
  status=${PIPESTATUS[0]}
  if [ "$status" -eq 0 ]; then
    break
  fi
  if [ "$pokusaj" -lt 10 ] && grep -qE "Gateway Time-out|Bad Gateway|Download failed|Server returned HTTP response code: 5|Connection (reset|aborted)|timed out|Temporary failure|Could not find a version that satisfies" build.log; then
    echo "Greska pri preuzimanju (pokusaj $pokusaj od 10). Ponovo za 20 s..."
    sleep 20
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
