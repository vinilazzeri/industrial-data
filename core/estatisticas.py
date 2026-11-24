"""Estatísticas descritivas com unidades preservadas."""

from collections.abc import Sequence
from statistics import fmean, median, pstdev, quantiles

from .dominio import RegistroIndustrial

MEDICOES = ("temperatura_ar", "temperatura_processo", "rpm", "torque", "desgaste")


def resumir(registros: Sequence[RegistroIndustrial]) -> dict:
    """Calcula média, mediana, extremos, desvio e histogramas de oito classes."""
    resumo = {
        "quantidade": len(registros),
        "alertas": sum(r.status == "Alerta" for r in registros),
        "falhas": sum(r.falha for r in registros),
        "medicoes": {},
    }
    if not registros:
        return resumo
    for campo in MEDICOES:
        valores = [getattr(registro, campo) for registro in registros]
        minimo, maximo = min(valores), max(valores)
        largura = (maximo - minimo) / 8
        classes = [0] * (8 if largura else 1)
        for valor in valores:
            indice = min(7, int((valor - minimo) / largura)) if largura else 0
            classes[indice] += 1
        quartis = (
            quantiles(valores, method="inclusive") if len(valores) > 1 else [minimo] * 3
        )
        resumo["medicoes"][campo] = {
            "media": fmean(valores),
            "mediana": median(valores),
            "minimo": minimo,
            "maximo": maximo,
            "desvio": pstdev(valores),
            "q1": quartis[0],
            "q3": quartis[2],
            "histograma": [
                {
                    "inicio": minimo + i * largura,
                    "fim": minimo + (i + 1) * largura,
                    "quantidade": total,
                }
                for i, total in enumerate(classes)
            ],
        }
    return resumo
