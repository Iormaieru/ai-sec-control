"""Guards the versioned seed artifact (alembic/data/catalogo_maestro_v1.json)
against silent drift from the source Excel: wrong counts here would mean
every domain/global score computed downstream is wrong too."""

import json
from pathlib import Path

import pytest

EXPECTED_DOMAIN_COUNTS = {
    "DDG": 10,
    "TAC": 7,
    "PDP": 18,
    "CYB": 37,
    "SAF": 25,
    "BFD": 15,
    "EHR": 13,
    "AHO": 13,
}

EXPECTED_TIER_COUNTS = {
    "DDG": {"critico": 5, "alto": 3, "estandar": 2},
    "TAC": {"critico": 3, "alto": 3, "estandar": 1},
    "PDP": {"critico": 10, "alto": 8, "estandar": 0},
    "CYB": {"critico": 20, "alto": 15, "estandar": 2},
    "SAF": {"critico": 7, "alto": 12, "estandar": 6},
    "BFD": {"critico": 6, "alto": 7, "estandar": 2},
    "EHR": {"critico": 6, "alto": 6, "estandar": 1},
    "AHO": {"critico": 8, "alto": 5, "estandar": 0},
}

SEED_PATH = Path(__file__).resolve().parents[2] / "alembic" / "data" / "catalogo_maestro_v1.json"

TIER_MULTIPLICADOR = {"critico": 3, "alto": 2, "estandar": 1}


def _load_payload() -> dict:
    return json.loads(SEED_PATH.read_text(encoding="utf-8"))


def test_total_question_count_is_138() -> None:
    payload = _load_payload()
    assert len(payload["preguntas"]) == 138


def test_eight_domains_present() -> None:
    payload = _load_payload()
    assert len(payload["dominios"]) == 8
    assert {d["codigo"] for d in payload["dominios"]} == set(EXPECTED_DOMAIN_COUNTS)


def test_domain_weights_sum_to_one() -> None:
    payload = _load_payload()
    total_peso = sum(d["peso"] for d in payload["dominios"])
    assert total_peso == pytest.approx(1.0, abs=1e-9)


def test_question_count_per_domain_matches_excel() -> None:
    payload = _load_payload()
    actual: dict[str, int] = {}
    for p in payload["preguntas"]:
        actual[p["dominio_codigo"]] = actual.get(p["dominio_codigo"], 0) + 1
    assert actual == EXPECTED_DOMAIN_COUNTS


def test_tier_counts_per_domain_match_excel() -> None:
    payload = _load_payload()
    actual: dict[str, dict[str, int]] = {codigo: {"critico": 0, "alto": 0, "estandar": 0} for codigo in EXPECTED_DOMAIN_COUNTS}
    for p in payload["preguntas"]:
        actual[p["dominio_codigo"]][p["tier"]] += 1
    assert actual == EXPECTED_TIER_COUNTS


def test_multiplicador_matches_tier_for_every_question() -> None:
    payload = _load_payload()
    for p in payload["preguntas"]:
        assert p["multiplicador"] == TIER_MULTIPLICADOR[p["tier"]], p


def test_domain_total_preguntas_matches_actual_question_count() -> None:
    payload = _load_payload()
    actual: dict[str, int] = {}
    for p in payload["preguntas"]:
        actual[p["dominio_codigo"]] = actual.get(p["dominio_codigo"], 0) + 1
    for dominio in payload["dominios"]:
        assert dominio["total_preguntas"] == actual[dominio["codigo"]], dominio


def test_every_question_has_bilingual_text() -> None:
    payload = _load_payload()
    for p in payload["preguntas"]:
        assert p["texto_es"], p
        assert p["texto_en"], p
