import pytest

from ekml.extract import canonical_value, extract
from ekml.llm import _parse, llm_attributes
from ekml.normalize import normalize, normalize_uom, set_abbreviations, to_number
from ekml.standardize import standard_description


@pytest.fixture(autouse=True)
def seed_dictionary():
    """Every test runs on the shipped YAML dictionary, whatever an earlier test or the DB loaded."""
    set_abbreviations({})
    yield
    set_abbreviations({})


def attrs(text: str) -> dict:
    return extract(normalize(text))[0]


# ---- normalize ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("SS HX BLT M12 L50", "stainless steel hexagonal bolt m12 l 50"),
    ("HEX BOLT M12X50", "hexagonal bolt m12 x 50"),
    ("S.S.304 HEX NUT", "stainless steel 304 hexagonal nut"),
    ("SCH-40", "schedule 40"),
    ("PIPE 50NB", "pipe 50 nominal bore"),
    ('1/2"', "0.5 in"),
    ('1-1/2"', "1.5 in"),
    ("2 INCH", "2 in"),
    ("3/4 in", "0.75 in"),
    ("", ""),
])
def test_normalize(raw, expected):
    assert normalize(raw) == expected


def test_normalize_none():
    assert normalize(None) == ""


@pytest.mark.parametrize("raw,expected", [
    ("NOS", "C62"), ("No.", "C62"), ("ea", "C62"), ("PCS", "C62"), ("Mtrs", "MTR"), ("KGS", "KGM"), ("set", "SET"),
    ("BOX", "BOX"), (None, None), ("", None),
])
def test_uom_maps_to_unece_rec20(raw, expected):
    assert normalize_uom(raw) == expected


@pytest.mark.parametrize("raw,expected", [("1-1/2", 1.5), ("1 1/2", 1.5), ("3/4", 0.75), ("2.5", 2.5), ("12", 12)])
def test_to_number(raw, expected):
    assert to_number(raw) == expected


def test_dictionary_override_and_reset():
    set_abbreviations({"zz": "shielded", "hx": "hexagonal"})
    assert normalize("ZZ HX") == "shielded hexagonal"
    assert normalize("SS") == "ss"                              # the override replaces the whole dictionary
    set_abbreviations({})
    assert normalize("SS") == "stainless steel"
    set_abbreviations(None)                                     # None also means "the shipped YAML"
    assert normalize("BLT") == "bolt"


def test_plurals_are_singular():
    assert normalize("STUDS GASKETS VALVES") == "stud gasket valve"


# ---- extract -----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("HEX BOLT M12X50 SS304", {"noun": "BOLT", "thread": "12", "length_mm": "50", "grade": "SS304"}),
    ("SS HX BLT M12 L50", {"noun": "BOLT", "thread": "12", "length_mm": "50"}),
    ("Bolt hexagonal SS 12x50mm", {"noun": "BOLT", "thread": "12", "length_mm": "50"}),
    ("STUD BOLT M16 X 90 A193 B7", {"noun": "STUD BOLT", "thread": "16", "length_mm": "90", "grade": "A193B7"}),
    ("BOLT,STUD,M16X90,ASTM A193 GR B7", {"noun": "STUD BOLT", "thread": "16", "length_mm": "90", "grade": "A193B7"}),
    ("HEX BOLT FOR FLANGE M12X50", {"noun": "BOLT", "thread": "12", "length_mm": "50"}),
    ('GASKET SPWD 4" 300# SS316L', {"noun": "GASKET", "size_in": "4", "rating": "300", "grade": "SS316L"}),
    ('FLANGE GASKET 2" CL150', {"noun": "GASKET", "size_in": "2", "rating": "150"}),
    ("PIPE 50 NB SCH 40 SMLS A106 GR.B", {"noun": "PIPE", "size_in": "2", "schedule": "40", "grade": "A106B"}),
    ('GATE VALVE 1-1/2" 800# API 602', {"noun": "GATE VALVE", "size_in": "1.5", "rating": "800", "standard": "API602"}),
    ("VALVE,GATE,50NB,CL150,BODY A105,API600",
     {"noun": "GATE VALVE", "size_in": "2", "rating": "150", "grade": "A105", "standard": "API600"}),
    ("BALL VALVE DN 100 API 6D", {"noun": "BALL VALVE", "size_in": "4", "standard": "API6D"}),
    ("BEARING 6205-2RS C3", {"noun": "BEARING", "bearing_no": "62052RSC3"}),
    ("CABLE 3.5C X 95 SQMM AL XLPE ARM 1.1KV",
     {"noun": "CABLE", "cores": "3.5", "area_sqmm": "95", "voltage": "1.1KV", "conductor": "ALUMINIUM"}),
    ("SPIRAL WOUND GASKET 4 IN 300# SS316 ASME B16.20", {"standard": "B16.20"}),
    ('SPWD GSKT 4" 300# SS316 B16.20', {"standard": "B16.20"}),
    # "150 1/2" must not become 150.5 inches
    ("GATE VALVE CL150 1/2 IN", {"noun": "GATE VALVE", "size_in": "0.5", "rating": "150"}),
    ('PIPE 2" SCH 40 L=6M A106B', {"size_in": "2", "length_mm": "6000"}),
    ('PIPE 2" SCH 40 L 6000MM A106B', {"length_mm": "6000", "size_mm": None}),
    ("BALL VALVE DN 100 PN16", {"size_in": "4", "rating": "PN16"}),
    ("STUDS M16X90 A193 B7", {"noun": "STUD BOLT", "thread": "16", "grade": "A193B7"}),
])
def test_extract(text, expected):
    got = attrs(text)
    assert {k: got.get(k) for k in expected} == expected, got


def test_bolt_length_is_not_a_size():
    assert "size_mm" not in attrs("HEX BOLT M12 X 50MM SS304")


def test_bearing_number_only_on_bearings():
    assert "bearing_no" not in attrs("PUMP 6205 SPARES")


def test_confidence_is_reported_per_attribute():
    _, conf = extract(normalize("Bolt hexagonal SS 12x50mm"))
    assert conf["noun"] == 0.9 and conf["thread"] == 0.8                  # derived from "12x50", so less certain


# ---- values typed by people or returned by an LLM ----------------------------------------------------------------

@pytest.mark.parametrize("key,value,expected", [
    ("thread", "M12", "12"), ("rating", "150#", "150"), ("rating", "CLASS 300", "300"), ("size_in", '2"', "2"),
    ("grade", "316", "SS316"), ("grade", "stainless steel 316L", "SS316L"), ("grade", "A106 GR.B", "A106B"),
    ("schedule", "SCH 40", "40"), ("standard", "ASME B16.5", "B16.5"), ("conductor", "Cu", "COPPER"),
    ("noun", "gate valve", "GATE VALVE"), ("noun", "spaceship", None), ("length_mm", "fifty", None),
    ("rating", "PN 16", "PN16"),
])
def test_canonical_value(key, value, expected):
    assert canonical_value(key, value) == expected


def test_llm_output_is_validated():
    raw = ('{"thread": "M12", "grade": "316", "rating": "150#", "noun": "SPACESHIP", "schedule": "SCH 40", '
           '"length_mm": "fifty", "evil": "x"}')
    assert _parse(raw) == {"thread": "12", "grade": "SS316", "rating": "150", "schedule": "40"}
    assert _parse("not json at all") == {}
    assert _parse('["a list"]') == {}


def test_llm_is_off_by_default(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "noop")
    assert llm_attributes("HEX BOLT M12X50 SS304") == {}


# ---- standard description ----------------------------------------------------------------------------------------

def test_standard_description_noun_first():
    assert standard_description(attrs("HEX BOLT M12X50 SS304")) == "BOLT; THREAD: M12; LENGTH: 50 MM; MATERIAL: SS304"
    assert standard_description(attrs('GATE VALVE 2" 150# A105')) == \
        "VALVE, GATE; SIZE: 2 IN; RATING: 150#; MATERIAL: A105"


def test_standard_description_falls_back_to_text():
    assert standard_description({}, "grease lithium ep2") == "GREASE LITHIUM EP2"
