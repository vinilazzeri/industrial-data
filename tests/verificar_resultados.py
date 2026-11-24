"""Confere os artefatos de uma rodada completa: python -m tests.verificar_resultados PASTA."""

import argparse
import csv
import json
from pathlib import Path
from statistics import median, quantiles

from PIL import Image

CONFIGURACOES = {"ordenacao": 48, "busca": 24, "hash": 9, "sistema": 24}
GRUPO = ("tamanho", "distribuicao", "algoritmo", "carga_alvo")


def conferir_csv(caminho, esperado):
    with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
        recebido = list(csv.DictReader(arquivo))
    assert len(recebido) == len(esperado), caminho
    for csv_linha, json_linha in zip(recebido, esperado):
        assert set(json_linha) <= csv_linha.keys(), caminho
        assert csv_linha == {
            chave: "" if (valor := json_linha.get(chave)) is None else str(valor)
            for chave in csv_linha
        }, caminho


def conferir(pasta, exigir_reconstrucao):
    for aba, quantidade in CONFIGURACOES.items():
        arquivo = pasta / f"{aba}.json"
        resultado = json.loads(arquivo.read_text(encoding="utf-8"))
        cfg = resultado["configuracao"]
        assert cfg["aba"] == aba
        assert cfg["tamanhos"] == [500, 2000, 8000]
        assert (
            cfg["repeticoes"],
            cfg["consultas"],
            cfg["semente"],
            cfg["operacoes"],
        ) == (5, 1000, 42, 100)
        assert len(resultado["compensacao"]) == (18 if aba == "busca" else 0), aba
        for tipo in ("brutos", "resumo", "compensacao"):
            if resultado[tipo]:
                conferir_csv(pasta / f"{aba}_{tipo}.csv", resultado[tipo])
        grupos = {}
        for linha in resultado["brutos"]:
            grupo = tuple(linha[campo] for campo in GRUPO)
            grupos.setdefault(grupo, []).append(linha)
            assert linha["semente"] == 42 + linha["tamanho"]
            assert linha["tempo_ns"] > 0 and linha["pico_bytes"] > 0
            assert (
                linha["unidade_tempo"] == "ns" and linha["unidade_memoria"] == "bytes"
            )
            if aba == "hash":
                assert linha["fator_carga"] == linha["tamanho"] / linha["capacidade"]
            if aba == "sistema" and linha["distribuicao"] == "Dinâmica":
                assert linha["mutacoes_executadas"] == 100
                if exigir_reconstrucao:
                    assert linha["reconstrucao_ns"] > 0
        assert len(grupos) == len(resultado["resumo"]) == quantidade
        assert len(resultado["brutos"]) == quantidade * 5
        for resumo in resultado["resumo"]:
            linhas = grupos.pop(tuple(resumo[campo] for campo in GRUPO))
            assert sorted(linha["repeticao"] for linha in linhas) == [1, 2, 3, 4, 5]
            for chave, valor in resumo.items():
                base, _, agregacao = chave.rpartition("_")
                if agregacao not in ("mediana", "iiq"):
                    continue
                valores = [linha[base] for linha in linhas if linha[base] is not None]
                if agregacao == "mediana":
                    assert valor == median(valores), (aba, chave)
                else:
                    q1, _, q3 = quantiles(valores, method="inclusive")
                    assert valor == q3 - q1, (aba, chave)
        assert not grupos
        with Image.open(pasta / f"{aba}.png") as figura:
            assert figura.format == "PNG" and min(figura.size) >= 400
            figura.verify()
        print(
            f"{aba}: {quantidade} configurações, {quantidade * 5} repetições, CSV/JSON/PNG válidos."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pasta", type=Path)
    parser.add_argument(
        "--referencia",
        action="store_true",
        help="Aceita a referência anterior à métrica de reconstrução.",
    )
    argumentos = parser.parse_args()
    conferir(argumentos.pasta, not argumentos.referencia)
