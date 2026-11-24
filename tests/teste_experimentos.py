import pytest

from core.algoritmos import (
    ORDENS,
    BuscaBinaria,
    BuscaSequencial,
    EstrategiaBusca,
    EstrategiaOrdenacao,
)
from core.dominio import RegistroIndustrial
from core.experimentos import (
    ColecaoCarga,
    ConfiguracaoExperimento,
    ExecutorExperimentos,
)


@pytest.mark.parametrize("aba", ["ordenacao", "busca", "hash", "sistema"])
def test_experimentos(aba):
    base = [RegistroIndustrial(i, torque=i % 4) for i in range(1, 41)]
    configuracao = ConfiguracaoExperimento.criar(
        {
            "aba": aba,
            "tamanhos": [20],
            "repeticoes": 5,
            "consultas": 1000,
            "operacoes": 20,
            "semente": 14,
        }
    )
    resultado = ExecutorExperimentos().executar(configuracao, base)
    assert resultado["brutos"] and resultado["resumo"]
    assert all(linha["tempo_ns"] > 0 for linha in resultado["brutos"])
    assert all(linha["pico_bytes"] >= 0 for linha in resultado["brutos"])
    assert all(linha["repeticoes"] == 5 for linha in resultado["resumo"])
    if aba == "hash":
        assert {linha["carga_alvo"] for linha in resultado["resumo"]} == {
            0.25,
            0.5,
            0.75,
        }
    if aba == "busca":
        assert resultado["compensacao"]


def test_executor_recebe_ordenadores_por_composicao():
    class OrdenacaoObservada(EstrategiaOrdenacao):
        def __init__(self, original):
            self.original = original
            self.chamadas_instrumentadas = 0

        def ordenar(self, registros, chave, metricas=None):
            if metricas is not None:
                self.chamadas_instrumentadas += 1
            return self.original.ordenar(registros, chave, metricas)

        def _ordenar(self, pares, metricas):
            raise AssertionError(
                "A estratégia deve ser invocada pelo contrato público."
            )

    insercao = OrdenacaoObservada(ORDENS["insercao"])
    heap = OrdenacaoObservada(ORDENS["heap"])
    executor = ExecutorExperimentos(
        ordenacoes={**ORDENS, "insercao": insercao, "heap": heap}
    )
    cfg = ConfiguracaoExperimento.criar({"aba": "ordenacao", "tamanhos": [2]})
    executor.executar(cfg, [RegistroIndustrial(2), RegistroIndustrial(1)])
    assert insercao.chamadas_instrumentadas == heap.chamadas_instrumentadas == 4


def test_executor_usa_busca_injetada_na_carga_e_reconstrucao():
    preparacoes = []
    consultas = []

    class BinariaObservada(BuscaBinaria):
        def preparar(self, registros):
            preparacoes.append(len(registros))
            return super().preparar(registros)

        def buscar(self, identificador, metricas=None):
            consultas.append(identificador)
            return super().buscar(identificador, metricas)

    executor = ExecutorExperimentos(buscas={"binaria": BinariaObservada()})
    cfg = ConfiguracaoExperimento.criar({"aba": "sistema", "tamanhos": [2]})
    resultado = executor.executar(cfg, [RegistroIndustrial(2), RegistroIndustrial(1)])
    assert len(resultado["resumo"]) == 8
    assert len(consultas) == 22_000
    assert len(preparacoes) == 5  # Reconstruções da carga dinâmica.


def test_executor_compoe_indice_independente_e_adaptador_mutavel():
    class BuscaComposta(EstrategiaBusca):
        def __init__(self, interna, nome):
            self.interna = interna
            self.nome = nome

        def preparar(self, registros):
            return self.interna.preparar(registros)

    binaria = BuscaComposta(BuscaBinaria(), "binaria")
    hash_alternativa = BuscaComposta(BuscaSequencial(), "hash")
    adaptadas = []

    def colecao(registros, metodo, busca):
        if busca is binaria or busca is hash_alternativa:
            adaptadas.append(busca.nome)
            if busca is hash_alternativa:
                return ColecaoCarga(registros, "sequencial", busca.interna)
            return ColecaoCarga(registros, metodo, busca.interna)
        return ColecaoCarga(registros, metodo, busca)

    executor = ExecutorExperimentos(
        buscas={"binaria": binaria, "hash": hash_alternativa}, colecao=colecao
    )
    base = [RegistroIndustrial(2), RegistroIndustrial(1)]
    cfg = ConfiguracaoExperimento.criar({"aba": "busca", "tamanhos": [2]})
    resultado = executor.executar(cfg, base)
    assert all("colisoes" not in r for r in resultado["brutos"])
    cfg = ConfiguracaoExperimento.criar({"aba": "sistema", "tamanhos": [2]})
    assert len(executor.executar(cfg, base)["resumo"]) == 8
    assert adaptadas.count("binaria") == adaptadas.count("hash") == 22
