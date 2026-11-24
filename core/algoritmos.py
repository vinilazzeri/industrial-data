"""Estratégias próprias de ordenação, busca e indexação."""

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from .dominio import RegistroIndustrial, inteiro

Chave = Callable[[RegistroIndustrial], tuple[float | int, int]]
ATRIBUTOS = (
    "identificador",
    "torque",
    "temperatura_processo",
    "temperatura_ar",
    "rpm",
    "desgaste",
)


def chave_de(atributo: str) -> Chave:
    """Usa um atributo numérico e desempata pelo UDI."""
    if atributo not in ATRIBUTOS:
        raise ValueError("Atributo de ordenação inválido.")
    return lambda registro: (getattr(registro, atributo), registro.identificador)


@dataclass(slots=True)
class Metricas:
    """Contadores locais da passagem instrumentada."""

    comparacoes: int = 0
    movimentacoes: int = 0
    espaco_auxiliar: int = 0


class EstrategiaOrdenacao(ABC):
    """Ordena uma cópia e mantém a entrada intacta."""

    def ordenar(
        self,
        registros: Sequence[RegistroIndustrial],
        chave: Chave,
        metricas: Metricas | None = None,
    ) -> list[RegistroIndustrial]:
        """Materializa chaves uma vez, ordena e devolve os registros."""
        pares = [(chave(registro), registro) for registro in registros]
        if metricas is not None:
            metricas.espaco_auxiliar = len(pares) * (2 if self.usa_buffer else 1)
        self._ordenar(pares, metricas)
        return [registro for _, registro in pares]

    usa_buffer = False

    @abstractmethod
    def _ordenar(self, pares: list, metricas: Metricas | None) -> None:
        """Ordena os pares privados."""


class OrdenacaoPorInsercao(EstrategiaOrdenacao):
    """Expande um prefixo ordenado por deslocamento."""

    def _ordenar(self, pares: list, metricas: Metricas | None) -> None:
        for indice in range(1, len(pares)):
            item = pares[indice]
            anterior = indice - 1
            while anterior >= 0:
                if metricas is not None:
                    metricas.comparacoes += 1
                if pares[anterior][0] <= item[0]:
                    break
                pares[anterior + 1] = pares[anterior]
                anterior -= 1
            if anterior + 1 != indice:
                pares[anterior + 1] = item
                if metricas is not None:
                    metricas.movimentacoes += indice - anterior


class OrdenacaoPorIntercalacao(EstrategiaOrdenacao):
    """Divide pela metade e intercala usando um único vetor auxiliar."""

    usa_buffer = True

    def _ordenar(self, pares: list, metricas: Metricas | None) -> None:
        auxiliar = [None] * len(pares)

        def intercalar(inicio: int, meio: int, fim: int) -> None:
            esquerda, direita = inicio, meio
            for destino in range(inicio, fim):
                if esquerda < meio and direita < fim and metricas is not None:
                    metricas.comparacoes += 1
                if direita >= fim or (
                    esquerda < meio and pares[esquerda][0] <= pares[direita][0]
                ):
                    auxiliar[destino] = pares[esquerda]
                    esquerda += 1
                else:
                    auxiliar[destino] = pares[direita]
                    direita += 1
            for destino in range(inicio, fim):
                pares[destino] = auxiliar[destino]
            if metricas is not None:
                metricas.movimentacoes += 2 * (fim - inicio)

        def dividir(inicio: int, fim: int) -> None:
            if fim - inicio <= 1:
                return
            meio = (inicio + fim) // 2
            dividir(inicio, meio)
            dividir(meio, fim)
            intercalar(inicio, meio, fim)

        dividir(0, len(pares))


class OrdenacaoPorHeap(EstrategiaOrdenacao):
    """Constrói um heap máximo e move a raiz para o sufixo ordenado."""

    def _ordenar(self, pares: list, metricas: Metricas | None) -> None:
        def trocar(a: int, b: int) -> None:
            pares[a], pares[b] = pares[b], pares[a]
            if metricas is not None:
                metricas.movimentacoes += 2

        def descer(raiz: int, fim: int) -> None:
            while (filho := 2 * raiz + 1) < fim:
                if filho + 1 < fim:
                    if metricas is not None:
                        metricas.comparacoes += 1
                    if pares[filho + 1][0] > pares[filho][0]:
                        filho += 1
                if metricas is not None:
                    metricas.comparacoes += 1
                if pares[raiz][0] >= pares[filho][0]:
                    break
                trocar(raiz, filho)
                raiz = filho

        for raiz in range(len(pares) // 2 - 1, -1, -1):
            descer(raiz, len(pares))
        for fim in range(len(pares) - 1, 0, -1):
            trocar(0, fim)
            descer(0, fim)


class IndiceBusca(Protocol):
    """Contrato de consulta sobre uma estrutura preparada."""

    def buscar(
        self, identificador: int, metricas: Metricas | None = None
    ) -> RegistroIndustrial | None:
        """Devolve o registro associado à chave ou ausência."""


class EstrategiaBusca(ABC):
    """Prepara um índice independente para consultas por identificador."""

    @abstractmethod
    def preparar(self, registros: Sequence[RegistroIndustrial]) -> IndiceBusca:
        """Prepara a estrutura requerida pela estratégia."""


class BuscaSequencial(EstrategiaBusca):
    """Percorre os registros na ordem recebida."""

    def __init__(self, registros: Sequence[RegistroIndustrial] = ()) -> None:
        self._registros = registros

    def preparar(self, registros: Sequence[RegistroIndustrial]) -> IndiceBusca:
        """Compartilha a visão de entrada, mantida estável pelo chamador."""
        return BuscaSequencial(registros)

    def buscar(
        self, identificador: int, metricas: Metricas | None = None
    ) -> RegistroIndustrial | None:
        """Compara cada chave examinada até encontrar a primeira igual."""
        for registro in self._registros:
            if metricas is not None:
                metricas.comparacoes += 1
            if registro.identificador == identificador:
                return registro
        return None


class BuscaOrdenada(BuscaSequencial):
    """Compartilha a preparação das estratégias que exigem ordem."""

    def preparar(self, registros: Sequence[RegistroIndustrial]) -> IndiceBusca:
        """Ordena manualmente por UDI com Merge Sort."""
        return type(self)(
            OrdenacaoPorIntercalacao().ordenar(registros, chave_de("identificador"))
        )


class BuscaBinaria(BuscaOrdenada):
    """Reduz à metade o intervalo candidato a cada consulta da chave."""

    def buscar(
        self, identificador: int, metricas: Metricas | None = None
    ) -> RegistroIndustrial | None:
        """Consulta chaves ordenadas e usa um passo por posição examinada."""
        inicio, fim = 0, len(self._registros) - 1
        while inicio <= fim:
            meio = (inicio + fim) // 2
            registro = self._registros[meio]
            if metricas is not None:
                metricas.comparacoes += 1
            if registro.identificador == identificador:
                return registro
            if registro.identificador < identificador:
                inicio = meio + 1
            else:
                fim = meio - 1
        return None


class BuscaInterpolacao(BuscaOrdenada):
    """Estima a posição pela distância inteira entre chaves."""

    def buscar(
        self, identificador: int, metricas: Metricas | None = None
    ) -> RegistroIndustrial | None:
        """Consulta um intervalo ordenado com proteção de limites e amplitude."""
        inicio, fim = 0, len(self._registros) - 1
        while inicio <= fim:
            menor = self._registros[inicio].identificador
            maior = self._registros[fim].identificador
            if identificador < menor or identificador > maior:
                return None
            if menor == maior:
                posicao = inicio
            else:
                posicao = inicio + (identificador - menor) * (fim - inicio) // (
                    maior - menor
                )
            registro = self._registros[posicao]
            if metricas is not None:
                metricas.comparacoes += 1
            if registro.identificador == identificador:
                return registro
            if registro.identificador < identificador:
                inicio = posicao + 1
            else:
                fim = posicao - 1
        return None


class TabelaHashEncadeamento:
    """Indexa o UDI por resto da divisão e mantém uma lista em cada balde."""

    def __init__(self, capacidade: int) -> None:
        self._capacidade = inteiro(capacidade, "Capacidade", 1)
        self._baldes: list[list[RegistroIndustrial]] = [
            [] for _ in range(self._capacidade)
        ]
        self._quantidade = 0
        self._colisoes = 0

    def _balde(self, identificador: int) -> list[RegistroIndustrial]:
        return self._baldes[identificador % self._capacidade]

    def inserir(self, registro: RegistroIndustrial) -> None:
        """Insere ou substitui uma chave, contando apenas novas colisões."""
        balde = self._balde(registro.identificador)
        for indice, anterior in enumerate(balde):
            if anterior.identificador == registro.identificador:
                balde[indice] = registro
                return
        self._colisoes += bool(balde)
        balde.append(registro)
        self._quantidade += 1

    def buscar(
        self, identificador: int, metricas: Metricas | None = None
    ) -> RegistroIndustrial | None:
        """Examina exclusivamente o balde mapeado pelo identificador."""
        for registro in self._balde(identificador):
            if metricas is not None:
                metricas.comparacoes += 1
            if registro.identificador == identificador:
                return registro
        return None

    def remover(self, identificador: int) -> bool:
        """Remove uma chave, preservando os demais elementos do balde."""
        balde = self._balde(identificador)
        for indice, registro in enumerate(balde):
            if registro.identificador == identificador:
                del balde[indice]
                self._quantidade -= 1
                return True
        return False

    def diagnostico(self) -> dict[str, int | float]:
        """Resume a ocupação corrente e as colisões acumuladas."""
        ocupados = sum(bool(balde) for balde in self._baldes)
        return {
            "capacidade": self._capacidade,
            "fator_carga": self._quantidade / self._capacidade,
            "colisoes": self._colisoes,
            "baldes_ocupados": ocupados,
            "balde_maximo": max(map(len, self._baldes)),
            "media_balde_ocupado": self._quantidade / ocupados if ocupados else 0,
        }


class BuscaHash(EstrategiaBusca):
    """Prepara um índice hash com capacidade explícita ou carga de até 0,75."""

    def __init__(self, capacidade: int | None = None) -> None:
        self._capacidade = capacidade

    def preparar(
        self, registros: Sequence[RegistroIndustrial]
    ) -> TabelaHashEncadeamento:
        """Insere cada registro em uma tabela exclusiva da execução."""
        capacidade = self._capacidade or max(1, (4 * len(registros) + 2) // 3)
        tabela = TabelaHashEncadeamento(capacidade)
        for registro in registros:
            tabela.inserir(registro)
        return tabela


ORDENS = {
    "insercao": OrdenacaoPorInsercao(),
    "intercalacao": OrdenacaoPorIntercalacao(),
    "heap": OrdenacaoPorHeap(),
}
BUSCAS = {
    "sequencial": BuscaSequencial(),
    "binaria": BuscaBinaria(),
    "interpolacao": BuscaInterpolacao(),
    "hash": BuscaHash(),
}
