#!/usr/bin/env bash
# Izgradnja APK-a (debug, ili potpisani release ako su podesene tajne za potpisivanje). Pokrece ga GitHub Actions (radni tok "Izgradnja APK").
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

echo "=== Biblioteke (rezervni izvori) ==="
# python-for-android preuzima OpenSSL sa www.openssl.org i SDL2_mixer sa GitHub-a; oba cesto vrate 504.
# Ovde se fajl preuzima unapred (sa vise izvora) u kes koji p4a vec koristi
# (.buildozer/android/platform/build-arm64-v8a/packages/<recept>/). Ako je fajl tamo, p4a ga ne preuzima ponovo.
PAKETI_DIR="$PWD/.buildozer/android/platform/build-arm64-v8a/packages"
pripremi_paket() {
  local recept="$1"; shift
  local ime; ime=$(basename "$1")
  local cilj="$PAKETI_DIR/$recept/$ime"
  mkdir -p "$PAKETI_DIR/$recept"
  for izvor in "$@"; do
    echo "Pokusavam ($recept): $izvor"
    rm -f "$cilj" "$PAKETI_DIR/$recept/.mark-$ime"
    if curl -fL --retry 3 --retry-delay 5 --connect-timeout 20 --max-time 180 -o "$cilj" "$izvor" \
        && tar -tzf "$cilj" > /dev/null 2>&1; then
      touch "$PAKETI_DIR/$recept/.mark-$ime"
      echo "Preuzeto unapred: $recept"
      return 0
    fi
    rm -f "$cilj"
    echo "Ovaj izvor ne radi."
  done
  echo "UPOZORENJE: $recept nije preuzet unapred; p4a pokusava sam."
  return 0
}
# Verzije moraju da se poklapaju sa verzijama u python-for-android grani iz buildozer.spec.
pripremi_paket openssl \
  "https://www.openssl.org/source/openssl-3.3.1.tar.gz" \
  "https://ftp.openssl.org/source/openssl-3.3.1.tar.gz" \
  "https://github.com/openssl/openssl/archive/refs/tags/openssl-3.3.1.tar.gz" \
  "https://github.com/openssl/openssl/releases/download/openssl-3.3.1/openssl-3.3.1.tar.gz"
pripremi_paket sdl2_mixer \
  "https://github.com/libsdl-org/SDL_mixer/releases/download/release-2.6.3/SDL2_mixer-2.6.3.tar.gz" \
  "https://www.libsdl.org/projects/SDL_mixer/release/SDL2_mixer-2.6.3.tar.gz"

echo "=== Potpisivanje (neobavezno) ==="
# Kljuc za potpisivanje NIKAD ne ide u repozitorijum. Upisuje se u GitHub: Settings -> Secrets and
# variables -> Actions: KEYSTORE_BASE64, KEYSTORE_PASSWORD, KEY_ALIAS (i neobavezno KEY_PASSWORD).
# Bez njih se gradi debug APK, kao do sada. Vidi README, odeljak "Faza 9".
REZIM="debug"
if [ -n "${KEYSTORE_BASE64:-}" ] || [ -n "${KEYSTORE_PASSWORD:-}" ] || [ -n "${KEY_ALIAS:-}" ]; then
  if [ -z "${KEYSTORE_BASE64:-}" ] || [ -z "${KEYSTORE_PASSWORD:-}" ] || [ -z "${KEY_ALIAS:-}" ]; then
    echo "GRESKA: za potpisivanje moraju biti podesena sva tri: KEYSTORE_BASE64, KEYSTORE_PASSWORD, KEY_ALIAS."
    exit 1
  fi
  KEYSTORE_FAJL="${RUNNER_TEMP:-/tmp}/release.keystore"
  if ! printf '%s' "$KEYSTORE_BASE64" | base64 -d > "$KEYSTORE_FAJL" 2>/dev/null || [ ! -s "$KEYSTORE_FAJL" ]; then
    echo "GRESKA: KEYSTORE_BASE64 nije ispravan base64 tekst."
    exit 1
  fi
  export P4A_RELEASE_KEYSTORE="$KEYSTORE_FAJL"
  export P4A_RELEASE_KEYALIAS="$KEY_ALIAS"
  export P4A_RELEASE_KEYSTORE_PASSWD="$KEYSTORE_PASSWORD"
  export P4A_RELEASE_KEYALIAS_PASSWD="${KEY_PASSWORD:-$KEYSTORE_PASSWORD}"
  REZIM="release"
  echo "Kljuc je podesen: gradi se potpisani release APK."
else
  echo "Kljuc nije podesen: gradi se debug APK (potpisan privremenim debug kljucem)."
fi

echo "=== Stalni kljuc za debug APK ==="
# Debug APK se inace potpisuje novim, slucajnim kljucem pri svakoj izgradnji, pa se nova verzija ne
# moze instalirati preko stare (mora da se brise aplikacija i gube omiljene). Ako postoji
# ci/stalni_kljuc.b64, gradle ga koristi kao debug kljuc: svaki APK je potpisan istim kljucem i
# instalira se preko stare verzije. Verzija u app/version.py mora stalno da raste.
if [ "$REZIM" = "debug" ] && [ -f ci/stalni_kljuc.b64 ]; then
  mkdir -p "$HOME/.android"
  if base64 -d ci/stalni_kljuc.b64 > "$HOME/.android/debug.keystore" 2>/dev/null && [ -s "$HOME/.android/debug.keystore" ]; then
    echo "Debug APK se potpisuje stalnim kljucem (ci/stalni_kljuc.b64)."
  else
    rm -f "$HOME/.android/debug.keystore"
    echo "UPOZORENJE: ci/stalni_kljuc.b64 nije ispravan; debug APK dobija privremeni kljuc."
  fi
else
  echo "Nema ci/stalni_kljuc.b64 ili je release rezim: kljuc se ne menja."
fi

echo "=== Izgradnja APK-a ==="
# Preuzimanja biblioteka sa GitHub-a povremeno padnu (npr. HTTP 504); tada se pokusava ponovo.
for pokusaj in 1 2 3 4 5 6 7 8 9 10; do
  buildozer -v android "$REZIM" 2>&1 | tee build.log
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
