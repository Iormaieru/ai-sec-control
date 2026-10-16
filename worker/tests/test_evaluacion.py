"""H3: criterios de evaluación (funciones puras)."""

import datetime as dt

from aisec_worker.herramientas.evaluacion import (
    AMARILLO,
    ROJO,
    SIN_DATOS,
    VERDE,
    DatosFuentes,
    es_candidata,
    evaluar,
    limpiar_version,
    novedades,
    nuevo_estado,
    repo_mudado,
)
from aisec_worker.herramientas.fuentes import RepoGitHub
from app.pentesting.models import EstadoHerramienta

AHORA = dt.datetime(2026, 10, 16, tzinfo=dt.UTC)


def _repo(**cambios) -> RepoGitHub:
    base = dict(
        nombre="NVIDIA/garak",
        descripcion="LLM vulnerability scanner",
        url="https://github.com/NVIDIA/garak",
        homepage=None,
        estrellas=9584,
        archivado=False,
        ultimo_push=AHORA - dt.timedelta(days=1),
        licencia="Apache-2.0",
    )
    return RepoGitHub(**{**base, **cambios})


def test_herramienta_sana_es_candidata() -> None:
    ev = evaluar(DatosFuentes(repo=_repo(), version_publicada="0.17.0"), AHORA)

    assert ev.senales == {"mantenida": VERDE, "adoptada": VERDE, "instalable": VERDE, "licencia": VERDE}
    assert ev.motivo is None
    assert es_candidata(ev)


def test_llm_guard_archivada_pasa_a_observacion() -> None:
    ev = evaluar(DatosFuentes(repo=_repo(nombre="protectai/llm-guard", estrellas=3216, archivado=True)), AHORA)

    assert ev.senales["mantenida"] == ROJO
    assert ev.motivo == "El repositorio protectai/llm-guard está archivado en GitHub"
    assert not es_candidata(ev)
    estado, motivo = nuevo_estado(EstadoHerramienta.ACTIVA, ev)
    assert (estado, motivo) == (EstadoHerramienta.EN_OBSERVACION, ev.motivo)


def test_actividad_vieja() -> None:
    hace_18_meses = evaluar(DatosFuentes(repo=_repo(ultimo_push=AHORA - dt.timedelta(days=540))), AHORA)
    hace_3_anios = evaluar(DatosFuentes(repo=_repo(ultimo_push=dt.datetime(2023, 9, 1, tzinfo=dt.UTC))), AHORA)

    assert hace_18_meses.senales["mantenida"] == AMARILLO
    assert hace_3_anios.senales["mantenida"] == ROJO
    assert hace_3_anios.motivo == "Sin actividad desde 2023-09-01"


def test_un_release_reciente_cuenta_como_actividad() -> None:
    datos = DatosFuentes(
        repo=_repo(ultimo_push=dt.datetime(2023, 1, 1, tzinfo=dt.UTC)),
        version_publicada="2.0",
        fecha_version=AHORA - dt.timedelta(days=30),
    )

    assert evaluar(datos, AHORA).senales["mantenida"] == VERDE


def test_adopcion_por_estrellas_o_distribuciones() -> None:
    poco_conocida = evaluar(DatosFuentes(repo=_repo(estrellas=40)), AHORA)
    en_dos_distros = evaluar(
        DatosFuentes(repo=_repo(estrellas=40), distribuciones=[{"distribucion": "kali"}, {"distribucion": "blackarch"}]),
        AHORA,
    )

    assert poco_conocida.senales["adoptada"] == ROJO
    assert en_dos_distros.senales["adoptada"] == VERDE
    assert not es_candidata(poco_conocida)


def test_sin_repo_como_burp_suite() -> None:
    """Burp no tiene repo: se la considera mantenida si una distribución la empaqueta."""
    ev = evaluar(DatosFuentes(distribuciones=[{"distribucion": "kali", "version": "2026.8"}]), AHORA)

    assert ev.senales == {"mantenida": VERDE, "adoptada": AMARILLO, "instalable": VERDE, "licencia": SIN_DATOS}


def test_sin_licencia_declarada_es_amarillo() -> None:
    assert evaluar(DatosFuentes(repo=_repo(licencia=None)), AHORA).senales["licencia"] == AMARILLO


def test_licencia_cargada_a_mano_cuenta() -> None:
    """sqlmap es GPL-2.0 pero GitHub no la reconoce; Burp es comercial y no tiene repo."""
    sqlmap = DatosFuentes(repo=_repo(licencia=None), licencia_registrada="GPL-2.0")
    burp = DatosFuentes(distribuciones=[{"distribucion": "kali"}], licencia_registrada="Comercial (Community gratuita)")

    assert evaluar(sqlmap, AHORA).senales["licencia"] == VERDE
    assert evaluar(burp, AHORA).senales["licencia"] == VERDE


def test_limpiar_version_empaquetada() -> None:
    assert limpiar_version("2026.8-0kali1") == "2026.8"
    assert limpiar_version("1:2026.9-1") == "2026.9"
    assert limpiar_version("0.17.0.r8.gbb30a7e-1") == "0.17.0"
    assert limpiar_version("2:7.4+parrot1") == "7.4"
    assert limpiar_version("3.11.1") == "3.11.1"


def test_vuelve_de_observacion_y_estados_manuales_no_cambian() -> None:
    sana = evaluar(DatosFuentes(repo=_repo()), AHORA)
    rota = evaluar(DatosFuentes(repo=_repo(archivado=True)), AHORA)

    assert nuevo_estado(EstadoHerramienta.EN_OBSERVACION, sana) == (EstadoHerramienta.ACTIVA, None)
    for manual in (EstadoHerramienta.CANDIDATA, EstadoHerramienta.RETIRADA, EstadoHerramienta.DESCARTADA):
        assert nuevo_estado(manual, rota)[0] == manual


def test_repo_mudado() -> None:
    mudado = DatosFuentes(repo=_repo(nombre="Giskard-AI/giskard-oss"), repo_esperado="Giskard-AI/giskard")

    assert repo_mudado(mudado) == "Giskard-AI/giskard-oss"
    assert repo_mudado(DatosFuentes(repo=_repo(), repo_esperado="nvidia/GARAK")) is None


def test_novedades() -> None:
    cambios = novedades(
        version_anterior="0.16.0",
        version_nueva="0.17.0",
        estado_anterior=EstadoHerramienta.ACTIVA,
        estado_nuevo=EstadoHerramienta.EN_OBSERVACION,
        motivo="Sin actividad desde 2023-09-01",
        mudado_a="microsoft/PyRIT",
    )

    assert cambios == [
        "Nueva versión 0.17.0 (antes 0.16.0)",
        "El repositorio se mudó a microsoft/PyRIT",
        "Pasó a observación: Sin actividad desde 2023-09-01",
    ]
