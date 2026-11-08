# TV_PROGRAM_GLOBAL --- PROJECT ROADMAP

## Pravilo upravljanja fazama

Radi jednu fazu po jednu. Faza se smatra završenom tek kada su
isporučeni traženi rezultati i provereni kriterijumi prihvatanja. Ne
prelazi dalje bez korisnikove potvrde.

## Faza 0 --- Istraživanje izvora podataka

**Zadatak:** Ispitati XMLTV i druge legalne izvore TV rasporeda.

**Isporuka:** - tabela poređenja izvora; - pokrivenost po državama i
kanalima; - dostupnost današnjeg rasporeda; - API/format, kvote, cena i
licenca; - preporuka primarnog i rezervnog izvora.

**Kriterijum završetka:** Izvor je izabran na osnovu proverljivih
podataka i korisnik ga je odobrio.

## Faza 1 --- Tehnička specifikacija i arhitektura

**Zadatak:** Definisati module, tok podataka, modele i način
konfiguracije izvora.

**Isporuka:** - dijagram arhitekture; - predložena struktura foldera; -
model podataka za kanale, programe i izvore; - strategija keširanja i
vremenskih zona; - lista zavisnosti sa verzijama.

**Kriterijum završetka:** Arhitektura je razumljiva, realna za Android i
odobrena.

## Faza 2 --- Osnovni Android projekat

**Zadatak:** Napraviti minimalnu aplikaciju sa početnim ekranom,
navigacijom i temom.

**Isporuka:** Pokretljiv projekat, osnovni ekran, konfiguracija
Buildozer-a i README.

**Kriterijum završetka:** Aplikacija se pokreće u ciljnom okruženju;
poznati problemi su dokumentovani.

## Faza 3 --- Pretraga televizijskih stanica

**Zadatak:** Implementirati pretragu po nazivu, skraćenici i
alternativnom nazivu.

**Isporuka:** Rezultati pretrage sa državom i jasnim razlikovanjem
sličnih kanala.

**Kriterijum završetka:** Testirani su poznati primeri, nepostojeći
kanal i dvosmisleni nazivi.

## Faza 4 --- Povezivanje izvora TV rasporeda

**Zadatak:** Implementirati odobreni izvor podataka i normalizaciju
njegovog formata.

**Isporuka:** Adapter izvora, obrada grešaka, logovanje bez tajnih
podataka i testovi parsera.

**Kriterijum završetka:** Stvarni podaci se preuzimaju i prikazuju; nema
izmišljenih rasporeda.

## Faza 5 --- Dnevni TV vodič

**Zadatak:** Prikazati dnevnu satnicu, emisiju „Sada" i „Sledeće".

**Isporuka:** Pregledan raspored sa lokalnim vremenom stanice, opisima
kada postoje i indikatorom ažurnosti.

**Kriterijum završetka:** Provereni su vremenska zona, prelazak datuma i
nedostajući podaci.

## Faza 6 --- Omiljeni kanali i lokalna baza

**Zadatak:** Dodati SQLite čuvanje omiljenih stanica i poslednjih
uspešnih podataka.

**Kriterijum završetka:** Podaci ostaju sačuvani nakon zatvaranja
aplikacije i pravilno se ažuriraju.

## Faza 7 --- Podešavanja i lokalizacija

**Zadatak:** Dodati izbor jezika, temu, vremenske postavke i podešavanja
osvežavanja.

**Kriterijum završetka:** Podešavanja se pamte i UI se pravilno
osvežava.

## Faza 8 --- Testiranje i stabilizacija

**Zadatak:** Testirati mrežne greške, prazne odgovore, loše podatke,
spor internet, keš i različite Android veličine ekrana.

**Kriterijum završetka:** Kritične greške su uklonjene; preostale
poznate greške su dokumentovane.

## Faza 9 --- Android APK i isporuka

**Zadatak:** Podesiti Buildozer, dozvole, potpisivanje i proces
izgradnje.

**Isporuka:** APK, izvorni kod, README i uputstvo za instalaciju.

**Kriterijum završetka:** APK je uspešno izgrađen i instaliran/testiran
na Android uređaju ili emulatoru. Ako test na fizičkom uređaju nije
moguć, to mora biti jasno navedeno.

## Pravilo izmene plana

Svaka promena opsega, tehnologije ili redosleda faza mora biti
obrazložena i odobrena od korisnika pre primene.
