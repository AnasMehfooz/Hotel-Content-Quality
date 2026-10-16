import pytest

from hcq.text import mojibake, normalize_phone_de, normalize_url, split_de_number, transliterate


def test_transliterate_german():
    assert transliterate("Köln Straße Düsseldorf") == "Koeln Strasse Duesseldorf"


def test_mojibake_matches_real_world_pattern():
    assert mojibake("Köln") == "KÃ¶ln"
    assert mojibake("Straße") == "StraÃŸe"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0221 / 123456", "+49221123456"),
        ("+49 (0)221 123456", "+49221123456"),
        ("0049 211 9876543", "+492119876543"),
        ("+492211234567", "+492211234567"),
        ("0221 12", None),
        ("n/a", None),
        (None, None),
    ],
)
def test_normalize_phone_de(raw, expected):
    assert normalize_phone_de(raw) == expected


def test_split_de_number():
    assert split_de_number("+492211234567") == ("221", "1234567")
    assert split_de_number("+4969123456") == ("69", "123456")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("www.hotel-am-dom.de", "https://www.hotel-am-dom.de"),
        ("http://hotel.de/", "https://hotel.de"),
        ("https://www .hotel.de", None),
        ("https://www..hotel.de", None),
    ],
)
def test_normalize_url(raw, expected):
    assert normalize_url(raw) == expected
