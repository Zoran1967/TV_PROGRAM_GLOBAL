# TV_PROGRAM_GLOBAL --- TECHNICAL SPECIFICATION

## 1. Platforma i osnovni okvir

-   Ciljna platforma: Android telefon.
-   Jezik implementacije: Python.
-   UI: Kivy/KivyMD, nakon provere kompatibilnosti izabranih verzija.
-   Lokalna baza: SQLite.
-   Mrežna komunikacija: HTTPS REST ili preuzimanje XMLTV podataka, u
    skladu sa izabranim izvorom.
-   Pakovanje: Buildozer/python-for-android.
-   Verzije koda: Git/GitHub.

## 2. Predložena logička arhitektura

Aplikaciju podeliti u odvojene slojeve:

1.  **UI layer** --- ekrani, navigacija, prikaz rezultata i rasporeda.
2.  **Application/service layer** --- orkestracija pretrage, osvežavanja
    i omiljenih kanala.
3.  **Provider adapters** --- zaseban adapter za svaki izvor TV
    podataka.
4.  **Data normalization** --- pretvaranje odgovora različitih izvora u
    jedinstven interni format.
5.  **Persistence layer** --- SQLite, keš i omiljeni kanali.
6.  **Configuration layer** --- jezik, tema, vremenska zona i
    podešavanja.

UI ne sme direktno da zavisi od specifičnog formata jednog API-ja.

## 3. Predloženi modeli podataka

### Channel

-   `id` --- interni jedinstveni identifikator;
-   `provider_id` --- identifikator kanala kod izvora;
-   `name` --- puno ime stanice;
-   `aliases` --- alternativni nazivi/skraćenice;
-   `country_code` --- ISO oznaka države, ako je dostupna;
-   `timezone` --- IANA vremenska zona, ako je dostupna;
-   `logo_url` --- opcioni URL logotipa;
-   `provider_name` --- izvor podataka.

### Programme

-   `id` --- interni identifikator;
-   `channel_id` --- veza sa kanalom;
-   `title` --- naziv emisije;
-   `description` --- opcioni opis;
-   `start_utc` --- početak kao UTC vremenska oznaka;
-   `end_utc` --- završetak kao UTC vremenska oznaka;
-   `category` --- opcioni žanr/kategorija;
-   `source_updated_at` --- vreme poslednjeg ažuriranja izvora.

### Favourite

-   `channel_id` --- identifikator omiljenog kanala;
-   `created_at` --- vreme dodavanja.

Napomena: konačan model prilagoditi stvarnoj šemi izabranog izvora. Ne
izmišljati polja koja izvor ne pruža.

## 4. Pretraga kanala

-   Normalizovati velika/mala slova i višak razmaka.
-   Podržati pretragu po punom nazivu i aliasima.
-   Ne birati automatski prvi rezultat ako postoji više mogućih kanala.
-   Prikazati državu kao pomoć za razdvajanje kanala istog imena.
-   Prikazati poruku „Stanica nije pronađena" kada nema rezultata.

## 5. Vremenske zone

-   Čuvati vremena u UTC formatu kada izvor omogućava pouzdanu
    konverziju.
-   Prikazivati vreme u vremenskoj zoni kanala.
-   Koristiti IANA identifikatore vremenskih zona, ne ručno fiksne
    pomake.
-   Obraditi letnje/zimsko računanje vremena.
-   Ako vremenska zona kanala nije poznata, jasno prikazati da je zona
    nepoznata; ne nagađati.

## 6. Keširanje i rad bez mreže

-   Čuvati poslednje uspešno preuzete rezultate.
-   Prikazati vreme poslednjeg osvežavanja.
-   Ne prikazivati zastarele podatke kao da su uživo.
-   Ako nema mreže, prikazati keš uz oznaku „Poslednje sačuvano".
-   Definisati rok važenja keša prema ograničenjima izvora.

## 7. Bezbednost

-   API ključeve čuvati van javnog repozitorijuma.
-   Ne uključivati tajne u logove.
-   Koristiti HTTPS kada je podržan.
-   Ograničiti timeout i broj ponovnih pokušaja.
-   Validirati podatke pre upisa u bazu.
-   Tražiti samo Android dozvole koje su zaista potrebne.

## 8. Testiranje

Obavezni testovi: - normalizacija naziva i aliasa; - više kanala sa
sličnim nazivom; - prazni i neispravni odgovori izvora; - parsiranje
vremena i vremenskih zona; - emisija koja je trenutno na programu; -
prelazak preko ponoći; - nedostupna mreža i timeout; - čuvanje i čitanje
omiljenih kanala; - keširanje i označavanje zastarelih podataka.

## 9. Predložena struktura projekta

Konačnu strukturu potvrditi u Fazi 1. Početni predlog:

``` text
TV_PROGRAM_GLOBAL/
├── main.py
├── app/
│   ├── screens/
│   ├── widgets/
│   ├── services/
│   ├── providers/
│   ├── models/
│   ├── database/
│   └── utils/
├── assets/
│   ├── icons/
│   └── fonts/
├── tests/
├── requirements.txt
├── buildozer.spec
├── README.md
└── .gitignore
```

Ne kreirati sve foldere unapred ako još nisu potrebni. Strukturu uvoditi
fazno i održavati je usklađenom sa stvarnim kodom.

## 10. Važno ograničenje proizvoda

Aplikacija prikazuje TV rasporede, ne TV prenos. Funkcija gledanja uživo
nije deo osnovnog opsega i ne sme se dodavati bez posebnog zahteva,
provere legalnih izvora i korisnikove potvrde.
