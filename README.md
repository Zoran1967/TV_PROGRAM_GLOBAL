# TV_PROGRAM_GLOBAL

Android aplikacija (Python, Kivy/KivyMD) za pronalazenje TV stanica i njihovog dnevnog rasporeda.
Aplikacija prikazuje TV rasporede, ne TV prenos.

**Status: Faza 6 - omiljene stanice i trajni kes.** Pretraga radi nad ugradjenim katalogom stanica (bez
interneta). Za 126 stanica sa Balkana (Srbija, Hrvatska, Slovenija, BiH, Crna Gora, Severna
Makedonija) aplikacija preuzima raspored sa izvora TvProfil i prikazuje danasnji program sa
oznakama "Sada" i "Sledece". Omiljene stanice i poslednji preuzeti raspored ostaju sacuvani i
posle zatvaranja aplikacije (Faza 6). Podesavanja i jezici stizu u Fazi 7.

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

## Raspored i izvori (Faza 4)

- Dodir na stanicu u rezultatima otvara raspored za danas u vremenskoj zoni stanice
  (datum, zona i izvor su ispisani; "Nazad na rezultate" vraca na pretragu).
- Stanica ima raspored samo ako je povezana sa izvorom (u rezultatima se to vidi tek po dodiru;
  stanice bez izvora dobijaju poruku da izvor nije povezan). Pokrivenost nije obecana.
- Izvor: TvProfil (https://tvprofil.net/xmltv/), XMLTV fajl po stanici, nekoliko dana unapred.
  Spisak njihovih kanala je u `data/sources/tvprofil_channels.csv` (prepisan sa njihove stranice
  06.11.2026.). Povezivanje sa katalogom je dozvoljeno samo kad je jednoznacno (ista drzava i isti
  naziv, ili rucno potvrdjeno u `data/sources/tvprofil_overrides.csv`). Od 220 kanala sa spiska:
  126 povezano, 31 bez podataka kod izvora, 59 bez poklapanja, 2 dvosmislena, 2 rucno iskljucena.
  Izvestaj po kanalu: `data/sources/tvprofil_mapping_report.csv`.
- Vremena u TvProfil fajlovima nemaju pomak; tumace se kao lokalno vreme drzave stanice
  (Europe/Belgrade, Zagreb, Ljubljana, Sarajevo, Podgorica, Skopje). Prelazak na letnje/zimsko
  vreme je obradjen (dvaput isti sat u oktobru). Stanica bez poznate zone ne prikazuje raspored.
- Greske se objasnjavaju na ekranu: nema veze, HTTP greska (npr. 404), izvor trazi pauzu, prazan
  odgovor, neispravni podaci, nepoznata zona. Ako osvezavanje ne uspe a postoje stariji podaci iz
  iste sesije, prikazuju se uz oznaku "stariji podaci" i razlog.
- Mreza: samo https, rok 20 s, najvise 2 ponovna pokusaja (mrezne greske i HTTP 5xx), 429 se
  postuje, odgovor najvise 8 MB (i posle gzip raspakivanja), preusmeravanje na http je blokirano.
  Nema tajnih kljuceva. Preuzimanje radi u pozadinskoj niti.
- Licenca: TvProfil je besplatan za kucnu upotrebu; za javnu objavu treba pisana dozvola.
  U `data/providers.json` je zato `license_status = pending`. Izgradnja "dev"
  (`app/build_flavor.py`) ucitava taj izvor, izgradnja "release" ga ne ucitava dok status
  ne postane `approved`.
- Novi izvor: novi adapter u `app/providers/`, unos u `ADAPTER_FACTORIES`
  (`app/providers/registry.py`) i u `data/providers.json`, plus veze stanica u katalogu
  (`channel_source`). Ekran i servisi se ne menjaju.

## Dnevni vodic (Faza 5)

- Zaglavlje: datum, zona stanice, **vreme u stanici**, "Sada" (sa krajem i preostalim vremenom),
  "Sledece", izvor i **ažurnost** ("Ažurno, osvezeno 14:05, pre 3 min"; ako su podaci stariji od
  roka osvezavanja izvora: "Podaci su stari ... Dodirnite Osvezi"; ako osvezavanje nije uspelo:
  "stariji podaci" uz razlog).
- Lista: sve emisije koje se preklapaju sa danasnjim danom, u vremenu stanice. Emisija koja je
  pocela juce je oznacena ("juce 23:00-00:30"), a ona koja se zavrsava sutra ("23:30-01:30 (sutra)").
  Trenutna emisija je istaknuta ("SADA"), sledeca ("SLEDECE"), zavrsene su prigusene. Lista se pri
  otvaranju sama pomera na trenutnu emisiju.
- Rupe u rasporedu (duze od 2 minuta) su prikazane kao "Nema podataka od 00:30 do 06:00".
  Emisije bez opisa ili kategorije se prikazuju bez njih; ništa se ne dopisuje.
- Pravila za "Sada/Sledece" (`app/services/now_next.py`): "Sada" je emisija koja je pocela i cije
  vreme zavrsetka je poznato i jos nije proslo. Ako izvor ne daje kraj, kraj je pocetak sledece
  emisije (naznaceno na ekranu). Poslednja emisija bez kraja se ne oznacava kao "Sada". Pri
  preklapanju "Sada" je emisija koja je poslednja pocela. U rupi nema "Sada", a "Sledece" je
  prva emisija koja tek pocinje. "Sledece" se racuna nad celim rasporedom, pa u 23:50 moze biti
  emisija posle ponoci.
- Vreme tece: na svakih 20 s se "Sada/Sledece" pomeraju bez interneta, a u ponoc se prelazi na
  novi dan iz vec preuzetih podataka. Novo preuzimanje ide kad podaci isteknu ili kad prikaz
  nije u redu (najcesce na 5 min).
- Dugme "Osvezi" trazi nove podatke; ako su preuzeti pre manje od minut, koriste se oni.

## Omiljene stanice i trajni kes (Faza 6)

- Zvezdica pored dugmeta "Osvezi" (na ekranu rasporeda) dodaje stanicu u omiljene ili je uklanja.
  Kartica **Omiljeni** prikazuje spisak (po nazivu, sa drzavom); dodir otvara raspored, a dugme
  "Nazad na omiljene" vraca na spisak.
- Omiljene se cuvaju po `catalog_id` (npr. `RTS1.rs`), pa ostaju ispravne i kad se katalog osvezi.
  Ako stanice vise nema u katalogu, ne prikazuje se, ali ostaje sacuvana i ekran javlja koliko ih je.
- Poslednji uspesno preuzet raspored svake stanice se upisuje na disk. Posle ponovnog pokretanja:
  svez podatak (mladji od roka osvezavanja izvora) se koristi bez mreze; stariji se pokusava osveziti,
  a ako mreze nema prikazuje se uz oznaku "stariji podaci" i pravo vreme preuzimanja. Neuspelo osvezavanje
  ne prepisuje sacuvane podatke. Nista se ne izmislja: bez sacuvanih podataka i bez mreze ekran javlja gresku.
- Baza je `userdata.db` u folderu aplikacije (`App.user_data_dir`), odvojena od kataloga koji se ne menja.
  Kes drzi najvise 100 stanica i brise podatke starije od 14 dana. Sacuvan raspored "iz buducnosti"
  (pogresan sat telefona) se ignorise.
- Ostecena baza se premesta u `userdata.db.corrupt-<vreme>` (ne brise se) i pravi se nova. Baza novije
  verzije aplikacije se ne dira. Ako trajno cuvanje ne radi, pretraga i raspored rade dalje (kes je samo
  u memoriji), a kartica Omiljeni to objasnjava; stanje se vidi i u Podesavanjima.
- Za razvoj i testove: promenljiva okruzenja `TVPG_USER_DATA_DIR` menja folder korisnickih podataka.

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
  screens/search_view.py     ekran pretrage i rasporeda
  screens/favourites_view.py ekran omiljenih stanica
  services/search_service.py pretraga (pravila, statusi)
  services/schedule_service.py raspored za danas (kes u memoriji i na disku, greske, zona, osvezavanje prikaza)
  services/favourites_service.py omiljene stanice (korisnicka baza + katalog)
  services/now_next.py       izracunavanje "Sada" i "Sledece"
  services/factory.py        pravi servise pri pokretanju
  providers/                 izvori rasporeda: base, tvprofil, xmltv, registry, errors
  net/http_client.py         preuzimanje (rok, ogranicenja, ponovni pokusaji)
  build_flavor.py            "dev" ili "release" izgradnja
  database/schema.py         sema kataloga
  database/catalog.py        citanje kataloga
  database/userdata.py       omiljene i trajni kes rasporeda (upisiva baza userdata.db)
  models/channel.py          modeli stanice i rezultata
  models/schedule.py         modeli emisije i veze stanice sa izvorom
  utils/text.py              normalizacija teksta
  utils/android_insets.py    visina sistemskih traka na Androidu
data/catalog_seed.db         katalog stanica (+ veze sa izvorom rasporeda)
data/providers.json          podesavanja izvora rasporeda (bez tajni)
data/sources/                spisak TvProfil kanala, rucne veze, izvestaj (ne ulazi u APK)
tools/build_catalog.py       pravi katalog i veze (ne ulazi u APK)
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

Testovi pretrage, parsera, mreze (pravi lokalni server) i rasporeda rade bez Kivy-ja. Testovi
ekrana rade samo kad postoji ekran (na racunaru) i u GitHub Actions se preskacu.

## Poznati problemi i neproveren deo

- **Preuzimanje sa TvProfil-a nije proveravano na pravom serveru.** Okruzenje u kome se pise kod
  nema pristup tvprofil.net. Adresa fajla (`https://tvprofil.net/xmltv/data/{id}/weekly_{id}_tvprofil.net.xml`)
  je preuzeta iz imena fajlova sa njihove stranice i iz javnih primera, a ne iz stvarnog preuzimanja.
  Parser je proveren samo na izmisljenim XMLTV primerima po XMLTV standardu. Prvo pokretanje na
  telefonu je prava provera: ako izvor odgovara drugacije, ekran ispisuje razlog (npr. greska 404).
- **Zona:** pretpostavka da su vremena lokalna po drzavi stanice potice iz XMLTV opisa i primera
  korisnika; nije potvrdjena na pravom fajlu. Provera na telefonu: npr. dnevnik na RTS1 treba da
  bude u uobicajeno vreme (oko 19:30), ne sat ranije ili kasnije.
- Pretraga ne pokazuje unapred koja stanica ima raspored; to se vidi tek posle dodira.
- Izgled ekrana rasporeda (isticanje trenutne emisije, pomeranje liste, dugmad) proveren je samo
  testovima na racunaru, ne na telefonu.
- Trajno cuvanje (omiljene, kes) je proveravano testovima na racunaru; na telefonu nije. Nije proveren
  ni upis u `user_data_dir` na Androidu niti ponasanje kad Android ocisti podatke aplikacije
  (tada se omiljene brisu zajedno sa njima).
- Omiljene se ne mogu ukloniti sa kartice Omiljeni; uklanjaju se zvezdicom na ekranu rasporeda.
- "Sada/Sledece" se racunaju iz sata na telefonu; pogresan sat telefona daje pogresne oznake
  (aplikacija to ne proverava).
- Izbor drugog datuma jos ne postoji (izvor daje samo narednih nekoliko dana).
- Stanice van Balkana (Srbija, Hrvatska, Slovenija, BiH, Crna Gora, Severna Makedonija) nemaju
  izvor rasporeda. TvProfil kanali bez oznake drzave (sport, filmovi, vesti...) nisu povezani jer im
  zona nije odredjena.
- Na Androidu nisu proveravani: HTTPS sa `certifi` sertifikatima i paket `tzdata` (zone). Ako zona
  nije dostupna, prikazuje se poruka umesto rasporeda.
- Pretraga (0.2.0) i ekran su proveravani testovima na racunaru (virtuelni displej). Izgled
  ekrana rasporeda i brzina na telefonu nisu proveravani.
- Unos iz sredine reci (npr. `ena sport`) radi samo kad nema boljih rezultata. Pretraga ne zna za
  greske u kucanju.
- Nazivi drzava su na engleskom (iz izvora); lokalizacija je u Fazi 7. Tekstovi se ne osvezavaju
  pri promeni jezika.
- KivyMD 1.2.0 je zastareo. KivyMD 2.0.0 sa PyPI zavisi od paketa materialshapes, koji trazi
  pycairo, a za pycairo nema Android paketa. Da li se 2.0.0 moze izgraditi nije proveravano.
- Samo arm64-v8a. Debug APK, podrazumevana ikona. Potpisivanje i AAB dolaze u Fazi 9. Dokumentacija
  Buildozera navodi da za objavu na Google Play treba python-for-android "develop" - Faza 9.
- `package.domain = org.vukica`: identifikator aplikacije je trajan na Google Play, potvrdi pre objave.
