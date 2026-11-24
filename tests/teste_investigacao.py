from time import monotonic, sleep

import pytest

from core.web import criar_app


@pytest.fixture()
def cliente(tmp_path):
    return criar_app({"TESTING": True, "PASTA_INSTANCIA": tmp_path}).test_client()


def demonstrar(cliente):
    resposta = cliente.post("/api/ocorrencias/demonstracao")
    assert resposta.status_code == 201
    return resposta.json


def test_experimento_contextual_grava_origem_sem_substituir_referencia(cliente):
    demo = demonstrar(cliente)
    selecao = {"origem": "M-01", "ocorrencia": demo["ocorrencia"]}
    assert cliente.get("/api/experimentos/hash", query_string=selecao).json is None
    assert (
        cliente.post(
            "/api/experimentos",
            json={
                "aba": "hash",
                "selecao": selecao,
                "tamanhos": [2, 5, 10],
            },
        ).status_code
        == 202
    )
    limite = monotonic() + 12
    while monotonic() < limite:
        estado = cliente.get("/api/experimentos/estado").json
        if estado["estado"] != "Executando":
            break
        sleep(0.05)
    assert estado["estado"] == "Concluído"
    medicao = cliente.get("/api/experimentos/hash", query_string=selecao).json
    referencia = cliente.get("/api/experimentos/hash").json
    assert medicao["configuracao"]["tamanhos"] == [2, 5, 10]
    assert referencia["configuracao"]["tamanhos"] == [500, 2000, 8000]
    assert medicao["origem"]["recorte_ocorrencia"] == demo["ocorrencia"]
    assert medicao["recorte_alterado"] is False
    csv = cliente.get("/api/experimentos/hash/csv", query_string=selecao).data
    assert b"conteudo_sha256" in csv and demo["ocorrencia"].encode() in csv
    assert (
        cliente.patch(f"/api/registros/{demo['udi']}", json={"torque": 22}).status_code
        == 200
    )
    revista = cliente.get("/api/experimentos/hash", query_string=selecao).json
    assert revista["recorte_alterado"] is True
    assert revista["origem"]["conteudo_sha256"] == medicao["origem"]["conteudo_sha256"]


def test_manter_indice_em_edicao_sem_alteracao_e_reconstruir_apos_remover(cliente):
    assert (
        cliente.post(
            "/api/registros", json={"identificador": 0, "torque": 31}
        ).status_code
        == 201
    )
    caminhos = {
        nome: f"/api/registros/consulta?udi=0&estrategia={nome}"
        for nome in ("sequencial", "binaria", "interpolacao", "hash")
    }
    for caminho in caminhos.values():
        assert cliente.get(caminho).json["registro"]["torque"] == 31
    assert cliente.patch("/api/registros/0", json={"torque": 31}).status_code == 200
    assert cliente.get("/api/registros/manutencao").json["invalidos"] == []
    assert cliente.get(caminhos["hash"]).json["indice_reutilizado"]
    assert cliente.delete("/api/registros/0").status_code == 204
    assert set(cliente.get("/api/registros/manutencao").json["invalidos"]) == set(
        caminhos
    )
    for caminho in caminhos.values():
        resposta = cliente.get(caminho).json
        assert resposta["registro"] is None
        assert not resposta["indice_reutilizado"]


def test_saida_operacional_vazia_unitaria_empates_e_sistema(cliente):
    caminho = "/api/investigacao/operacoes"
    selecao = {"origem": "trabalho", "fonte": "Manual"}
    ordem = {
        "selecao": selecao,
        "operacao": "ordenacao",
        "estrategia": "todas",
        "atributo": "torque",
    }
    vazio = cliente.post(caminho, json=ordem).json
    assert vazio["equivalentes"] and vazio["maiores"] == []
    for udi in (10002, 10001):
        assert (
            cliente.post(
                "/api/registros", json={"identificador": udi, "torque": 60}
            ).status_code
            == 201
        )
        assert len(cliente.post(caminho, json=ordem).json["menores"]) == 10003 - udi
    resultado = cliente.post(caminho, json=ordem).json
    assert [r["identificador"] for r in resultado["menores"]] == [10001, 10002]
    sistema = cliente.post(
        caminho,
        json={
            "selecao": selecao,
            "operacao": "sistema",
            "udi": 10001,
            "consultas": 7,
        },
    ).json
    assert sistema["equivalentes"] and len(sistema["metricas"]) == 8
    assert all(
        r["reconstrucao_ns"] is not None
        for r in sistema["metricas"]
        if r["cenario"] == "Dinâmica"
    )


def test_demonstracao_investigacao_e_exportacao(cliente):
    assert cliente.get("/ocorrencias").status_code == 200
    vazio = cliente.get("/api/ocorrencias?origem=M-03").json
    assert vazio["ocorrencias"] == [] and vazio["quantidade"] == 0
    demo = demonstrar(cliente)
    caminho = "/api/ocorrencias?origem=M-01&ocorrencia=" + demo["ocorrencia"]
    resposta = cliente.get(caminho).json
    assert resposta["ocorrencia"]["tipo"] == "Falha"
    assert resposta["detecao"]["equipamento"] == "M-01"
    assert resposta["detecao"]["ciclo"] == resposta["ocorrencia"]["ciclo"]
    assert 1 < resposta["quantidade"] <= 30
    udi = resposta["detecao"]["identificador"]
    url = "/api/investigacao/operacoes"
    contexto = resposta["selecao"]
    ordem = cliente.post(
        url,
        json={
            "selecao": contexto,
            "operacao": "ordenacao",
            "estrategia": "todas",
            "atributo": "torque",
        },
    ).json
    assert ordem["equivalentes"]
    assert len(ordem["metricas"]) == 3
    assert all(
        item["tempo_ns"] > 0 and item["comparacoes"] > 0 for item in ordem["metricas"]
    )
    busca = cliente.post(
        url,
        json={
            "selecao": contexto,
            "operacao": "busca",
            "estrategia": "todas",
            "udi": udi,
        },
    ).json
    assert busca["equivalentes"] and busca["registro"]["identificador"] == udi
    assert len(busca["metricas"]) == 4
    exportacao = cliente.get(caminho.replace("ocorrencias?", "ocorrencias/csv?"))
    assert (
        b"temperatura_processo" in exportacao.data
        and str(udi).encode() in exportacao.data
    )
    assert cliente.get("/api/ocorrencias?origem=M-02").json["quantidade"] == 0


def test_ciclo_progressivo_cria_ocorrencia_com_udi_e_filtros_preservados(cliente):
    equipamento = "/api/maquinas/M-03"
    assert (
        cliente.patch(
            equipamento,
            json={
                "ciclos": 5,
                "modo": "Desgaste acelerado",
                "limites_locais": {"desgaste": 15},
            },
        ).status_code
        == 200
    )
    assert cliente.post(equipamento + "/iniciar").status_code == 200
    for _ in range(2):
        execucao = cliente.get(equipamento).json["execucao"]
        resposta = cliente.post(
            "/api/operacao/avancar",
            json={"versoes": {"M-03": {k: execucao[k] for k in ("id", "versao")}}},
        ).json
        assert resposta["gerados"] == 1
    evento = next(e for e in resposta["painel"]["eventos"] if e["estado"] == "Falha")
    recorte = {"origem": "M-03", "ocorrencia": evento["ocorrencia"]}
    ocorrencia = cliente.get("/api/ocorrencias", query_string=recorte).json
    assert ocorrencia["detecao"]["ciclo"] == evento["ciclo"] == 2
    assert ocorrencia["detecao"]["equipamento"] == "M-03"
    udi = ocorrencia["detecao"]["identificador"]
    filtros = {**recorte, "fonte": "Manual"}
    assert cliente.get("/api/registros", query_string=filtros).json["total"] == 0
    assert (
        cliente.get(
            "/api/registros/consulta",
            query_string={
                **filtros,
                "udi": udi,
                "estrategia": "hash",
            },
        ).json["registro"]
        is None
    )
    assert (
        cliente.get("/api/investigacao/origem", query_string=filtros).json["quantidade"]
        == 0
    )
    assert cliente.get("/api/ocorrencias?origem=M-01").json["ocorrencias"] == []


def test_correcao_e_remocao_respeitadas_no_recorte(cliente):
    demo = demonstrar(cliente)
    contexto = {"origem": "M-01", "ocorrencia": demo["ocorrencia"]}
    corpo = {
        "selecao": contexto,
        "operacao": "busca",
        "estrategia": "hash",
        "udi": demo["udi"],
    }
    url = "/api/investigacao/operacoes"
    assert cliente.post(url, json=corpo).json["registro"]
    assert cliente.post(url, json=corpo).json["metricas"][0]["indice_reutilizado"]
    assert (
        cliente.patch(
            f"/api/registros/{demo['udi']}", json={"equipamento": "M-02"}
        ).status_code
        == 400
    )
    assert (
        cliente.patch(f"/api/registros/{demo['udi']}", json={"torque": 24}).status_code
        == 200
    )
    assert cliente.post(url, json=corpo).json["registro"]["torque"] == 24
    assert cliente.delete(f"/api/registros/{demo['udi']}").status_code == 204
    assert (
        cliente.post(url, json={**corpo, "estrategia": "todas"}).json["registro"]
        is None
    )
    ocorrencia = cliente.get(
        "/api/ocorrencias",
        query_string={**contexto, "inicio": demo["ciclo"], "fim": demo["ciclo"]},
    ).json
    assert ocorrencia["detecao"] is None
    assert ocorrencia["quantidade"] == 0
    assert ocorrencia["ocorrencia"]["id"] == demo["ocorrencia"]


def test_hash_em_copia_e_historia_pequena(cliente):
    demo = demonstrar(cliente)
    selecao = {"origem": "M-01", "inicio": demo["ciclo"], "fim": demo["ciclo"]}
    url = "/api/investigacao/operacoes"
    hash_demo = cliente.post(
        url,
        json={
            "selecao": selecao,
            "operacao": "hash",
            "udi": demo["udi"],
            "capacidade": 1,
        },
    ).json
    assert hash_demo["equivalentes"]
    assert hash_demo["diagnostico"]["colisoes"] >= 1
    assert hash_demo["consulta_apos_remocao"] is None
    assert cliente.get(
        f"/api/registros/consulta?udi={demo['udi']}&estrategia=hash"
    ).json["registro"]
    assert (
        cliente.post(
            "/api/experimentos",
            json={
                "aba": "busca",
                "selecao": selecao,
                "tamanhos": [500, 2000, 8000],
            },
        ).status_code
        == 400
    )
