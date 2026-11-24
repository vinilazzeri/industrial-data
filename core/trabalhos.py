"""Execução em segundo plano e exportação de resultados persistidos."""

import csv
import io
import json
import logging
from collections.abc import Sequence
from multiprocessing import get_context
from multiprocessing.connection import Connection
from pathlib import Path
from threading import Lock, Thread
from uuid import uuid4

from .dominio import RegistroIndustrial
from .experimentos import ABAS, ConfiguracaoExperimento, ExecutorExperimentos
from .repositorio import escrever_atomicamente

REGISTRO = logging.getLogger(__name__)


def _medir_em_processo(
    configuracao: ConfiguracaoExperimento,
    base: Sequence[RegistroIndustrial],
    pasta: Path,
    canal: Connection,
    origem: dict | None,
) -> None:
    with canal:
        resultado = ExecutorExperimentos().executar(
            configuracao,
            base,
            lambda concluidos, total: canal.send((concluidos, total)),
        )
        salvar_resultado(pasta, configuracao.aba, resultado, origem)


def csv_metricas(linhas: list[dict]) -> str:
    """Exporta todos os campos observados, incluindo as unidades."""
    colunas = list(dict.fromkeys(campo for linha in linhas for campo in linha))
    arquivo = io.StringIO(newline="")
    escritor = csv.DictWriter(arquivo, fieldnames=colunas)
    if colunas:
        escritor.writeheader()
        escritor.writerows(linhas)
    return arquivo.getvalue()


class TrabalhosExperimentos:
    """Executa um benchmark isolado por vez e publica a última execução por aba."""

    def __init__(self, pasta: Path, base: Sequence[RegistroIndustrial]) -> None:
        self._pasta = pasta
        self._base = base
        self._trava = Lock()
        self._ativo: dict | None = None

    def iniciar(
        self,
        configuracao: ConfiguracaoExperimento,
        *,
        base: Sequence[RegistroIndustrial] | None = None,
        contexto: str = "",
        origem: dict | None = None,
    ) -> dict:
        """Agenda a execução e informa o estado sem bloquear o Flask."""
        entrada = self._base if base is None else base
        if max(configuracao.tamanhos) > len(entrada):
            raise ValueError(
                f"Este recorte tem {len(entrada)} registros. Reduza os tamanhos ou selecione "
                "o conjunto controlado para o protocolo de 500, 2.000 e 8.000."
            )
        with self._trava:
            if self._ativo and self._ativo["estado"] == "Executando":
                raise RuntimeError("Já existe um experimento em execução.")
            identificador = uuid4().hex
            self._ativo = {
                "id": identificador,
                "aba": configuracao.aba,
                "contexto": contexto,
                "estado": "Executando",
                "concluidos": 0,
                "total": 0,
            }
            Thread(
                target=self._executar,
                args=(configuracao, entrada, contexto, origem),
                daemon=True,
            ).start()
            return self._ativo.copy()

    def _progresso(self, concluidos: int, total: int) -> None:
        with self._trava:
            self._ativo.update(concluidos=concluidos, total=total)

    def _executar(
        self,
        configuracao: ConfiguracaoExperimento,
        base: Sequence[RegistroIndustrial],
        contexto_dados: str,
        origem: dict | None,
    ) -> None:
        contexto = get_context("spawn")
        receptor, emissor = contexto.Pipe(duplex=False)
        processo = contexto.Process(
            target=_medir_em_processo,
            args=(configuracao, base, self._pasta / contexto_dados, emissor, origem),
            daemon=True,
        )
        concluido = False
        try:
            with receptor, emissor:
                processo.start()
                emissor.close()
                while True:
                    try:
                        concluidos, total = receptor.recv()
                    except EOFError:
                        break
                    self._progresso(concluidos, total)
            processo.join()
            concluido = processo.exitcode == 0
        except (OSError, RuntimeError):
            REGISTRO.exception("Falha no experimento %s.", configuracao.aba)
        finally:
            if processo.pid is not None and processo.is_alive():
                processo.terminate()
                processo.join()
            processo.close()
        with self._trava:
            if concluido:
                self._ativo.update(estado="Concluído")
            else:
                self._ativo.update(
                    estado="Erro", mensagem="Falha ao concluir o experimento."
                )

    def estado(self) -> dict | None:
        """Permite consultar progresso mesmo após recarregar a página."""
        with self._trava:
            return self._ativo.copy() if self._ativo else None

    def resultado(self, aba: str, contexto: str = "") -> dict | None:
        """Lê o último resultado completo gravado para a aba."""
        if aba not in ABAS:
            raise LookupError("Aba experimental não encontrada.")
        caminho = self._pasta / contexto / f"{aba}.json"
        return (
            json.loads(caminho.read_text(encoding="utf-8"))
            if caminho.exists()
            else None
        )


def salvar_resultado(
    pasta: Path,
    aba: str,
    resultado: dict,
    origem: dict | None = None,
) -> None:
    """Publica CSV brutos e agregados, seguidos do resultado para a aplicação."""
    if origem:
        resultado = {
            **resultado,
            "origem": origem,
            **{
                tipo: [{**linha, **origem} for linha in resultado[tipo]]
                for tipo in ("brutos", "resumo", "compensacao")
            },
        }
    for tipo in ("brutos", "resumo", "compensacao"):
        if resultado[tipo]:
            escrever_atomicamente(
                pasta / f"{aba}_{tipo}.csv", csv_metricas(resultado[tipo])
            )
    escrever_atomicamente(
        pasta / f"{aba}.json", json.dumps(resultado, ensure_ascii=False)
    )
