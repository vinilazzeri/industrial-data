from dataclasses import FrozenInstanceError, replace

import pytest

from core.algoritmos import (
    ORDENS,
    BuscaBinaria,
    BuscaInterpolacao,
    BuscaSequencial,
    Metricas,
    TabelaHashEncadeamento,
    chave_de,
)
from core.dominio import RegistroIndustrial
from core.repositorio import RepositorioRegistros, gravar_csv, ler_csv


@pytest.mark.parametrize("valores", [[], [4], [1, 2, 3], [3, 2, 1], [2, 1, 2, 1]])
def test_ordenacoes(valores):
    registros = [RegistroIndustrial(i, torque=v) for i, v in enumerate(valores[::-1])]
    registros.reverse()
    chave = chave_de("torque")
    for estrategia in ORDENS.values():
        assert estrategia.ordenar(registros, chave, Metricas()) == sorted(
            registros, key=chave
        )
    assert [r.identificador for r in registros] == list(reversed(range(len(valores))))


@pytest.mark.parametrize("ids", [[], [9], [0, 17, 93, 10**40]])
def test_buscas(ids):
    registros = [RegistroIndustrial(i) for i in ids]
    for busca in (BuscaSequencial(), BuscaBinaria(), BuscaInterpolacao()):
        indice = busca.preparar(registros)
        for alvo in [*ids, 1, 20, 10**41]:
            assert indice.buscar(alvo, Metricas()) == next(
                (r for r in registros if r.identificador == alvo), None
            )


@pytest.mark.parametrize("capacidade", [4, 6, 12])
def test_hash(capacidade):
    tabela = TabelaHashEncadeamento(capacidade)
    for chave in (0, capacidade, 2 * capacidade):
        tabela.inserir(RegistroIndustrial(chave))
    assert tabela.diagnostico()["fator_carga"] == 3 / capacidade
    assert tabela.diagnostico()["colisoes"] == 2
    metricas = Metricas()
    assert tabela.buscar(2 * capacidade, metricas).identificador == 2 * capacidade
    assert metricas.comparacoes == 3
    assert tabela.remover(capacidade)
    assert tabela.buscar(capacidade) is None
    assert tabela.buscar(2 * capacidade)


def test_repositorio(tmp_path):
    caminho = tmp_path / "trabalho.csv"
    repositorio = RepositorioRegistros(caminho)
    assert repositorio.listar() == ()
    with pytest.raises(ValueError):
        RegistroIndustrial(-1)
    registro = RegistroIndustrial(0)
    with pytest.raises(FrozenInstanceError):
        registro.identificador = 7
    repositorio.inserir(registro)
    with pytest.raises(ValueError):
        repositorio.inserir(registro)
    with pytest.raises(ValueError):
        repositorio.atualizar(0, {"identificador": 4})
    assert repositorio.consultar(0, "hash")["registro"] == registro
    revisado = replace(registro, torque=62)
    repositorio.atualizar(0, {"torque": 62})
    for estrategia in ("sequencial", "binaria", "interpolacao", "hash"):
        assert repositorio.consultar(0, estrategia)["registro"] == revisado
    exportado = gravar_csv(repositorio.listar())
    assert ler_csv(exportado) == [revisado]
    assert RepositorioRegistros(caminho).listar() == (revisado,)
    repositorio.remover(0)
    for estrategia in ("sequencial", "binaria", "interpolacao", "hash"):
        assert repositorio.consultar(0, estrategia)["registro"] is None
    repositorio.importar(ler_csv(exportado))
    assert repositorio.listar() == (revisado,)


def test_importacao_atomica(tmp_path, monkeypatch):
    caminho = tmp_path / "registros.csv"
    repositorio = RepositorioRegistros(caminho)
    primeiro, segundo = RegistroIndustrial(1), RegistroIndustrial(2)
    repositorio.inserir(primeiro)
    assert repositorio.consultar(1, "binaria")["registro"] == primeiro
    with pytest.raises(ValueError):
        repositorio.importar([segundo, primeiro])
    assert repositorio.listar() == (primeiro,)
    with pytest.raises(ValueError):
        ler_csv(gravar_csv([primeiro, primeiro]))

    def sem_espaco(*args):
        raise OSError("Disco indisponível.")

    monkeypatch.setattr("core.repositorio.escrever_atomicamente", sem_espaco)
    with pytest.raises(OSError):
        repositorio.remover(1)
    assert ler_csv(caminho.read_text(encoding="utf-8")) == [primeiro]
    assert repositorio.consultar(1, "binaria")["registro"] == primeiro


def test_csv_preserva_quebras_em_campo_textual(tmp_path):
    caminho = tmp_path / "registros.csv"
    registro = RegistroIndustrial(1, produto="lote A\r\nlote B")
    RepositorioRegistros(caminho).inserir(registro)
    assert RepositorioRegistros(caminho).listar() == (registro,)
