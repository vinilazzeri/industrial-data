"""Gera quatro figuras acadêmicas a partir dos CSV agregados."""

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter, PercentFormatter  # noqa: E402

CORES = ("#007d72", "#286eac", "#ad5900", "#6f4ca4")
NOMES = {
    "insercao": "Insertion Sort",
    "intercalacao": "Merge Sort",
    "heap": "Heap Sort",
    "nativo": "Python sorted",
    "sequencial": "Sequencial",
    "binaria": "Binária",
    "interpolacao": "Interpolação",
    "hash": "Tabela hash",
}


def _linhas(pasta: Path, aba: str) -> list[dict[str, str]]:
    with (pasta / f"{aba}_resumo.csv").open(
        encoding="utf-8-sig", newline=""
    ) as arquivo:
        return list(csv.DictReader(arquivo))


def _figura(titulo: str, perfis: list[str]):
    colunas = min(2, len(perfis))
    linhas = (len(perfis) + colunas - 1) // colunas
    figura, eixos = plt.subplots(
        linhas,
        colunas,
        squeeze=False,
        figsize=(11 if colunas == 2 else 8, 3.9 * linhas),
        layout="constrained",
    )
    figura.suptitle(titulo, fontsize=15, fontweight="semibold")
    return figura, eixos.flat


def _plotar(
    eixo,
    coordenadas: list[float],
    medianas: list[float],
    cor: str,
    rotulo: str,
    iiqs: list[float] | None = None,
) -> None:
    eixo.plot(coordenadas, medianas, color=cor, marker="o", linewidth=1.7, label=rotulo)
    if iiqs and any(iiqs):
        eixo.fill_between(
            coordenadas,
            [max(1e-8, m - q / 2) for m, q in zip(medianas, iiqs)],
            [m + q / 2 for m, q in zip(medianas, iiqs)],
            color=cor,
            alpha=0.12,
        )


def _por_tamanho(
    pasta: Path,
    aba: str,
    titulo: str,
    campo: str,
    unidade: str,
    perfis: list[str],
    log: bool = False,
) -> None:
    registros = _linhas(pasta, aba)
    figura, eixos = _figura(titulo, perfis)
    nomes = list(dict.fromkeys(r["algoritmo"] for r in registros))
    for eixo, perfil in zip(eixos, perfis):
        for nome, cor in zip(nomes, CORES):
            selecionados = sorted(
                (
                    r
                    for r in registros
                    if r["distribuicao"] == perfil and r["algoritmo"] == nome
                ),
                key=lambda r: int(r["tamanho"]),
            )
            tamanhos = [int(r["tamanho"]) for r in selecionados]
            medianas = [float(r[f"{campo}_mediana"]) / 1e6 for r in selecionados]
            iiqs = [float(r[f"{campo}_iiq"]) / 1e6 for r in selecionados]
            _plotar(eixo, tamanhos, medianas, cor, NOMES[nome], iiqs)
        eixo.set_title(perfil, loc="left", fontsize=11)
        eixo.set_xlabel("Registros")
        eixo.set_ylabel(unidade)
        eixo.xaxis.set_major_formatter(
            FuncFormatter(lambda x, _: f"{x:,.0f}".replace(",", "."))
        )
        if log:
            eixo.set_yscale("log")
        eixo.grid(alpha=0.2)
        eixo.legend(fontsize=8)
    figura.supxlabel(
        "Linhas: medianas | Faixas centradas na mediana: largura do IIQ",
        color="#46566a",
        fontsize=9,
    )
    figura.savefig(pasta / f"{aba}.png", dpi=170, facecolor="white")
    plt.close(figura)


def _hash(pasta: Path) -> None:
    registros = _linhas(pasta, "hash")
    perfis = ["Chaves presentes", "Chaves ausentes"]
    figura, eixos = _figura("Efeito do fator de carga da tabela hash", perfis)
    tamanhos = sorted({int(r["tamanho"]) for r in registros})
    for eixo, perfil, campo in zip(
        eixos, perfis, ("passos_presente", "passos_ausente")
    ):
        for tamanho, cor in zip(tamanhos, CORES):
            linhas = sorted(
                (r for r in registros if int(r["tamanho"]) == tamanho),
                key=lambda r: float(r["fator_carga_mediana"]),
            )
            _plotar(
                eixo,
                [float(r["fator_carga_mediana"]) for r in linhas],
                [float(r[f"{campo}_mediana"]) for r in linhas],
                cor,
                f"{tamanho:,} registros".replace(",", "."),
            )
        eixo.set_title(perfil, loc="left", fontsize=11)
        eixo.set_xlabel("Fator de carga real")
        eixo.set_ylabel("Passos médios")
        eixo.xaxis.set_major_formatter(PercentFormatter(1))
        eixo.set_ylim(bottom=0)
        eixo.grid(alpha=0.2)
        eixo.legend(fontsize=8)
    figura.savefig(pasta / "hash.png", dpi=170, facecolor="white")
    plt.close(figura)


def gerar_graficos(pasta: Path) -> None:
    """Gera PNGs dos quatro experimentos sem executar novos benchmarks."""
    _por_tamanho(
        pasta,
        "ordenacao",
        "Crescimento das ordenações",
        "tempo_ns",
        "Tempo (ms)",
        ["Aleatória", "Ordenada", "Inversa", "Repetições"],
        log=True,
    )
    _por_tamanho(
        pasta,
        "busca",
        "Custo das buscas por UDI",
        "consulta_ns",
        "Consultas (ms)",
        ["Regular", "Lacunas e concentração"],
        log=True,
    )
    _hash(pasta)
    _por_tamanho(
        pasta,
        "sistema",
        "Custo total com preparação e atualizações",
        "tempo_ns",
        "Tempo total (ms)",
        ["Estática", "Dinâmica"],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pasta", type=Path, help="Pasta com os CSV agregados.")
    gerar_graficos(parser.parse_args().pasta)
