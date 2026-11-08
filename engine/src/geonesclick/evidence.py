"""Local rules: what the text of the marks proves, without asking the model to interpret.

The vision model transcribes; these rules conclude, each with its source:
1. the ALPHABET rules out the countries that do not write it (Cyrillic excludes France), a robust rule even when
   the model invents the words, since it does not change alphabet;
2. the LETTERS SPECIFIC to a language point to its countries ("ъ" before a consonant: Bulgarian);
3. PLACE NAMES (GeoNames directory, see places.py) point to a country.

A country is "certain" only with at least one place name AND another concurring proof, with no mark
pointing to another: measured on 2026-11-07, the model invented "Казань" on a blurry crop.

A LONE PLACE concludes nothing (decided with the user on 2026-11-07): measured the same day, lone places were
wrong 4 times (Gare → FR/LU, Laas → IT, Orion → PH/US, "Lo Manto" from a street name → Honduras, against
StreetCLIP at 96 % for Italy), whereas the right conclusions came from grouped places. A confirmation is
needed: a 2nd place, a letter or a word of the country's language, or StreetCLIP giving that country 10 % or more.
The words of a STREET NAME (after "via", "rue"… or before "utca", "street"…) are not places.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

WIKI = "https://en.wikipedia.org/wiki/"

# Alphabet → countries that write it on their signs (official or co-official script).
# Latin rules out nobody: it is found everywhere (transliterations, shop signs, brands).
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
MIN_SCRIPT_LETTERS = 2  # a single letter (symbol, misread reflection) is not enough to set an alphabet

_SPANISH = {"ES", "MX", "GT", "PA", "DO", "CO", "EC", "PE", "BO", "CL", "AR", "UY", "PY", "CR", "HN", "SV", "NI",
            "VE", "CU", "PR"}

# Letters specific to a language: (pattern, displayed letter, language, countries, source). Caution: a letter shared
# by several languages lists all their countries ("ā" is also Maori: not kept for Latvian).
LETTERS: list[tuple[str, str, str, set[str], str]] = [
    # In Russian, "ъ" only precedes е, ё, ю, я; in Bulgarian it is a vowel (Гърмен, България).
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

# Street and address words, as whole words ("utca": measured, the model concluded Slovakia from it). Common source:
# street names by language, https://en.wikipedia.org/wiki/Street_name and each language's articles.
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

# Words that announce a STREET NAME: the words that follow them ("Via Paolo Lo Manto", "Rue de Paris") or
# precede them ("Repkény utca", "Main Street") name the street, often after a person or another city:
# they do not locate the view. Normalised forms (lower case, without Latin accents), compared word by word.
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
# Languages that weld the word to the name (Mannerheimintie, Storgatan, Vesterbrogade): also recognised at the end
# of a word, preceded by at least 3 letters ("tie" alone would be English).
SUFFIXES = {"katu", "tie", "gatan", "vägen", "gade", "vej", "veien", "straße", "strasse", "straat", "iela", "tänav"}
WORDS.append(("tie", "finnois", {"FI"}))
_WORDS = [(re.compile(rf"(?<!\w)(?:\w{{3,}})?{re.escape(word)}(?!\w)" if word in SUFFIXES
                      else rf"(?<!\w){re.escape(word)}(?!\w)"), word, language, countries)
          for word, language, countries in WORDS]


@dataclass
class Evidence:
    kind: str  # "alphabet" (rules out), "lettres" or "mot" (language), "lieu" (place name), "rue" (does not count)
    value: str  # what was read: "ъ devant une consonne", "Благоевград"
    label: str  # what it means: "bulgare", "ville de Bulgarie"
    countries: list[str]
    source: str = ""
    km: float | None = None  # place: distance read right after the name (direction sign)
    points: list[list[Any]] = field(default_factory=list)  # place: namesakes as [latitude, longitude, country, name]
    note: str = ""  # why it does not count ("hors de tes pays candidats"), shown as is


def scripts_of(text: str) -> Counter[str]:
    """Number of letters of each script (first word of the Unicode name: CYRILLIC, LATIN, GREEK…)."""
    found: Counter[str] = Counter()
    for ch in text:
        if ch.isalpha():
            found[unicodedata.name(ch, "UNKNOWN").split()[0]] += 1
    return found


def text_evidence(lines: list[str]) -> list[Evidence]:
    """Alphabets and specific letters of a mark (place names are added by places.py)."""
    text = unicodedata.normalize("NFC", " ".join(lines))
    lower = text.lower()
    out = []
    for script, count in scripts_of(text).most_common():
        if script in SCRIPTS and count >= MIN_SCRIPT_LETTERS:
            label, countries, source = SCRIPTS[script]
            if not any(e.kind == "alphabet" and e.value == label for e in out):  # kana: hiragana + katakana
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
    """What the marks prove, all together."""

    country: str = ""
    level: str = ""  # "certain", "probable" (very likely) or "" (nothing stands out)
    allowed: list[str] | None = None  # countries the alphabet leaves possible; None: none ruled out
    scripts: list[str] = field(default_factory=list)  # alphabets read ("cyrillique")
    cites: list[dict[str, Any]] = field(default_factory=list)  # [{n, items}]: marks that prove it
    against: list[dict[str, Any]] = field(default_factory=list)  # [{n, country, items}]: contrary marks
    conflict: str = ""  # incompatible alphabets between marks
    unconfirmed: list[dict[str, Any]] = field(default_factory=list)  # [{n, value, country}]: lone places, clues


def verdict(marks: list[tuple[int, list[Evidence]]], prior: dict[str, float] | None = None,
            prior_min: float = 0.10) -> Verdict:
    """Combines the proofs of each mark (number, proofs) into a cautious conclusion.

    prior: StreetCLIP's probabilities (look of the view); a lone place is confirmed if its country reaches prior_min
    there.
    """
    v = Verdict()
    allowed: set[str] | None = None
    for _, evidence in marks:
        for e in evidence:
            if e.kind == "alphabet":
                if e.value not in v.scripts:
                    v.scripts.append(e.value)
                allowed = set(e.countries) if allowed is None else allowed & set(e.countries)
    if allowed is not None and not allowed:  # e.g. Greek on one mark, Cyrillic on the other
        v.conflict = f"alphabets incompatibles : {', '.join(v.scripts)}"
        allowed = None
    v.allowed = sorted(allowed) if allowed is not None else None

    # Proofs that point to ONE country (letter specific to a single country, unique place name), mark by mark.
    exclusive: dict[str, list[tuple[int, Evidence]]] = {}
    for n, evidence in marks:
        for e in evidence:
            if e.kind != "alphabet" and len(e.countries) == 1:
                exclusive.setdefault(e.countries[0], []).append((n, e))
    if allowed is not None:
        exclusive = {c: items for c, items in exclusive.items() if c in allowed}
    # Letters and words shared by several countries ("via": Italy, Switzerland): they confirm a place in one of them.
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
