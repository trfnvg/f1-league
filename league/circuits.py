"""Circuit catalogue shared by the event editor and server-rendered SVGs.

Paths are local, simplified geographic outlines: no map API, remote asset or
client-side geometry calculation is needed to display a circuit.
"""
import json
import math
import re
import unicodedata
from functools import lru_cache
from pathlib import Path


# key, GeoJSON id, GP label, short location, country, aliases for existing cards.
_DEFINITIONS = (
    ("melbourne", "au-1953", "Гран-при Австралии", "Мельбурн", "AUSTRALIA / AU", ("австрали", "мельбурн", "australi", "melbourne", "albert park")),
    ("shanghai", "cn-2004", "Гран-при Китая", "Шанхай", "CHINA / CN", ("кита", "шанха", "chin", "shanghai")),
    ("suzuka", "jp-1962", "Гран-при Японии", "Судзука", "JAPAN / JP", ("япони", "судзук", "сузук", "japan", "suzuka")),
    ("bahrain", "bh-2002", "Гран-при Бахрейна", "Сахир", "BAHRAIN / BH", ("бахрейн", "сахир", "bahrain", "sakhir")),
    ("jeddah", "sa-2021", "Гран-при Саудовской Аравии", "Джидда", "SAUDI ARABIA / SA", ("саудов", "джидд", "saudi", "jeddah")),
    ("miami", "us-2022", "Гран-при Майами", "Майами", "MIAMI / US", ("майами", "miami")),
    ("montreal", "ca-1978", "Гран-при Канады", "Монреаль", "CANADA / CA", ("канад", "монреал", "canad", "montreal", "gilles villeneuve")),
    ("monaco", "mc-1929", "Гран-при Монако", "Монако", "MONACO / MC", ("монако", "monaco", "monte carlo")),
    ("barcelona", "es-1991", "Гран-при Барселоны-Каталуньи", "Барселона", "BARCELONA / ES", ("барселон", "каталун", "barcelona", "catalunya")),
    ("spielberg", "at-1969", "Гран-при Австрии", "Шпильберг", "AUSTRIA / AT", ("австри", "шпильберг", "austri", "spielberg", "red bull ring")),
    ("silverstone", "gb-1948", "Гран-при Великобритании", "Сильверстоун", "GREAT BRITAIN / GB", ("великобрит", "британ", "сильверсто", "british", "great britain", "silverstone")),
    ("spa", "be-1925", "Гран-при Бельгии", "Спа", "BELGIUM / BE", ("бельги", "спа", "belgi", "spa francorchamps")),
    ("hungaroring", "hu-1986", "Гран-при Венгрии", "Будапешт", "HUNGARY / HU", ("венгр", "будапешт", "хунгароринг", "hungar", "budapest")),
    ("zandvoort", "nl-1948", "Гран-при Нидерландов", "Зандворт", "NETHERLANDS / NL", ("нидерланд", "голланд", "зандворт", "netherland", "dutch", "zandvoort")),
    ("monza", "it-1922", "Гран-при Италии", "Монца", "ITALY / IT", ("италии", "монц", "italian", "italy", "monza")),
    ("madrid", "es-2026", "Гран-при Испании", "Мадрид", "MADRID / ES", ("мадрид", "madrid", "madring", "испан", "spanish", "spain")),
    ("baku", "az-2016", "Гран-при Азербайджана", "Баку", "AZERBAIJAN / AZ", ("азербайджан", "баку", "azerbaijan", "baku")),
    ("singapore", "sg-2008", "Гран-при Сингапура", "Сингапур", "SINGAPORE / SG", ("сингапур", "singapore", "marina bay")),
    ("austin", "us-2012", "Гран-при США", "Остин", "UNITED STATES / US", ("сша", "остин", "austin", "united states", "americas", "usa")),
    ("mexico", "mx-1962", "Гран-при Мехико", "Мехико", "MEXICO / MX", ("мексик", "мехико", "mexic", "hermanos")),
    ("interlagos", "br-1940", "Гран-при Сан-Паулу", "Сан-Паулу", "BRAZIL / BR", ("бразил", "сан паулу", "интерлагос", "brazil", "sao paulo", "interlagos")),
    ("las-vegas", "us-2023", "Гран-при Лас-Вегаса", "Лас-Вегас", "LAS VEGAS / US", ("лас вегас", "las vegas")),
    ("lusail", "qa-2004", "Гран-при Катара", "Лусаил", "QATAR / QA", ("катар", "лусаил", "лосаи", "лосаил", "qatar", "lusail", "losail")),
    ("yas-marina", "ae-2009", "Гран-при Абу-Даби", "Абу-Даби", "ABU DHABI / AE", ("абу даби", "яс марин", "yas marina", "abu dhabi")),
    ("imola", "it-1953", "Гран-при Эмилии-Романьи", "Имола", "IMOLA / IT", ("эмиль", "эмили", "имол", "imola", "emilia", "san marino")),
    ("portimao", "pt-2008", "Гран-при Португалии", "Портиман", "PORTUGAL / PT", ("португал", "портима", "portugal", "portimao")),
    ("istanbul", "tr-2005", "Гран-при Турции", "Стамбул", "TURKEY / TR", ("турци", "стамбул", "турец", "turk", "istanbul")),
)

_GEOMETRIES = json.loads((Path(__file__).parent / "data" / "circuits.json").read_text(encoding="utf-8"))
CIRCUITS = {
    key: {"key": key, "source_id": source_id, "grand_prix": gp,
          "location": location, "country": country, "aliases": aliases,
          **_GEOMETRIES[key]}
    for key, source_id, gp, location, country, aliases in _DEFINITIONS
}
CIRCUIT_CHOICES = [(key, f"{value['grand_prix']} — {value['name']}") for key, value in CIRCUITS.items()]


def _map_annotations(circuit):
    """Schematic sector labels, not authoritative FIA timing-line positions."""
    points = [(float(x), float(y)) for x, y in re.findall(r"[ML]([\d.]+),([\d.]+)", circuit["path"])]
    distances = [math.dist(a, b) for a, b in zip(points, points[1:])]
    length = sum(distances)
    center = (sum(x for x, _ in points) / len(points), sum(y for _, y in points) / len(points))

    def label_at(point, text):
        dx, dy = point[0] - center[0], point[1] - center[1]
        norm = math.hypot(dx, dy) or 1
        return {"text": text, "x": round(max(25, min(595, point[0] + 28 * dx / norm)), 1),
                "y": round(max(18, min(352, point[1] + 28 * dy / norm)), 1)}

    labels = []
    for index, fraction in enumerate((.18, .5, .82), 1):
        remaining = length * fraction
        for a, b, distance in zip(points, points[1:], distances):
            if remaining <= distance and distance:
                ratio = remaining / distance
                point = (a[0] + (b[0] - a[0]) * ratio, a[1] + (b[1] - a[1]) * ratio)
                labels.append(label_at(point, f"S{index}"))
                break
            remaining -= distance
    return {"start_label": label_at((circuit["start_x"], circuit["start_y"]), "START"), "sector_labels": labels}


for _circuit in CIRCUITS.values():
    _circuit.update(_map_annotations(_circuit))


def _normalise(value):
    value = unicodedata.normalize("NFKD", value.lower().replace("ё", "е"))
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^\w]+", " ", value).strip()


def _contains(alias, name):
    alias = _normalise(alias)
    return bool(re.search(r"\b" + re.escape(alias) + r"\b", name)) if len(alias) <= 3 else alias in name


@lru_cache(maxsize=512)
def resolve_circuit(key="", event_name="", season_year=None):
    """Explicit selection wins; match old cards by name, never by round number."""
    if key in CIRCUITS:
        return CIRCUITS[key]
    name = _normalise(event_name)
    # Barcelona was the Spanish GP before Madrid's introduction. Explicit city
    # matches take priority over the generic country alias in either season.
    for circuit in CIRCUITS.values():
        if _contains(circuit["location"], name):
            return circuit
    matches = []
    for circuit in CIRCUITS.values():
        for alias in circuit["aliases"]:
            if alias in ("испан", "spanish", "spain"):
                continue
            alias = _normalise(alias)
            # Short names such as SPA must not match SPAnish / иСПАнии.
            matched = _contains(alias, name)
            if matched:
                matches.append((len(alias), circuit))
    if matches:
        return max(matches, key=lambda match: match[0])[1]
    if any(alias in name for alias in ("испан", "spanish", "spain")):
        return CIRCUITS["barcelona" if season_year and season_year < 2026 else "madrid"]
    return None
