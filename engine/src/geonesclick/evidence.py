"""Règles locales : ce que le texte des marques prouve, sans demander au modèle d'interpréter.

Le modèle de vision transcrit ; ces règles concluent, chacune avec sa source :
1. l'ALPHABET écarte les pays qui ne l'écrivent pas (du cyrillique exclut la France), règle robuste même quand
   le modèle invente les mots, car il ne change pas d'alphabet ;
2. les LETTRES PROPRES à une langue désignent ses pays (« ъ » devant une consonne : bulgare) ;
3. les NOMS DE LIEUX (répertoire GeoNames, voir places.py) désignent un pays.

Un pays n'est « certain » qu'avec au moins un nom de lieu ET une autre preuve concordante, sans aucune marque qui
en désigne un autre : mesuré le 2026-11-07, le modèle a inventé « Казань » sur une découpe floue.

Un LIEU SEUL ne conclut rien (décidé avec l'utilisateur le 2026-11-07) : mesuré le même jour, les lieux seuls se
sont trompés 4 fois (Gare → FR/LU, Laas → IT, Orion → PH/US, « Lo Manto » d'un nom de rue → Honduras, contre
StreetCLIP à 96 % pour l'Italie), alors que les conclusions justes venaient de lieux groupés. Il faut une
confirmation : un 2ᵉ lieu, une lettre ou un mot de la langue du pays, ou StreetCLIP qui donne ce pays à 10 % ou plus.
Les mots d'un NOM DE RUE (après « via », « rue »… ou avant « utca », « street »…) ne sont pas des lieux.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

WIKI = "https://en.wikipedia.org/wiki/"

# Alphabet → pays qui l'écrivent sur leurs panneaux (écriture officielle ou co-officielle).
# Le latin n'écarte personne : on le trouve partout (translittérations, enseignes, marques).
SCRIPTS: dict[str, tuple[str, set[str], str]] = {
    "CYRILLIC": ("cyrillique", {"RU", "UA", "BY", "BG", "RS", "MK", "ME", "BA", "KZ", "KG", "MN", "TJ"},
                 WIKI + "Cyrillic_script"),
    "GREEK": ("grec", {"GR", "CY"}, WIKI + "Greek_alphabet"),
    "HEBREW": ("hébreu", {"IL"}, WIKI + "Hebrew_alphabet"),
    "ARABIC": ("arabe", {"AE", "JO", "TN", "IL", "QA", "LB", "OM", "EG", "MA", "SA", "DZ", "IQ", "KW", "BH", "PS",
                         "PK", "AF", "IR"}, WIKI + "Arabic_script"),
    "THAI": ("thaï", {"TH"}, WIKI + "Thai_script"),
    "HANGUL": ("hangeul", {"KR"}, WIKI + "Hangul"),
    "HIRAGANA": ("kana", {"JP"}, WIKI + "Kana"),
    "KATAKANA": ("kana", {"JP"}, WIKI + "Kana"),
    "CJK": ("sinogrammes", {"JP", "TW", "CN", "HK", "MO", "SG"}, WIKI + "Chinese_characters"),
    "KHMER": ("khmer", {"KH"}, WIKI + "Khmer_script"),
    "LAO": ("lao", {"LA"}, WIKI + "Lao_script"),
    "SINHALA": ("cinghalais", {"LK"}, WIKI + "Sinhala_script"),
    "TAMIL": ("tamoul", {"LK", "IN", "SG", "MY"}, WIKI + "Tamil_script"),
    "BENGALI": ("bengali", {"BD", "IN"}, WIKI + "Bengali%E2%80%93Assamese_script"),
    "DEVANAGARI": ("devanagari", {"IN", "NP"}, WIKI + "Devanagari"),
    "GURMUKHI": ("gurmukhi", {"IN"}, WIKI + "Gurmukhi"),
    "GUJARATI": ("gujarati", {"IN"}, WIKI + "Gujarati_script"),
    "KANNADA": ("kannada", {"IN"}, WIKI + "Kannada_script"),
    "TELUGU": ("télougou", {"IN"}, WIKI + "Telugu_script"),
    "MALAYALAM": ("malayalam", {"IN"}, WIKI + "Malayalam_script"),
    "ORIYA": ("odia", {"IN"}, WIKI + "Odia_script"),
    "TIBETAN": ("tibétain", {"BT", "CN", "IN", "NP"}, WIKI + "Tibetan_script"),
    "GEORGIAN": ("géorgien", {"GE"}, WIKI + "Georgian_scripts"),
    "ARMENIAN": ("arménien", {"AM"}, WIKI + "Armenian_alphabet"),
    "ETHIOPIC": ("guèze", {"ET", "ER"}, WIKI + "Ge%CA%BDez_script"),
    "MYANMAR": ("birman", {"MM"}, WIKI + "Burmese_alphabet"),
    "THAANA": ("thâna", {"MV"}, WIKI + "Thaana"),
}
MIN_SCRIPT_LETTERS = 2  # une lettre isolée (symbole, reflet mal lu) ne suffit pas à fixer un alphabet

_SPANISH = {"ES", "MX", "GT", "PA", "DO", "CO", "EC", "PE", "BO", "CL", "AR", "UY", "PY", "CR", "HN", "SV", "NI",
            "VE", "CU", "PR"}

# Lettres propres à une langue : (motif, lettre affichée, langue, pays, source). Prudence : une lettre partagée
# par plusieurs langues liste tous leurs pays (« ā » est aussi maori : pas retenu pour le letton).
LETTERS: list[tuple[str, str, str, set[str], str]] = [
    # En russe, « ъ » ne précède que е, ё, ю, я ; en bulgare c'est une voyelle (Гърмен, България).
    (r"ъ(?=[бвгджзйклмнпрстфхцчшщ])", "ъ devant une consonne", "bulgare", {"BG"}, WIKI + "Bulgarian_alphabet"),
    (r"[ыэ]", "ы, э", "russe ou langue d'Asie centrale", {"RU", "BY", "KZ", "KG", "MN"}, WIKI + "Yery"),
    (r"[їєґ]", "ї, є, ґ", "ukrainien", {"UA"}, WIKI + "Ukrainian_alphabet"),
    (r"[ђћ]", "ђ, ћ", "serbe", {"RS", "ME", "BA"}, WIKI + "Serbian_Cyrillic_alphabet"),
    (r"[ѓќѕ]", "ѓ, ќ, ѕ", "macédonien", {"MK"}, WIKI + "Macedonian_alphabet"),
    (r"[өү]", "ө, ү", "kirghize, kazakh ou mongol", {"KG", "KZ", "MN"}, WIKI + "Kyrgyz_alphabets"),
    (r"[őű]", "ő, ű", "hongrois", {"HU"}, WIKI + "Hungarian_alphabet"),
    (r"[șțţ]", "ș, ț", "roumain", {"RO", "MD"}, WIKI + "Romanian_alphabet"),
    (r"[łżśźń]", "ł, ż, ś, ź, ń", "polonais", {"PL"}, WIKI + "Polish_alphabet"),
    (r"[řůě]", "ř, ů, ě", "tchèque", {"CZ"}, WIKI + "Czech_orthography"),
    (r"[ľĺŕ]", "ľ, ĺ, ŕ", "slovaque", {"SK"}, WIKI + "Slovak_orthography"),
    (r"[ėįų]", "ė, į, ų", "lituanien", {"LT"}, WIKI + "Lithuanian_orthography"),
    (r"[ģķļņ]", "ģ, ķ, ļ, ņ", "letton", {"LV"}, WIKI + "Latvian_orthography"),
    (r"[ğı]", "ğ, ı", "turc", {"TR"}, WIKI + "Turkish_alphabet"),
    (r"ß", "ß", "allemand", {"DE", "AT", "LU"}, WIKI + "%C3%9F"),
    (r"[þð]", "þ, ð", "islandais", {"IS"}, WIKI + "Icelandic_orthography"),
    (r"[øæ]", "ø, æ", "danois ou norvégien", {"DK", "NO"}, WIKI + "Danish_and_Norwegian_alphabet"),
    (r"õ", "õ", "estonien ou portugais", {"EE", "PT", "BR"}, WIKI + "%C3%95"),
    (r"[ươẠ-ỹ]", "ư, ơ, ạ…", "vietnamien", {"VN"}, WIKI + "Vietnamese_alphabet"),
    (r"ñ", "ñ", "espagnol", _SPANISH, WIKI + "%C3%91"),
]
_LETTERS = [(re.compile(p), *rest) for p, *rest in LETTERS]

# Mots de rue et d'adresse, en mot entier (« utca » : mesuré, le modèle en a conclu Slovaquie). Source commune :
# les noms de voies par langue, https://en.wikipedia.org/wiki/Street_name et les articles de chaque langue.
WORDS: list[tuple[str, str, set[str]]] = [
    ("utca", "hongrois", {"HU"}),
    ("út", "hongrois", {"HU"}),
    ("iela", "letton", {"LV"}),
    ("gatvė", "lituanien", {"LT"}),
    ("katu", "finnois", {"FI"}),
    ("gatan", "suédois", {"SE"}),
    ("vägen", "suédois", {"SE"}),
    ("gade", "danois", {"DK"}),
    ("vej", "danois", {"DK"}),
    ("veien", "norvégien", {"NO"}),
    ("gata", "suédois, norvégien ou islandais", {"SE", "NO", "IS"}),
    ("tänav", "estonien", {"EE"}),
    ("ulica", "langue slave occidentale ou du Sud", {"PL", "SK", "HR", "SI", "RS", "BA", "ME"}),
    ("ulice", "tchèque", {"CZ"}),
    ("straße", "allemand", {"DE", "AT", "CH", "LU"}),
    ("strasse", "allemand", {"DE", "AT", "CH", "LU"}),
    ("straat", "néerlandais", {"NL", "BE"}),
    ("strada", "roumain ou italien", {"RO", "MD", "IT"}),
    ("sokak", "turc", {"TR"}),
    ("sokağı", "turc", {"TR"}),
    ("caddesi", "turc", {"TR"}),
    ("rruga", "albanais", {"AL"}),
    ("вулиця", "ukrainien", {"UA"}),
    ("улица", "russe, bulgare, macédonien ou serbe", {"RU", "BY", "KZ", "KG", "BG", "MK", "RS"}),
    ("via", "italien", {"IT", "CH", "SM", "VA"}),
    ("viale", "italien", {"IT", "CH", "SM"}),
    ("piazza", "italien", {"IT", "CH", "SM"}),
    ("vicolo", "italien", {"IT", "CH", "SM"}),
    ("rue", "français", {"FR", "BE", "CH", "LU", "MC", "CA"}),
    ("calle", "espagnol", _SPANISH),
    ("plaza", "espagnol", _SPANISH),
    ("rua", "portugais", {"PT", "BR"}),
]

# Mots qui annoncent un NOM DE RUE : les mots qui les suivent (« Via Paolo Lo Manto », « Rue de Paris ») ou les
# précèdent (« Repkény utca », « Main Street ») nomment la rue, souvent d'après une personne ou une autre ville :
# ils ne situent pas la vue. Formes normalisées (minuscules, sans accents latins), comparées mot à mot.
STREET_BEFORE = {
    "via", "viale", "vicolo", "piazza", "piazzale", "corso", "largo", "rue", "avenue", "boulevard", "place", "chemin",
    "allee", "impasse", "quai", "calle", "avenida", "avda", "plaza", "paseo", "carrer", "rua", "travessa", "praca",
    "strada", "bulevardul", "ulica", "ul", "ulice", "namesti", "trg", "plac", "aleja", "улица", "ул", "бульвар",
    "проспект", "вулиця", "вул", "площа", "οδος", "λεωφορος",
}
STREET_AFTER = {
    "utca", "ut", "ter", "iela", "gatve", "tanav", "gatan", "vagen", "gade", "vej", "veien", "gata", "strasse",
    "straat", "weg", "laan", "sokak", "sokagi", "caddesi", "street", "road", "lane", "drive", "avenue",
}
# Langues qui soudent le mot au nom (Mannerheimintie, Storgatan, Vesterbrogade) : aussi reconnu en fin de mot,
# précédé d'au moins 3 lettres (« tie » seul serait l'anglais).
SUFFIXES = {"katu", "tie", "gatan", "vägen", "gade", "vej", "veien", "straße", "strasse", "straat", "iela", "tänav"}
WORDS.append(("tie", "finnois", {"FI"}))
_WORDS = [(re.compile(rf"(?<!\w)(?:\w{{3,}})?{re.escape(word)}(?!\w)" if word in SUFFIXES
                      else rf"(?<!\w){re.escape(word)}(?!\w)"), word, language, countries)
          for word, language, countries in WORDS]


@dataclass
class Evidence:
    kind: str  # "alphabet" (écarte), "lettres" ou "mot" (langue), "lieu" (nom de lieu), "rue" (ne compte pas)
    value: str  # ce qui a été lu : « ъ devant une consonne », « Благоевград »
    label: str  # ce que ça veut dire : « bulgare », « ville de Bulgarie »
    countries: list[str]
    source: str = ""
    km: float | None = None  # lieu : distance lue juste après le nom (panneau directionnel)
    points: list[list[Any]] = field(default_factory=list)  # lieu : [latitude, longitude, pays, nom] des homonymes
    note: str = ""  # pourquoi elle ne compte pas (« hors de tes pays candidats »), affiché tel quel


def scripts_of(text: str) -> Counter[str]:
    """Nombre de lettres de chaque écriture (premier mot du nom Unicode : CYRILLIC, LATIN, GREEK…)."""
    found: Counter[str] = Counter()
    for ch in text:
        if ch.isalpha():
            found[unicodedata.name(ch, "UNKNOWN").split()[0]] += 1
    return found


def text_evidence(lines: list[str]) -> list[Evidence]:
    """Alphabets et lettres propres d'une marque (les noms de lieux sont ajoutés par places.py)."""
    text = unicodedata.normalize("NFC", " ".join(lines))
    lower = text.lower()
    out = []
    for script, count in scripts_of(text).most_common():
        if script in SCRIPTS and count >= MIN_SCRIPT_LETTERS:
            label, countries, source = SCRIPTS[script]
            if not any(e.kind == "alphabet" and e.value == label for e in out):  # kana : hiragana + katakana
                out.append(Evidence("alphabet", label, f"alphabet {label}", sorted(countries), source))
    for pattern, shown, language, countries, source in _LETTERS:
        if pattern.search(lower):
            out.append(Evidence("lettres", shown, language, sorted(countries), source))
    for pattern, word, language, countries in _WORDS:
        found = pattern.search(lower)
        if found and not (word == "tie" and found.group() == "tie"):
            out.append(Evidence("mot", word, language, sorted(countries), WIKI + "Street_name"))
    return out


@dataclass
class Verdict:
    """Ce que les marques prouvent, toutes ensemble."""

    country: str = ""
    level: str = ""  # "certain", "probable" (très probable) ou "" (rien ne se détache)
    allowed: list[str] | None = None  # pays que l'alphabet laisse possibles ; None : aucun écarté
    scripts: list[str] = field(default_factory=list)  # alphabets lus (« cyrillique »)
    cites: list[dict[str, Any]] = field(default_factory=list)  # [{n, items}] : marques qui le prouvent
    against: list[dict[str, Any]] = field(default_factory=list)  # [{n, country, items}] : marques contraires
    conflict: str = ""  # alphabets incompatibles entre marques
    unconfirmed: list[dict[str, Any]] = field(default_factory=list)  # [{n, value, country}] : lieux seuls, indices


def verdict(marks: list[tuple[int, list[Evidence]]], prior: dict[str, float] | None = None,
            prior_min: float = 0.10) -> Verdict:
    """Combine les preuves de chaque marque (numéro, preuves) en une conclusion prudente.

    prior : probabilités de StreetCLIP (allure de la vue) ; un lieu seul est confirmé si son pays y atteint prior_min.
    """
    v = Verdict()
    allowed: set[str] | None = None
    for _, evidence in marks:
        for e in evidence:
            if e.kind == "alphabet":
                if e.value not in v.scripts:
                    v.scripts.append(e.value)
                allowed = set(e.countries) if allowed is None else allowed & set(e.countries)
    if allowed is not None and not allowed:  # ex. grec sur une marque, cyrillique sur l'autre
        v.conflict = f"alphabets incompatibles : {', '.join(v.scripts)}"
        allowed = None
    v.allowed = sorted(allowed) if allowed is not None else None

    # Preuves qui désignent UN pays (lettre propre à un seul pays, nom de lieu unique), marque par marque.
    exclusive: dict[str, list[tuple[int, Evidence]]] = {}
    for n, evidence in marks:
        for e in evidence:
            if e.kind != "alphabet" and len(e.countries) == 1:
                exclusive.setdefault(e.countries[0], []).append((n, e))
    if allowed is not None:
        exclusive = {c: items for c, items in exclusive.items() if c in allowed}
    # Lettres et mots partagés par plusieurs pays (« via » : Italie, Suisse) : ils confirment un lieu de l'un d'eux.
    shared = {c for _, evidence in marks for e in evidence
              if e.kind in ("lettres", "mot") and len(e.countries) > 1 for c in e.countries}

    def confirmed(country: str, support: list[tuple[int, Evidence]]) -> bool:
        places = sum(1 for _, e in support if e.kind == "lieu")
        return (places < len(support) or places >= 2 or country in shared
                or (prior or {}).get(country, 0.0) >= prior_min)

    concluded = {c: items for c, items in exclusive.items() if confirmed(c, items)}
    if not concluded:
        v.unconfirmed = [{"n": n, "value": e.value, "country": c}
                         for c, items in exclusive.items() for n, e in items]
        return v
    country = max(concluded, key=lambda c: (len(concluded[c]), any(e.kind == "lieu" for _, e in concluded[c])))
    support = concluded[country]
    v.country = country
    for n in sorted({n for n, _ in support}):
        v.cites.append({"n": n, "items": [e.value for m, e in support if m == n]})
    for other, items in exclusive.items():
        if other != country:
            for n in sorted({n for n, _ in items}):
                v.against.append({"n": n, "country": other, "items": [e.value for m, e in items if m == n]})
    has_place = any(e.kind == "lieu" for _, e in support)
    v.level = "certain" if has_place and len(support) >= 2 and not v.against else "probable"
    return v


def as_dict(items: list[Evidence]) -> list[dict[str, Any]]:
    return [asdict(e) for e in items]


def from_dict(items: list[dict[str, Any]]) -> list[Evidence]:
    return [Evidence(**e) for e in items]
