"""Bounded, offline name-policy checks. This is not a legal-content classifier."""
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from django.core.exceptions import ValidationError

DATA = Path(__file__).parent / "data" / "name_moderation"
_RUSSIAN = str.maketrans(dict(zip(
    "абвгдеёжзийклмнопрстуфхцчшщъыьэюяіїєґ",
    ("a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u", "f", "kh", "ts", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya", "i", "yi", "ye", "g"),
)))
_CYRILLIC_LOOKALIKES = str.maketrans({"а":"a", "в":"b", "е":"e", "к":"k", "м":"m", "н":"h", "о":"o", "р":"p", "с":"c", "т":"t", "у":"y", "х":"x", "і":"i"})
_LATIN_LOOKALIKES = str.maketrans({"a":"а", "b":"в", "c":"с", "e":"е", "h":"н", "k":"к", "m":"м", "o":"о", "p":"р", "t":"т", "x":"х", "y":"у"})
_DIGITS = str.maketrans({"0":"o", "1":"i", "3":"e", "4":"a", "5":"s", "7":"t", "8":"b", "9":"g"})
_RUSSIAN_DIGITS = str.maketrans({"0":"o", "1":"i", "3":"z", "4":"a", "5":"s", "6":"b", "7":"t", "8":"b"})
_WORDS = re.compile(r"[a-z0-9]+")
_LETTERS = re.compile(r"[a-z]+")
_REPEATS = re.compile(r"([a-z])\1{2,}")


def _fold(value):
    value = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", value).casefold())
    return "".join(char for char in value if not unicodedata.category(char).startswith(("M", "C")))


def _compact(value):
    return "".join(_WORDS.findall(value.translate(_RUSSIAN)))


def _alternatives(value):
    folded = _fold(value)
    variants = {folded, folded.translate(_CYRILLIC_LOOKALIKES), folded.translate(_LATIN_LOOKALIKES)}
    result = set()
    for variant in variants:
        for candidate in (variant, variant.translate(_DIGITS), variant.translate(_RUSSIAN_DIGITS)):
            latin = candidate.translate(_RUSSIAN)
            result.add(latin)
            result.add(_REPEATS.sub(r"\1", latin))
    return result


def _literal_pattern(terms):
    choices = [re.escape(term) for term in sorted(terms, key=lambda item: (-len(item), item)) if term]
    return "(?:" + "|".join(choices) + ")" if choices else r"(?!)"


@lru_cache(maxsize=1)
def _rules():
    policy = json.loads((DATA / "policy.json").read_text(encoding="utf-8"))
    excluded = {_compact(_fold(term)) for term in policy["excluded_source_terms"]}
    terms = set()
    for language in ("ru", "en"):
        for line in (DATA / f"ldnoobw-{language}.txt").read_text(encoding="utf-8").splitlines():
            term = _compact(_fold(line))
            if term and term not in excluded:
                terms.add(term)
    terms.update(_compact(_fold(term)) for term in policy["extra_terms"])
    # Shorter ambiguous stems are prefix-only: e.g. Esteban must not match eban.
    stems = set(policy["compound_stems"])
    bounded = stems & {"eban", "ebet", "khuy", "khui", "huy"}
    embedded = re.compile(_literal_pattern(stems-bounded))
    prefixed = re.compile(r"(?:super|mega|ultra|real|the|racer|pilot|f1|max|maks)?" + _literal_pattern(bounded) + r"[a-z0-9]*")
    identities = {_compact(_fold(term)) for term in policy["policy_identities"]}
    identity = re.compile(r"(?:real|the|official|president|racer|pilot|f1|fan)?" + _literal_pattern(identities)
        + r"(?:fan|pilot|racer|f1)?[0-9]*")
    return re.compile(_literal_pattern(terms)), embedded, prefixed, identity


def validate_public_name(value):
    """Reject prohibited spellings without changing a legitimate stored name."""
    if not isinstance(value, str) or len(value) > 150:
        raise ValidationError("Слишком длинное имя или логин.", code="name_too_long")
    words, embedded, prefixed, identity = _rules()
    for alternative in _alternatives(value):
        compact = _compact(alternative)
        candidates = {compact, compact.strip("0123456789")}
        candidates.update(_WORDS.findall(alternative))
        candidates.update(_LETTERS.findall(alternative))
        if any(words.fullmatch(candidate) or identity.fullmatch(candidate) for candidate in candidates if candidate):
            raise ValidationError("Это имя или логин не соответствует правилам Fastlap. Выберите другой вариант.", code="name_not_allowed")
        if compact and (embedded.search(compact) or prefixed.fullmatch(compact)):
            raise ValidationError("Это имя или логин не соответствует правилам Fastlap. Выберите другой вариант.", code="name_not_allowed")
