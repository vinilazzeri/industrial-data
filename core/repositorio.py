"""Leitura CSV, snapshots imutáveis e persistência atômica."""

import csv
import io
import os
from collections.abc import Iterable, Mapping
from dataclasses import asdict, fields, replace
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock
from time import perf_counter_ns, sleep

from .algoritmos import BUSCAS, IndiceBusca, Metricas
from .dominio import RegistroIndustrial

COLUNAS_AI4I = (
    "UDI",
    "Product ID",
    "Type",
    "Air temperature [K]",
    "Process temperature [K]",
    "Rotational speed [rpm]",
    "Torque [Nm]",
    "Tool wear [min]",
    "Machine failure",
    "TWF",
    "HDF",
    "PWF",
    "OSF",
    "RNF",
)
CAMPOS = tuple(campo.name for campo in fields(RegistroIndustrial))


def validar_alteracoes(alteracoes: Mapping) -> None:
    """Protege UDI, procedência e ciclo de edições na coleção."""
    campos_protegidos = ("identificador", "fonte", "ciclo")
    if any(campo not in CAMPOS or campo in campos_protegidos for campo in alteracoes):
        raise ValueError("Há campos desconhecidos ou protegidos na alteração.")


def gravar_csv(registros: Iterable[RegistroIndustrial]) -> str:
    """Serializa a representação de trabalho, sem conversão de unidades."""
    arquivo = io.StringIO(newline="")
    escritor = csv.DictWriter(arquivo, fieldnames=CAMPOS)
    escritor.writeheader()
    escritor.writerows(asdict(registro) for registro in registros)
    return arquivo.getvalue()


def ler_csv(conteudo: str, fonte_ai4i: str = "AI4I") -> list[RegistroIndustrial]:
    """Lê o esquema UCI ou o exportado pela aplicação e valida cada linha."""
    leitor = csv.DictReader(
        io.StringIO(conteudo.lstrip("\ufeff"), newline=""), strict=True
    )
    try:
        colunas = leitor.fieldnames or []
        original = set(colunas) == set(COLUNAS_AI4I) and len(colunas) == len(
            COLUNAS_AI4I
        )
        if not original and (
            set(colunas) != set(CAMPOS) or len(colunas) != len(CAMPOS)
        ):
            raise ValueError(
                "Cabeçalho CSV incompatível. Use o formato AI4I ou um CSV exportado."
            )
        if fonte_ai4i not in ("AI4I", "Importação"):
            raise ValueError("Origem inválida para CSV AI4I.")
        registros = []
        chaves = set()
        for linha in leitor:
            if None in linha or None in linha.values():
                raise ValueError(
                    f"Linha {leitor.line_num}: quantidade de campos inválida."
                )
            atributos = linha
            if original:
                if not all(linha[coluna].strip() for coluna in colunas):
                    raise ValueError(
                        f"Linha {leitor.line_num}: campo obrigatório vazio."
                    )
                atributos = {
                    campo: linha[coluna] for coluna, campo in zip(COLUNAS_AI4I, CAMPOS)
                }
                atributos["fonte"] = fonte_ai4i
            try:
                registro = RegistroIndustrial(**atributos)
                if registro.identificador in chaves:
                    raise ValueError(f"UDI duplicado ({registro.identificador}).")
            except ValueError as erro:
                raise ValueError(f"Linha {leitor.line_num}: {erro}") from erro
            chaves.add(registro.identificador)
            registros.append(registro)
        return registros
    except csv.Error as erro:
        raise ValueError(f"CSV inválido na linha {leitor.line_num}.") from erro


def escrever_atomicamente(caminho: Path, conteudo: str) -> None:
    """Substitui um arquivo somente após a gravação integral no mesmo volume."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            delete=False,
            dir=caminho.parent,
            suffix=".tmp",
        ) as arquivo:
            temporario = Path(arquivo.name)
            arquivo.write(conteudo)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        for tentativa in range(6):
            try:
                temporario.replace(caminho)
                break
            except PermissionError as erro:
                # No Windows um leitor com o arquivo aberto pode impedir a troca.
                if getattr(erro, "winerror", None) not in (5, 32, 33) or tentativa == 5:
                    raise
                sleep(0.025 * (tentativa + 1))
    finally:
        if temporario is not None:
            temporario.unlink(missing_ok=True)


class RepositorioRegistros:
    """Coordena alterações, snapshots e invalidação de índices por versão."""

    def __init__(self, caminho: Path, original: Path | None = None) -> None:
        self._caminho = caminho
        self._trava = RLock()
        self._indices: dict[str, IndiceBusca] = {}
        self._registros: tuple[RegistroIndustrial, ...] = ()
        if caminho.exists():
            self._registros = tuple(ler_csv(caminho.read_bytes().decode("utf-8-sig")))
        elif original is not None:
            self._salvar(ler_csv(original.read_bytes().decode("utf-8-sig")))

    def _salvar(self, registros: Iterable[RegistroIndustrial]) -> None:
        novos = tuple(registros)
        escrever_atomicamente(self._caminho, gravar_csv(novos))
        self._registros = novos
        self._indices.clear()

    def listar(self) -> tuple[RegistroIndustrial, ...]:
        """Devolve uma coleção que o chamador não consegue modificar."""
        with self._trava:
            return self._registros

    def inserir(self, registro: RegistroIndustrial) -> None:
        """Inclui um registro se o UDI estiver livre."""
        self.importar([registro])

    def importar(self, registros: Iterable[RegistroIndustrial]) -> int:
        """Mescla um lote em transação única, rejeitando conflitos de UDI."""
        novos = tuple(registros)
        with self._trava:
            chaves = {registro.identificador for registro in self._registros}
            for registro in novos:
                if registro.identificador in chaves:
                    raise ValueError(f"UDI {registro.identificador} já cadastrado.")
                chaves.add(registro.identificador)
            if novos:
                self._salvar((*self._registros, *novos))
        return len(novos)

    def atualizar(self, identificador: int, alteracoes: Mapping) -> RegistroIndustrial:
        """Substitui a observação no mesmo UDI, preservando a procedência."""
        validar_alteracoes(alteracoes)
        with self._trava:
            posicao = self._posicao(identificador)
            novos = list(self._registros)
            registro = replace(novos[posicao], **alteracoes)
            if registro == novos[posicao]:
                return novos[posicao]
            novos[posicao] = registro
            self._salvar(novos)
            return registro

    def _posicao(self, identificador: int) -> int:
        for posicao, registro in enumerate(self._registros):
            if registro.identificador == identificador:
                return posicao
        raise LookupError("Registro não encontrado.")

    def remover(self, identificador: int) -> None:
        """Remove o UDI e invalida todos os índices somente após persistir."""
        with self._trava:
            posicao = self._posicao(identificador)
            self._salvar(self._registros[:posicao] + self._registros[posicao + 1 :])

    def consultar(self, identificador: int, estrategia: str) -> dict:
        """Mede preparo a frio e consulta, com contagem em passagem separada."""
        if estrategia not in BUSCAS:
            raise ValueError("Estratégia de busca inválida.")
        with self._trava:
            reutilizado = estrategia in self._indices
            preparo_ns = 0
            if not reutilizado:
                inicio = perf_counter_ns()
                self._indices[estrategia] = BUSCAS[estrategia].preparar(self._registros)
                preparo_ns = perf_counter_ns() - inicio
            indice = self._indices[estrategia]
            return medir_consulta(
                indice, identificador, estrategia, preparo_ns, reutilizado
            )


def medir_consulta(
    indice: IndiceBusca,
    identificador: int,
    estrategia: str,
    preparo_ns: int,
    reutilizado: bool = False,
) -> dict:
    """Mede uma consulta sem instrumentação e conta posições em outra passagem."""
    inicio = perf_counter_ns()
    registro = indice.buscar(identificador)
    consulta_ns = perf_counter_ns() - inicio
    metricas = Metricas()
    indice.buscar(identificador, metricas)
    return {
        "registro": registro,
        "estrategia": estrategia,
        "passos": metricas.comparacoes,
        "preparo_ns": preparo_ns,
        "consulta_ns": consulta_ns,
        "indice_reutilizado": reutilizado,
    }
