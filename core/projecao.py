"""Ajustes da coleção consultável sem reescrever o histórico de máquinas."""

import csv
import io
from dataclasses import asdict, replace
from pathlib import Path

from .dominio import RegistroIndustrial, inteiro
from .repositorio import CAMPOS, escrever_atomicamente, validar_alteracoes


class ProjecaoTelemetria:
    """Guarda edições e remoções lógicas da telemetria na coleção de registros."""

    def __init__(self, caminho: Path) -> None:
        self._caminho = caminho
        self._ajustes: dict[int, RegistroIndustrial | None] = {}
        if caminho.exists():
            with caminho.open(encoding="utf-8", newline="") as arquivo:
                for linha in csv.DictReader(arquivo):
                    udi = inteiro(linha["identificador"], "UDI")
                    removido = inteiro(linha.pop("removido"), "Removido", 0, 1)
                    self._ajustes[udi] = (
                        None if removido else RegistroIndustrial(**linha)
                    )

    def visivel(self, original: RegistroIndustrial) -> RegistroIndustrial | None:
        """Devolve a versão de trabalho, o registro original ou uma remoção lógica."""
        registro = self._ajustes.get(original.identificador, original)
        if registro is not None and registro.equipamento != original.equipamento:
            return replace(registro, equipamento=original.equipamento)
        return registro

    def aplicar(
        self, original: RegistroIndustrial, alteracoes: dict | None
    ) -> RegistroIndustrial | None:
        """Persiste um ajuste ou uma remoção sem modificar o ciclo arquivado."""
        atual = self.visivel(original)
        if atual is None:
            raise LookupError("Registro não encontrado.")
        revisado = None
        if alteracoes is not None:
            validar_alteracoes(alteracoes)
            if (
                alteracoes.get("equipamento", original.equipamento)
                != original.equipamento
            ):
                raise ValueError("O equipamento de um ciclo arquivado é imutável.")
            revisado = replace(atual, **alteracoes)
            if revisado == atual:
                return atual
        ajustes = {**self._ajustes, original.identificador: revisado}
        arquivo = io.StringIO(newline="")
        escritor = csv.DictWriter(arquivo, fieldnames=("removido", *CAMPOS))
        escritor.writeheader()
        for udi, registro in ajustes.items():
            if registro is None:
                escritor.writerow({"removido": 1, "identificador": udi})
            else:
                escritor.writerow({"removido": 0, **asdict(registro)})
        escrever_atomicamente(self._caminho, arquivo.getvalue())
        self._ajustes = ajustes
        return revisado
