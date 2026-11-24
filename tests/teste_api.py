from io import BytesIO
from time import monotonic, sleep

import pytest

from core.web import criar_app


@pytest.fixture()
def cliente(tmp_path):
    app = criar_app({"TESTING": True, "PASTA_INSTANCIA": tmp_path})
    return app.test_client()


@pytest.mark.parametrize(
    "pagina", ["/", "/maquinas", "/registros", "/laboratorio", "/relatorios", "/dados"]
)
def test_paginas(cliente, pagina):
    assert cliente.get(pagina).status_code == 200


def test_crud_consultas_e_csv(cliente):
    assert cliente.get("/api/registros").json["total"] == 10000
    assert cliente.post("/api/registros", json={"identificador": -1}).status_code == 400
    assert cliente.post("/api/registros", json={"identificador": 0}).status_code == 201
    assert cliente.post("/api/registros", json={"identificador": 0}).status_code == 400
    assert cliente.patch("/api/registros/0", json={"torque": 53}).json["torque"] == 53
    assert (
        cliente.patch("/api/registros/0", json={"identificador": 9}).status_code == 400
    )
    for metodo in ("sequencial", "binaria", "interpolacao", "hash"):
        consulta = cliente.get(
            f"/api/registros/consulta?udi=0&estrategia={metodo}"
        ).json
        assert consulta["registro"]["torque"] == 53
        assert consulta["consulta_ns"] >= 0
    csv = cliente.get("/api/registros/csv?fonte=Manual").data
    assert cliente.delete("/api/registros/0").status_code == 204
    assert (
        cliente.get("/api/registros/consulta?udi=0&estrategia=hash").json["registro"]
        is None
    )
    retorno = cliente.post(
        "/api/registros/importar", data={"arquivo": (BytesIO(csv), "reg.csv")}
    )
    assert retorno.status_code == 201 and retorno.json["importados"] == 1
    assert cliente.get("/api/registros?ordem=invalida").status_code == 400


def test_simulacao_e_configuracao(cliente):
    assert (
        cliente.patch("/api/configuracoes", json={"repeticoes": 2}).status_code == 400
    )
    assert (
        cliente.patch("/api/configuracoes", json={"semente": 220}).json["semente"]
        == 220
    )
    assert cliente.patch("/api/maquinas/M-01", json={"ciclos": 3}).status_code == 200
    assert cliente.post("/api/maquinas/M-01/executar").json["gerados"] == 3
    assert cliente.get("/api/maquinas/M-02").json["estado"] == "Parada"
    assert cliente.post("/api/maquinas/M-01/falha").json["gerados"] == 1
    assert cliente.post("/api/maquinas/M-01/executar").json["gerados"] == 0
    assert cliente.post("/api/maquinas/M-01/reiniciar").status_code == 200
    assert cliente.get("/api/maquinas/M-01/estatisticas").json["falhas"] == 1
    assert cliente.get("/api/registros?fonte=Simulação").json["total"] == 4
    assert cliente.get("/api/maquinas/M-01/csv").mimetype == "text/csv"


def test_trabalho_em_segundo_plano(cliente):
    resposta = cliente.post("/api/experimentos", json={"aba": "hash", "tamanhos": [20]})
    assert resposta.status_code == 202
    limite = monotonic() + 10
    while monotonic() < limite:
        estado = cliente.get("/api/experimentos/estado").json["estado"]
        if estado != "Executando":
            break
        sleep(0.03)
    assert estado == "Concluído"
    assert len(cliente.get("/api/experimentos/hash").json["resumo"]) == 3
    bruto = cliente.get("/api/experimentos/hash/csv?tipo=brutos")
    assert bruto.mimetype == "text/csv"
    assert b"unidade_tempo" in bruto.data


def test_edicao_simulada_preserva_historico_e_invalida_indices(tmp_path):
    cfg = {"TESTING": True, "PASTA_INSTANCIA": tmp_path}
    cliente = criar_app(cfg).test_client()
    cliente.patch("/api/maquinas/M-01", json={"ciclos": 1})
    cliente.post("/api/maquinas/M-01/executar")
    caminho = "/api/registros/10001"
    busca = "/api/registros/consulta?udi=10001&estrategia="
    metodos = ("sequencial", "binaria", "interpolacao", "hash")
    for metodo in metodos:
        assert cliente.get(busca + metodo).json["registro"]["fonte"] == "Simulação"
    assert cliente.patch(caminho, json={"torque": 99}).json["torque"] == 99
    for metodo in metodos:
        assert cliente.get(busca + metodo).json["registro"]["torque"] == 99
    assert cliente.delete(caminho).status_code == 204
    for cliente_atual in (cliente, criar_app(cfg).test_client()):
        for metodo in metodos:
            assert cliente_atual.get(busca + metodo).json["registro"] is None
        assert (
            cliente_atual.get("/api/maquinas/M-01").json["historico"][0]["torque"] != 99
        )
        assert cliente_atual.get(caminho).status_code == 405
        assert cliente_atual.patch(caminho, json={"torque": 1}).status_code == 404
        assert cliente_atual.get("/api/registros?fonte=Simulação").json["total"] == 0


def test_udi_grande_permanece_exato_em_json(cliente):
    udi = str(2**78 + 271)
    retorno = cliente.post("/api/registros", json={"identificador": udi})
    assert retorno.json["identificador"] == udi
    for metodo in ("sequencial", "binaria", "interpolacao", "hash"):
        retorno = cliente.get(f"/api/registros/consulta?udi={udi}&estrategia={metodo}")
        assert retorno.json["registro"]["identificador"] == udi
