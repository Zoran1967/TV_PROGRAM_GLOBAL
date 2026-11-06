[app]

title = TV Program Global
package.name = tvprogramglobal
package.domain = org.vukica

source.dir = .
source.include_exts = py,kv,png,jpg,json,ttf,db
source.exclude_dirs = tests,bin,docs,.github,.buildozer,tools

# Verzija se cita iz app/version.py (jedino mesto za izmenu verzije)
version.regex = __version__ = ["'](.*)["']
version.filename = %(source.dir)s/app/version.py

# Python 3.11.6 + Kivy 2.3.1 + KivyMD 1.2.0 (vidi README, odeljak Verzije)
requirements = python3==3.11.6,hostpython3==3.11.6,kivy==2.3.1,kivymd==1.2.0,pillow

orientation = portrait
fullscreen = 0

# Dozvole: u Fazi 2 nisu potrebne. INTERNET se dodaje u Fazi 4.
# android.permissions =

android.api = 36
android.minapi = 24
android.ndk = 28c
android.ndk_api = 24
android.archs = arm64-v8a
android.accept_sdk_license = True

# Fiksirana verzija python-for-android (ponovljiva izgradnja)
p4a.branch = v2026.05.09

[buildozer]

log_level = 2
warn_on_root = 1
