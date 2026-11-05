# TV_PROGRAM_GLOBAL

Android aplikacija (Python, Kivy/KivyMD) za pronalazenje TV stanica i njihovog dnevnog rasporeda.
Aplikacija prikazuje TV rasporede, ne TV prenos.

**Status: Faza 2 - osnovni Android projekat.** Postoje pocetni ekran, donja navigacija
(Pretraga, Omiljeni, Podesavanja) i tamno plava/zlatna tema. Pretraga, raspored i omiljeni
jos nisu implementirani (Faze 3-6).

## Struktura

```text
main.py                  ulazna tacka
buildozer.spec           podesavanja za APK
requirements.txt         zavisnosti za razvoj na racunaru (ne za APK)
app/
  tvapp.py               glavna klasa aplikacije
  version.py             verzija aplikacije (jedino mesto)
  strings.py             tekstovi interfejsa (srpski)
  theme.py               boje
  ui/main.kv             izgled ekrana
tests/test_smoke.py      osnovni testovi
.github/workflows/build-apk.yml   izgradnja APK-a na GitHub Actions
```

## Verzije

| Deo | Verzija | Napomena |
|---|---|---|
| Python na Androidu | 3.11.6 | Kivy 2.3.1 zvanicno podrzava 3.8-3.13. p4a po defaultu koristi 3.14, a Kivy 2.3.1 na 3.14 nije podrzan |
| Kivy | 2.3.1 | poslednje stabilno izdanje |
| KivyMD | 1.2.0 | ispisuje upozorenje da je zastareo, vidi Poznati problemi |
| Buildozer | 1.6.0 | |
| python-for-android | v2026.05.09 | fiksirano u buildozer.spec |
| Android NDK | 28c | preporuceno u p4a |
| Android API / minimum | 36 / 24 | 36 trazi Google Play za nove aplikacije |
| Arhitektura | arm64-v8a | |

## Izgradnja APK-a (GitHub Actions)

1. Otvori repozitorijum na GitHub-u, pa karticu **Actions**.
2. Izaberi **Izgradnja APK** (levo/u listi), pa **Run workflow**. Izgradnja se pokrece i sama posle svakog commit-a u `main`.
3. Prva izgradnja traje dugo (desetine minuta). Zuti krug = radi, zelena kvacica = uspesno, crveno X = greska.
4. Kad je zeleno, otvori taj tok i dole u delu **Artifacts** preuzmi `tv-program-global-debug-apk`. To je ZIP sa `.apk` fajlom.
5. Raspakuj ZIP, otvori `.apk` na telefonu i dozvoli instalaciju iz nepoznatih izvora kad telefon pita.

## Testovi

```text
python -m pytest -q tests
```

Test izgradnje UI-ja radi samo kad postoji ekran (na racunaru); u GitHub Actions se preskace.

## Poznati problemi i neproveren deo

- APK nije izgradjen niti pokretan na uredjaju ili emulatoru. Prva izgradnja na GitHub Actions je provera (go/no-go).
- UI stablo je proveravano samo na racunaru (Python 3.12, virtuelni ekran): gradi se bez greske. Izgled nije vizuelno proveren.
- KivyMD 1.2.0 je zastareo. KivyMD 2.0.0 sa PyPI zavisi od paketa materialshapes, koji trazi pycairo, a za pycairo nema Android paketa. Da li se 2.0.0 moze izgraditi za Android nije proveravano.
- Tekstovi se ne osvezavaju pri promeni jezika (Faza 7).
- Samo arm64-v8a (bez 32-bitnih telefona).
- Debug APK, podrazumevana ikona. Potpisivanje i AAB dolaze u Fazi 9. Dokumentacija Buildozera navodi da za objavu na Google Play treba python-for-android "develop" - proverava se u Fazi 9.
- `package.domain = org.vukica`: identifikator aplikacije je trajan na Google Play, potvrdi pre objave.
