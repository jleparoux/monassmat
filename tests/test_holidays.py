from datetime import date
from monassmat.calculations import parse_holidays_response


def test_parse_holidays_standard():
    data = {
        "2025-01-01": "1er janvier",
        "2025-05-01": "Fête du Travail",
        "invalid-date": "Ignoré",
    }
    result = parse_holidays_response(data)
    assert result == [
        (date(2025, 1, 1), "1er janvier"),
        (date(2025, 5, 1), "Fête du Travail"),
    ]


def test_parse_holidays_empty():
    assert parse_holidays_response({}) == []


def test_parse_holidays_sorted():
    data = {
        "2025-12-25": "Noël",
        "2025-07-14": "Fête nationale",
    }
    result = parse_holidays_response(data)
    assert result[0][0] == date(2025, 7, 14)
    assert result[1][0] == date(2025, 12, 25)
