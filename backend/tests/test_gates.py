import pytest

from ekml.explain import explain
from ekml.extract import extract
from ekml.features import pair_features
from ekml.gates import gate_failures
from ekml.normalize import normalize, set_abbreviations
from ekml.score import decide, is_exact, weighted

TH = {"near": 0.88, "equivalent": 0.78}


@pytest.fixture(autouse=True)
def seed_dictionary():
    set_abbreviations({})
    yield


def attrs(text: str) -> dict:
    return extract(normalize(text))[0]


def gates(x: str, y: str) -> list[str]:
    return gate_failures(attrs(x), attrs(y))


# ---- G2: hard negatives are always blocked -----------------------------------------------------------------------

@pytest.mark.parametrize("x,y,key", [
    ("HEX BOLT M12X50 SS304", "HEX BOLT M16X50 SS304", "thread"),
    ("HEX BOLT M12X50 SS304", "HEX BOLT M12X65 SS304", "length_mm"),
    ('GASKET SPWD 4" 150# SS316', 'GASKET SPWD 4" 300# SS316', "rating"),
    ("HEX BOLT M12X50 SS304", "HEX BOLT M12X50 SS316", "grade"),
    ('GASKET 4" 150# SS316', 'GASKET 4" 150# SS316L', "grade"),
    ("STUD BOLT M16X90 A193 B7", "HEX BOLT M16X90 A193 B7", "noun"),
    ("HEX NUT M12 SS304", "HEX BOLT M12X50 SS304", "noun"),
    ('PIPE 2" SCH 40 A106B', 'PIPE 3" SCH 40 A106B', "size_in"),
    ('PIPE 2" SCH 40 A106B', 'PIPE 2" SCH 80 A106B', "schedule"),
    ("BEARING 6205-2RS", "BEARING 6205-ZZ", "bearing_no"),
    ("CABLE 3C X 95 SQMM CU 1.1KV", "CABLE 3C X 95 SQMM AL 1.1KV", "conductor"),
    ('PIPE 2" SCH 40 L=6M A106B', 'PIPE 2" SCH 40 L=12M A106B', "length_mm"),
    ('GATE VALVE 2" 150# A105', 'GATE VALVE 2" PN16 A105', "rating"),       # class 150 is not PN16
])
def test_conflicts_are_blocked(x, y, key):
    assert key in gates(x, y)


@pytest.mark.parametrize("x,y", [
    ("HEX BOLT M12X50 SS304", "SS HX BLT M12 L50"),
    ("HEX BOLT M12X50 SS304", "Bolt hexagonal SS 12x50mm"),
    ("HEX BOLT M12X50 SS304", "BOLT,HEX,M12 X 50MM,S.S.304"),
    ("PIPE 50 NB SCH 40 SMLS A106 GR.B", 'PIPE 2" SCH-40 A106B'),
    ('GATE VALVE 2" 150# A105 API 600', "GV 2 IN 150# A105 API 600"),
    ('GATE VALVE 2" 150# A105 API 600', "VALVE,GATE,50NB,CL150,BODY A105,API600"),
    ("SPIRAL WOUND GASKET 4 IN 300# SS316 ASME B16.20", 'SPWD GSKT 4" 300# SS316 B16.20'),
    ("BEARING 6205-2RS", "BRG 6205 2RS"),
    ('PIPE 2" SCH 40 L=6M A106B', 'PIPE 50NB SCH-40 L 6000MM A106 GR.B'),     # metres vs mm, inch vs NB
])
def test_same_material_written_differently_passes(x, y):
    assert gates(x, y) == []


def test_missing_value_is_not_a_conflict():
    assert gates("HEX BOLT M12X50", "HEX BOLT M12X50 SS304") == []


# ---- scoring -----------------------------------------------------------------------------------------------------

def feats(**kw) -> dict:
    f = {"semantic": 0.95, "lexical": 0.95, "attribute": 1.0, "spec": 1.0, "unit": 1.0, "category": 1.0,
         "text_exact": 0.95}
    f.update(kw)
    return f


def test_a_gate_forces_different_whatever_the_score():
    d = decide(feats(semantic=0.99, lexical=1.0), ["thread"], TH)
    assert d.match_type == "DIFFERENT" and d.score <= 0.49 and d.gates == ["thread"]


def test_exact_duplicate_needs_same_words_same_attributes_same_unit():
    assert decide(feats(text_exact=1.0, lexical=1.0), [], TH).match_type == "EXACT_DUPLICATE"
    assert decide(feats(text_exact=1.0, lexical=1.0, attribute=0.83), [], TH).match_type != "EXACT_DUPLICATE"
    assert decide(feats(text_exact=1.0, lexical=1.0, unit=0.0), [], TH).match_type != "EXACT_DUPLICATE"


def test_threshold_bands():
    assert decide(feats(), [], TH).match_type == "NEAR_DUPLICATE"
    fe = feats(semantic=0.85, lexical=0.7, attribute=0.75, spec=0.5, text_exact=0.6)
    assert TH["equivalent"] <= weighted(fe) < TH["near"]
    assert decide(fe, [], TH).match_type == "FUNCTIONAL_EQUIVALENT"
    low = feats(semantic=0.5, lexical=0.4, attribute=0.5, spec=0.5, text_exact=0.3)
    assert decide(low, [], TH).match_type == "DIFFERENT"


def test_one_sided_attribute_counts_half():
    a, b = attrs("HEX BOLT M12X50 SS304"), attrs("SS HX BLT M12 L50")
    f = pair_features(0.93, normalize("HEX BOLT M12X50 SS304"), normalize("SS HX BLT M12 L50"), a, b, "C62", "C62")
    assert f["attribute"] == pytest.approx(2.5 / 3, abs=1e-3)               # thread, length agree; grade unstated
    assert f["category"] == 1.0 and f["unit"] == 1.0
    assert not is_exact(f)


def test_unit_conflict_feature():
    f = pair_features(0.9, "a", "a", {}, {}, "C62", "SET")
    assert f["unit"] == 0.0


def test_explanation_marks_the_conflict():
    a, c = attrs("HEX BOLT M12X50 SS304"), attrs("HEX BOLT M16X50 SS304")
    chips = {x["key"]: x["kind"] for x in explain({"semantic": 0.97, "lexical": 0.9}, a, c, ["thread"]) if "key" in x}
    assert chips["thread"] == "conflict" and chips["grade"] == "match" and chips["length_mm"] == "match"
