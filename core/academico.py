"""Executa o protocolo acadêmico completo fora do servidor Flask."""

import argparse
from pathlib import Path

from .experimentos import ABAS, ConfiguracaoExperimento, ExecutorExperimentos
from .investigacao import RecorteIndustrial, SelecaoRegistros
from .repositorio import ler_csv
from .trabalhos import salvar_resultado


def principal() -> None:
    """Mede todas as abas e grava dados reprodutíveis."""
    raiz = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pasta", type=Path, default=raiz / "instancia" / "experimentos"
    )
    parser.add_argument("--semente", type=int, default=42)
    parametros = parser.parse_args()
    base = tuple(
        ler_csv((raiz / "data" / "ai4i2020.csv").read_text(encoding="utf-8-sig"))
    )
    origem = RecorteIndustrial(
        SelecaoRegistros("controlado"), base, []
    ).procedencia_experimental()
    for aba in ABAS:
        cfg = ConfiguracaoExperimento.criar({"aba": aba, "semente": parametros.semente})
        print(f"Executando {aba}...", flush=True)
        resultado = ExecutorExperimentos().executar(cfg, base)
        salvar_resultado(parametros.pasta, aba, resultado, origem)
        print(f"Concluído: {len(resultado['brutos'])} medições ({aba}).", flush=True)


if __name__ == "__main__":
    principal()
