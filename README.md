# TV_PROGRAM_GLOBAL

Android aplikacija (Python, Kivy/KivyMD) za pronalazenje TV stanica i njihovog dnevnog rasporeda.
Aplikacija prikazuje TV rasporede, ne TV prenos.

**Status: Faza 3 - pretraga televizijskih stanica.** Pretraga radi nad ugradjenim katalogom
stanica (bez interneta). Raspored jos nije povezan (Faze 4-5), omiljeni stizu u Fazi 6.

## Pretraga (Faza 3)

- Unos: naziv, skracenica ili alternativni naziv (npr. `RTS1`, `BBC One`, `CNN`, `HRT1`, `Dak`).
  Najmanje 2 slova/cifre, najvise 64 znaka.
- Razmaci, interpunkcija, velika/mala slova i dijakritici se ignorisu (`RTS 1`, `rts-1` i `rts1` su isto).
  Srpska cirilica se pretvara u latinicu (`РТС 1` nalazi `RTS 1`; `Đak`, `Djak` i `Ђак` su isto).
- Redosled: tacan naziv, naziv koji pocinje unosom, pa naziv u kome neka rec pocinje unosom
  (`one` nalazi `BBC One`). Samo ako nista nije pronadjeno, trazi se i unos iz sredine reci.
- Najvise 50 rezultata. Stanice istog naziva u razlicitim drzavama se ne spajaju: svaki
  rezultat ima drzavu, a po potrebi mrezu, naziv po kome je pronadjen i ID kataloga.
- Prvi rezultat se nikad ne bira automatski. Dodir na rezultat samo belezi izbor
  (prikaz rasporeda dolazi u narednim fazama).

## Katalog stanica

- Fajl `data/catalog_seed.db` (SQLite, samo za citanje) ulazi u APK.
- Izvor: [iptv-org/database](https://github.com/iptv-org/database), licenca Unlicense / CC0
  (javno vlasnistvo). Izbaceni su ugaseni kanali i kanali za odrasle.
  Trenutno: 29.910 stanica iz 231 drzave. Tacan commit izvora i vreme izrade su u tabeli `meta`
  i prikazuju se na kartici Podesavanja.
- Stanica u katalogu NE znaci da za nju postoji raspored. Dostupnost rasporeda zavisi od izvora
  (Faza 4). Pokrivenost nije obecana.
- Logotipi se ne koriste: prava na slike nisu proverena.
- Nazivi drzava su na engleskom (iz izvora). Lokalizacija je u Fazi 7.
- Novi katalog (potreban racunar ili Termux sa internetom):
  `python tools/build_catalog.py`

## Struktura

```text
main.py                      ulazna tacka
buildozer.spec               podesavanja za APK
requirements.txt             zavisnosti za razvoj na racunaru (ne za APK)
app/
  tvapp.py                   glavna klasa aplikacije
  version.py                 verzija aplikacije (jedino mesto)
  strings.py                 tekstovi interfejsa (srpski)
  theme.py                   boje
  ui/main.kv                 izgled ekrana
  screens/search_view.py     ekran pretrage
  services/search_service.py pretraga (pravila, statusi)
  database/schema.py         sema kataloga
  database/catalog.py        citanje kataloga
  models/channel.py          modeli stanice i rezultata
  utils/text.py              normalizacija teksta
  utils/android_insets.py    visina sistemskih traka na Androidu
data/catalog_seed.db         katalog stanica
tools/build_catalog.py       pravi katalog (ne ulazi u APK)
ci/build.sh, ci/test.sh      skripte za GitHub Actions
tests/                       testovi
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
2. Izaberi **Izgradnja APK**, pa **Run workflow**. Izgradnja se pokrece i sama posle raspakivanja ZIP-a.
3. Prva izgradnja traje dugo (desetine minuta). Zuti krug = radi, zelena kvacica = uspesno, crveno X = greska.
4. Kad je zeleno, otvori **Releases** i skini najnoviji `.apk` (ili u delu **Artifacts** u samom toku).
5. Otvori `.apk` na telefonu i dozvoli instalaciju iz nepoznatih izvora kad telefon pita.

## Testovi

```text
python -m pytest -q tests
```

Testovi pretrage rade bez Kivy-ja. Testovi ekrana rade samo kad postoji ekran (na racunaru) i
u GitHub Actions se preskacu.

## Poznati problemi i neproveren deo

- APK je izgradjen na GitHub Actions i korisnik ga je instalirao i pokrenuo na jednom Android
  telefonu (verzija 0.1.0 i 0.1.1; ispravka razmaka za sistemske trake potvrdjena na tom telefonu).
  Drugi uredjaji i emulator nisu testirani.
- Pretraga (0.2.0) je proverena testovima na racunaru (ukljucujuci ekran na virtuelnom displeju).
  Izgled ekrana pretrage i brzina na telefonu nisu proveravani. Na racunaru tipican upit traje
  manje od 1 ms, najgori (`tv`) oko 30 ms.
- Unos iz sredine reci (npr. `ena sport`) radi samo kad nema boljih rezultata.
- Pretraga ne zna za greske u kucanju (npr. `Arena Sprot`).
- KivyMD 1.2.0 je zastareo. KivyMD 2.0.0 sa PyPI zavisi od paketa materialshapes, koji trazi
  pycairo, a za pycairo nema Android paketa. Da li se 2.0.0 moze izgraditi za Android nije proveravano.
- Tekstovi se ne osvezavaju pri promeni jezika (Faza 7).
- Samo arm64-v8a (bez 32-bitnih telefona).
- Debug APK, podrazumevana ikona. Potpisivanje i AAB dolaze u Fazi 9. Dokumentacija Buildozera
  navodi da za objavu na Google Play treba python-for-android "develop" - proverava se u Fazi 9.
- `package.domain = org.vukica`: identifikator aplikacije je trajan na Google Play, potvrdi pre objave.
