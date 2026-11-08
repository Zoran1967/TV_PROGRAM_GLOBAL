"""Nazivi drzava za prikaz. Katalog ima engleske nazive; za srpski se prevode ovde.

Drzava koje nema u tabeli prikazuje se engleski naziv iz kataloga (nista se ne izmislja).
"""

SERBIAN = {
    "AD": "Andora", "AE": "Ujedinjeni Arapski Emirati", "AF": "Avganistan",
    "AG": "Antigva i Barbuda", "AI": "Angvila", "AL": "Albanija", "AM": "Jermenija",
    "AO": "Angola", "AR": "Argentina", "AS": "Američka Samoa", "AT": "Austrija",
    "AU": "Australija", "AW": "Aruba", "AX": "Olandska Ostrva", "AZ": "Azerbejdžan",
    "BA": "Bosna i Hercegovina", "BB": "Barbados", "BD": "Bangladeš", "BE": "Belgija",
    "BF": "Burkina Faso", "BG": "Bugarska", "BH": "Bahrein", "BI": "Burundi",
    "BJ": "Benin", "BM": "Bermudi", "BN": "Brunej", "BO": "Bolivija", "BQ": "Bonaire",
    "BR": "Brazil", "BS": "Bahami", "BT": "Butan", "BW": "Bocvana", "BY": "Belorusija",
    "BZ": "Belize", "CA": "Kanada", "CD": "Demokratska Republika Kongo",
    "CF": "Centralnoafrička Republika", "CG": "Republika Kongo", "CH": "Švajcarska",
    "CI": "Obala Slonovače", "CK": "Kukova Ostrva", "CL": "Čile", "CM": "Kamerun",
    "CN": "Kina", "CO": "Kolumbija", "CR": "Kostarika", "CU": "Kuba",
    "CV": "Zelenortska Ostrva", "CW": "Kurasao", "CY": "Kipar", "CZ": "Češka",
    "DE": "Nemačka", "DJ": "Džibuti", "DK": "Danska", "DM": "Dominika",
    "DO": "Dominikanska Republika", "DZ": "Alžir", "EC": "Ekvador", "EE": "Estonija",
    "EG": "Egipat", "EH": "Zapadna Sahara", "ER": "Eritreja", "ES": "Španija",
    "ET": "Etiopija", "FI": "Finska", "FJ": "Fidži", "FK": "Foklandska Ostrva",
    "FM": "Mikronezija", "FO": "Farska Ostrva", "FR": "Francuska", "GA": "Gabon",
    "GD": "Grenada", "GE": "Gruzija", "GF": "Francuska Gvajana", "GH": "Gana",
    "GI": "Gibraltar", "GL": "Grenland", "GM": "Gambija", "GN": "Gvineja",
    "GP": "Gvadalupe", "GQ": "Ekvatorijalna Gvineja", "GR": "Grčka", "GT": "Gvatemala",
    "GU": "Guam", "GW": "Gvineja Bisao", "GY": "Gvajana", "HK": "Hongkong",
    "HN": "Honduras", "HR": "Hrvatska", "HT": "Haiti", "HU": "Mađarska",
    "ID": "Indonezija", "IE": "Irska", "IL": "Izrael", "IN": "Indija", "IQ": "Irak",
    "IR": "Iran", "IS": "Island", "IT": "Italija", "JM": "Jamajka", "JO": "Jordan",
    "JP": "Japan", "KE": "Kenija", "KG": "Kirgistan", "KH": "Kambodža", "KI": "Kiribati",
    "KM": "Komori", "KN": "Sveti Kits i Nevis", "KP": "Severna Koreja",
    "KR": "Južna Koreja", "KW": "Kuvajt", "KY": "Kajmanska Ostrva", "KZ": "Kazahstan",
    "LA": "Laos", "LB": "Liban", "LC": "Sveta Lucija", "LI": "Lihtenštajn",
    "LK": "Šri Lanka", "LR": "Liberija", "LS": "Lesoto", "LT": "Litvanija",
    "LU": "Luksemburg", "LV": "Letonija", "LY": "Libija", "MA": "Maroko", "MC": "Monako",
    "MD": "Moldavija", "ME": "Crna Gora", "MG": "Madagaskar", "MK": "Severna Makedonija",
    "ML": "Mali", "MM": "Mjanmar", "MN": "Mongolija", "MO": "Makao",
    "MP": "Severna Marijanska Ostrva", "MQ": "Martinik", "MR": "Mauritanija",
    "MS": "Monserat", "MT": "Malta", "MU": "Mauricijus", "MV": "Maldivi", "MW": "Malavi",
    "MX": "Meksiko", "MY": "Malezija", "MZ": "Mozambik", "NA": "Namibija",
    "NC": "Nova Kaledonija", "NE": "Niger", "NG": "Nigerija", "NI": "Nikaragva",
    "NL": "Holandija", "NO": "Norveška", "NP": "Nepal", "NR": "Nauru", "NU": "Niue",
    "NZ": "Novi Zeland", "OM": "Oman", "PA": "Panama", "PE": "Peru",
    "PF": "Francuska Polinezija", "PG": "Papua Nova Gvineja", "PH": "Filipini",
    "PK": "Pakistan", "PL": "Poljska", "PM": "Sen Pjer i Mikelon", "PR": "Portoriko",
    "PS": "Palestina", "PT": "Portugalija", "PW": "Palau", "PY": "Paragvaj",
    "QA": "Katar", "RE": "Reunion", "RO": "Rumunija", "RS": "Srbija", "RU": "Rusija",
    "RW": "Ruanda", "SA": "Saudijska Arabija", "SB": "Solomonska Ostrva",
    "SC": "Sejšeli", "SD": "Sudan", "SE": "Švedska", "SG": "Singapur",
    "SH": "Sveta Jelena", "SI": "Slovenija", "SK": "Slovačka", "SL": "Sijera Leone",
    "SM": "San Marino", "SN": "Senegal", "SO": "Somalija", "SR": "Surinam",
    "SS": "Južni Sudan", "ST": "Sao Tome i Principe", "SV": "Salvador",
    "SX": "Sint Marten", "SY": "Sirija", "SZ": "Esvatini", "TC": "Turks i Kaikos",
    "TD": "Čad", "TG": "Togo", "TH": "Tajland", "TJ": "Tadžikistan",
    "TL": "Istočni Timor", "TM": "Turkmenistan", "TN": "Tunis", "TO": "Tonga",
    "TR": "Turska", "TT": "Trinidad i Tobago", "TV": "Tuvalu", "TW": "Tajvan",
    "TZ": "Tanzanija", "UA": "Ukrajina", "UG": "Uganda", "UK": "Ujedinjeno Kraljevstvo",
    "US": "Sjedinjene Američke Države", "UY": "Urugvaj", "UZ": "Uzbekistan",
    "VA": "Vatikan", "VC": "Sveti Vincent i Grenadini", "VE": "Venecuela",
    "VG": "Britanska Devičanska Ostrva", "VI": "Američka Devičanska Ostrva",
    "VN": "Vijetnam", "VU": "Vanuatu", "WF": "Valis i Futuna", "WS": "Samoa",
    "XK": "Kosovo", "YE": "Jemen", "YT": "Majot", "ZA": "Južna Afrika", "ZM": "Zambija",
    "ZW": "Zimbabve",
}

TABLES = {"sr": SERBIAN}


def country_name(channel, language):
    """Naziv drzave stanice za prikaz; za jezik bez prevoda ostaje naziv iz kataloga."""
    return TABLES.get(language, {}).get(channel.country_code, channel.country_name)
