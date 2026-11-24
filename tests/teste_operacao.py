from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import pytest

from core.simulacao import SimuladorIndustrial
from core.web import criar_app


@pytest.fixture()
def app(tmp_path):
    return criar_app({"TESTING": True, "PASTA_INSTANCIA": tmp_path})


@pytest.fixture()
def cliente(app):
    return app.test_client()


def estado(cliente, codigo="M-01"):
    return cliente.get(f"/api/maquinas/{codigo}").json


def avancar(cliente, *maquinas):
    versoes = {
        m["codigo"]: {"id": m["execucao"]["id"], "versao": m["execucao"]["versao"]}
        for m in maquinas
    }
    return cliente.post("/api/operacao/avancar", json={"versoes": versoes})


def test_frota_pausa_retomada_e_interrupcao(cliente):
    for codigo in ("M-01", "M-02", "M-03"):
        assert (
            cliente.patch(f"/api/maquinas/{codigo}", json={"ciclos": 3}).status_code
            == 200
        )
    assert cliente.post("/api/maquinas/iniciar").json["iniciadas"] == 3
    frota = [estado(cliente, codigo) for codigo in ("M-01", "M-02", "M-03")]
    assert [m["ciclo"] for m in frota] == [0, 0, 0]
    assert avancar(cliente, *frota).json["gerados"] == 3
    primeira = estado(cliente)
    assert primeira["sensores"]["rpm"] > 0
    assert cliente.post("/api/maquinas/M-01/pausar").status_code == 200
    pausada = estado(cliente)
    assert pausada["estado"] == "Operando"
    assert pausada["execucao"]["fase"] == "Pausada"
    assert pausada["sensores"] == primeira["sensores"]
    assert cliente.post("/api/maquinas/M-01/falha").status_code == 409
    assert (
        avancar(
            cliente, primeira, estado(cliente, "M-02"), estado(cliente, "M-03")
        ).json["gerados"]
        == 2
    )
    assert estado(cliente)["ciclo"] == 1
    assert cliente.post("/api/maquinas/M-01/retomar").status_code == 200
    assert avancar(cliente, primeira).json["gerados"] == 0
    assert avancar(cliente, estado(cliente)).json["gerados"] == 1
    assert cliente.post("/api/maquinas/M-01/interromper").status_code == 200
    assert estado(cliente)["sensores"]["rpm"] == 0
    assert estado(cliente)["execucao"]["fase"] == "Interrompida"
    assert estado(cliente)["estatisticas"]["quantidade"] == 2
    eventos = cliente.get("/api/maquinas/M-01/historico").json["eventos"]
    assert {e["descricao"] for e in eventos} >= {
        "Máquina iniciada",
        "Máquina pausada",
        "Máquina retomada",
        "Simulação interrompida",
    }


@pytest.mark.parametrize("codigo", ["M-01", "M-02", "M-03"])
def test_inicio_individual(cliente, codigo):
    assert cliente.post(f"/api/maquinas/{codigo}/iniciar").json["iniciadas"] == 1
    painel = cliente.get("/api/painel?leve=1").json
    assert painel["operando"] == 1
    assert [
        m["codigo"]
        for m in painel["maquinas"]
        if m["execucao"]["fase"] == "Em execução"
    ] == [codigo]
    assert avancar(cliente, estado(cliente, codigo)).json["gerados"] == 1


def test_lote_falha_alerta_e_limites_locais(cliente):
    url = "/api/maquinas/M-02"
    assert (
        cliente.patch(
            url,
            json={
                "rpm": 1400,
                "torque": 73,
                "ciclos": 8,
                "temperatura_c": 37.0,
                "limites_locais": {"torque": 80, "temperatura_c": 50.85},
            },
        ).status_code
        == 200
    )
    assert cliente.post(url + "/iniciar").status_code == 200
    assert cliente.post(url + "/iniciar").status_code == 409
    assert cliente.patch(url, json={"rpm": 2000}).status_code == 409
    assert avancar(cliente, estado(cliente, "M-02")).json["gerados"] == 1
    alerta = estado(cliente, "M-02")
    assert alerta["estado"] == "Alerta"
    assert alerta["indicadores"]["torque"]["nivel"] == "alerta"
    assert alerta["indicadores"]["rpm"]["nivel"] == "normal"
    assert alerta["sensores"]["temperatura_c"] == pytest.approx(37, abs=1)
    assert cliente.post(url + "/falha").status_code == 200
    falha = estado(cliente, "M-02")
    assert falha["estado"] == "Falha" and falha["sensores"]["rpm"] == 0
    assert falha["motivos"][0]["campo"] == "manual"
    assert avancar(cliente, alerta).json["gerados"] == 0
    assert cliente.post(url + "/iniciar").status_code == 409
    assert cliente.post(url + "/reiniciar").status_code == 200
    reiniciada = estado(cliente, "M-02")
    assert reiniciada["estatisticas"]["falhas"] == 1
    assert reiniciada["sensores"]["desgaste"] == 0
    assert reiniciada["estatisticas"]["desgaste_acumulado"] > 0
    assert estado(cliente)["ciclo"] == 0
    csv = cliente.get(url + "/csv")
    assert b"10001" in BytesIO(csv.data).read()
    consulta = cliente.get("/api/registros/consulta?udi=10001&estrategia=hash").json
    assert consulta["registro"]["equipamento"] == "M-02"


def test_falha_natural_e_conclusao(cliente):
    assert (
        cliente.patch(
            "/api/maquinas/M-01",
            json={
                "modo": "Desgaste acelerado",
                "ciclos": 6,
                "limites_locais": {"desgaste": 15},
            },
        ).status_code
        == 200
    )
    assert cliente.patch("/api/maquinas/M-02", json={"ciclos": 2}).status_code == 200
    cliente.post("/api/maquinas/iniciar")
    for _ in range(2):
        assert (
            avancar(cliente, estado(cliente), estado(cliente, "M-02")).json["gerados"]
            == 2
        )
    primeira, segunda = estado(cliente), estado(cliente, "M-02")
    assert primeira["execucao"]["fase"] == "Falhou"
    assert primeira["motivos"][0]["campo"] == "desgaste"
    assert segunda["execucao"]["fase"] == "Concluída"
    assert segunda["estado"] == "Parada"
    assert segunda["execucao"]["realizados"] == 2
    historico = cliente.get("/api/maquinas/M-02/historico?inicio=2&fim=2").json
    assert [r["ciclo"] for r in historico["historico"]] == [2]
    assert cliente.get("/api/maquinas/M-02/historico?inicio=4&fim=2").status_code == 400


def test_requisicoes_duplicadas_geram_um_ciclo(app):
    cliente = app.test_client()
    cliente.post("/api/maquinas/M-01/iniciar")
    maquina = estado(cliente)
    with ThreadPoolExecutor(max_workers=2) as executor:
        resultados = list(
            executor.map(
                lambda _: avancar(app.test_client(), maquina).json["gerados"], range(2)
            )
        )
    assert sorted(resultados) == [0, 1]
    assert estado(cliente)["ciclo"] == 1


def test_comando_de_um_lote_antigo_nao_interrompe_o_novo(cliente):
    url = "/api/maquinas/M-01"
    cliente.post(url + "/iniciar")
    antigo = estado(cliente)["execucao"]["id"]
    cliente.post(url + "/interromper")
    cliente.post(url + "/iniciar")
    assert cliente.post(url + "/pausar", json={"lote": antigo}).status_code == 409
    assert estado(cliente)["execucao"]["fase"] == "Em execução"


def test_persistencia_e_reprodutibilidade_com_pausa(tmp_path):
    caminho_a, caminho_b = (tmp_path / f"{i}.csv" for i in range(2))
    a, b = SimuladorIndustrial(caminho_a), SimuladorIndustrial(caminho_b)
    for simulador in (a, b):
        simulador.configurar("M-01", {"ciclos": 3})
        simulador.iniciar("M-01", 55)
    for rodada in range(3):
        for simulador in (a, b):
            execucao = simulador.detalhar("M-01")["execucao"]
            simulador.avancar(
                {"M-01": {"id": execucao["id"], "versao": execucao["versao"]}}, 0
            )
        if rodada == 0:
            b.comandar("M-01", "pausar")
            b = SimuladorIndustrial(caminho_b)
            assert b.detalhar("M-01")["execucao"]["fase"] == "Pausada"
            b.comandar("M-01", "retomar")
    assert a.registros() == b.registros()
