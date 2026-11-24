from concurrent.futures import ThreadPoolExecutor
from csv import DictReader
from hashlib import sha256
from io import StringIO
from random import Random
from statistics import fmean
from time import monotonic, sleep

import pytest

from core.web import criar_app

CENARIOS = [
    ("M-01", 101, {}, 3, ("Normal",) * 3, None),
    ("M-01", 102, {"modo": "Sobrecarga", "torque": 50}, 3, ("Alerta",) * 3, "torque"),
    (
        "M-01",
        42,
        {"demonstracao": True},
        12,
        ("Normal",) * 9 + ("Alerta",) * 2 + ("Falha",),
        "desgaste",
    ),
    ("M-02", 201, {}, 3, ("Normal",) * 3, None),
    ("M-02", 202, {"temperatura_c": 48.85}, 3, ("Alerta",) * 3, "temperatura"),
    ("M-02", 203, {"temperatura_c": 51.85}, 3, ("Falha",), "temperatura"),
    ("M-03", 301, {}, 3, ("Normal",) * 3, None),
    ("M-03", 302, {"modo": "Sobrecarga", "torque": 57}, 3, ("Falha",), "torque"),
    (
        "M-03",
        303,
        {"modo": "Desgaste acelerado", "limites_locais": {"desgaste": 40}},
        6,
        ("Normal",) * 3 + ("Alerta", "Falha"),
        "desgaste",
    ),
]


def cliente_em(pasta):
    return criar_app({"TESTING": True, "PASTA_INSTANCIA": pasta}).test_client()


def estado(cliente, codigo):
    return cliente.get(f"/api/maquinas/{codigo}").json


def comando(cliente, codigo, acao, esperado=200):
    resposta = cliente.post(f"/api/maquinas/{codigo}/{acao}")
    assert resposta.status_code == esperado, resposta.json


def configurar(cliente, codigo, semente, parametros):
    assert (
        cliente.patch("/api/configuracoes", json={"semente": semente}).status_code
        == 200
    )
    resposta = cliente.patch(f"/api/maquinas/{codigo}", json=parametros)
    assert resposta.status_code == 200, resposta.json


def avancar(cliente, *maquinas):
    versoes = {
        m["codigo"]: {chave: m["execucao"][chave] for chave in ("id", "versao")}
        for m in maquinas
    }
    resposta = cliente.post("/api/operacao/avancar", json={"versoes": versoes})
    assert resposta.status_code == 200, resposta.json
    return resposta.json["gerados"]


def concluir(cliente, codigo):
    maquina = estado(cliente, codigo)
    while maquina["execucao"]["fase"] == "Em execução":
        assert avancar(cliente, maquina) == 1
        seguinte = estado(cliente, codigo)
        assert seguinte["ciclo"] == maquina["ciclo"] + 1
        maquina = seguinte
    return maquina


@pytest.mark.parametrize(
    "codigo,semente,config,ciclos,situacoes,motivo",
    CENARIOS,
    ids=[
        "torno-normal",
        "torno-sobrecarga",
        "torno-demonstracao",
        "fresadora-normal",
        "fresadora-termico",
        "fresadora-recuperacao",
        "prensa-normal",
        "prensa-sobrecarga",
        "prensa-interrupcao",
    ],
)
def test_cenario_industrial(
    tmp_path, codigo, semente, config, ciclos, situacoes, motivo
):
    cliente = cliente_em(tmp_path)
    url = f"/api/maquinas/{codigo}"
    inicial = estado(cliente, codigo)
    assert (inicial["estado_atual"], inicial["ciclo"], inicial["execucao"]["fase"]) == (
        "Parada",
        0,
        "Inativa",
    )

    demonstracao = config.get("demonstracao")
    if demonstracao:
        demo = cliente.post("/api/ocorrencias/demonstracao")
        assert demo.status_code == 201 and demo.json["ciclo"] == 12
        segundo = cliente_em(tmp_path / "repeticao")
        assert segundo.post("/api/ocorrencias/demonstracao").status_code == 201
        assert (
            estado(cliente, codigo)["historico"] == estado(segundo, codigo)["historico"]
        )
    else:
        configurar(cliente, codigo, semente, {**config, "ciclos": ciclos})
        comando(cliente, codigo, "iniciar")
        aberto = estado(cliente, codigo)
        assert aberto["execucao"]["fase"] == "Em execução" and aberto["ciclo"] == 0
        assert avancar(cliente, aberto) == 1
        primeiro = estado(cliente, codigo)
        assert (
            primeiro["estado_atual"]
            == {
                "Normal": "Operando",
                "Alerta": "Alerta",
                "Falha": "Falha",
            }[situacoes[0]]
        )
        if codigo == "M-03" and semente == 303:
            comando(cliente, codigo, "pausar")
            pausada = estado(cliente, codigo)
            assert pausada["execucao"]["fase"] == "Pausada"
            assert pausada["sensores"] == primeiro["sensores"]
            assert avancar(cliente, primeiro) == avancar(cliente, pausada) == 0
            comando(cliente, codigo, "retomar")
            assert avancar(cliente, primeiro) == 0
            assert avancar(cliente, estado(cliente, codigo)) == 1
            comando(cliente, codigo, "interromper")
            parcial = estado(cliente, codigo)
            assert parcial["execucao"]["fase"] == "Interrompida"
            assert parcial["ciclo"] == 2 and parcial["estado_atual"] == "Parada"
            assert [r["desgaste"] for r in parcial["historico"]] == [8, 16]
            cliente = cliente_em(tmp_path)
            assert estado(cliente, codigo) == parcial
            comando(cliente, codigo, "iniciar")

    final = concluir(cliente, codigo)
    fase = "Falhou" if situacoes[-1] == "Falha" else "Concluída"
    assert final["execucao"]["fase"] == fase
    assert final["estado_atual"] == ("Falha" if fase == "Falhou" else "Parada")
    assert final["sensores"]["rpm"] == 0
    assert final["execucao"]["semente"] == semente
    assert final["execucao"]["total"] == ciclos
    assert avancar(cliente, final) == 0
    historico = cliente.get(url + "/historico").json
    leituras = historico["historico"]
    assert [r["status"] for r in leituras] == list(situacoes)
    assert [r["ciclo"] for r in leituras] == list(range(1, len(situacoes) + 1))
    udis = [r["identificador"] for r in leituras]
    assert udis == list(range(10001, 10001 + len(situacoes)))
    rpm, torque = {"M-01": (1500, 40), "M-02": (1560, 44), "M-03": (1440, 37)}[codigo]
    torque = config.get("torque", torque)
    temperatura = config.get("temperatura_c", 36.85) + 273.15
    if config.get("modo") == "Sobrecarga":
        rpm, torque, temperatura = rpm * 1.1, torque * 1.45, temperatura + 8
    for r in leituras:
        ruido = Random(semente * 1000003 + int(codigo[-2:]) * 100003 + r["ciclo"])
        assert r["equipamento"] == codigo
        assert r["rpm"] == round(rpm + ruido.gauss(0, 12))
        assert r["torque"] == round(torque + ruido.gauss(0, 0.6), 2)
        assert r["temperatura_processo"] == round(temperatura + ruido.gauss(0, 0.18), 2)
        assert r["temperatura_c"] == pytest.approx(r["temperatura_processo"] - 273.15)
        assert r["temperatura_ar"] == pytest.approx(r["temperatura_processo"] - 10)
    incremento = (
        8
        if demonstracao or config.get("modo") == "Desgaste acelerado"
        else (3 if config.get("modo") == "Sobrecarga" else 2)
    )
    assert [r["desgaste"] for r in leituras] == [
        incremento * n for n in range(1, len(situacoes) + 1)
    ]
    estatisticas = cliente.get(url + "/estatisticas").json
    assert estatisticas["quantidade"] == len(situacoes)
    assert estatisticas["alertas"] == situacoes.count("Alerta")
    assert estatisticas["falhas"] == situacoes.count("Falha")
    for campo, medidas in estatisticas["medicoes"].items():
        assert medidas["media"] == pytest.approx(fmean(r[campo] for r in leituras))
    eventos = historico["eventos"]
    if motivo:
        diagnosticados = [e for e in eventos if e["ocorrencia"]]
        assert diagnosticados and all(
            m["campo"] == motivo for e in diagnosticados for m in e["motivos"]
        )
        for evento in diagnosticados:
            r = leituras[evento["ciclo"] - 1]
            assert (evento["estado"], evento["equipamento"]) == (r["status"], codigo)
            ocorrencia = cliente.get(
                "/api/ocorrencias",
                query_string={"origem": codigo, "ocorrencia": evento["ocorrencia"]},
            ).json
            assert ocorrencia["detecao"] == r
            campo = "temperatura_c" if motivo == "temperatura" else motivo
            assert evento["motivos"][0]["valor"] == pytest.approx(r[campo])
    else:
        assert not any(e["ocorrencia"] for e in eventos)
    if fase == "Concluída":
        assert eventos[0]["descricao"] == "Lote concluído"
    csv = cliente.get(url + "/csv").data.decode("utf-8-sig")
    assert [int(r["identificador"]) for r in DictReader(StringIO(csv))] == udis
    for udi in udis:
        resposta = cliente.get(
            "/api/registros/consulta", query_string={"udi": udi, "estrategia": "hash"}
        )
        assert resposta.json["registro"] == leituras[udi - udis[0]]
    cliente = cliente_em(tmp_path)
    assert estado(cliente, codigo) == final
    assert cliente.get(url + "/historico").json == historico

    if fase == "Falhou":
        comando(cliente, codigo, "iniciar", esperado=409)
    if codigo == "M-02" and semente == 203:
        comando(cliente, codigo, "reiniciar")
        assert estado(cliente, codigo)["estado_atual"] == "Parada"
        configurar(cliente, codigo, 203, {"temperatura_c": 36.85, "ciclos": 2})
        comando(cliente, codigo, "iniciar")
        recuperada = concluir(cliente, codigo)
        assert recuperada["execucao"]["fase"] == "Concluída"
        assert recuperada["historico"][:1] == leituras
        assert [r["identificador"] for r in recuperada["historico"]] == [
            10001,
            10002,
            10003,
        ]
        assert [r["status"] for r in recuperada["historico"]] == [
            "Falha",
            "Normal",
            "Normal",
        ]


def test_frota_isolada_reenvio_e_concorrencia(tmp_path):
    cliente = cliente_em(tmp_path)
    app = cliente.application
    codigos = ("M-01", "M-02", "M-03")
    configuracoes = [
        {"ciclos": 5, "rpm": 1400},
        {"ciclos": 5, "torque": 73},
        {"ciclos": 5, "modo": "Desgaste acelerado", "limites_locais": {"desgaste": 16}},
    ]
    for codigo, semente, config in zip(codigos, (71, 72, 73), configuracoes):
        configurar(cliente, codigo, semente, config)
        comando(cliente, codigo, "iniciar")
    primeira = tuple(estado(cliente, c) for c in codigos)
    assert [m["execucao"]["semente"] for m in primeira] == [71, 72, 73]
    with ThreadPoolExecutor(max_workers=2) as pool:
        envios = pool.map(lambda _: avancar(app.test_client(), *primeira), range(2))
        assert sorted(envios) == [0, 3]
    assert avancar(cliente, *primeira) == 0  # Reenvio após perda da resposta.
    comando(cliente, "M-01", "pausar")
    assert avancar(cliente, *(estado(cliente, c) for c in codigos)) == 2
    m1, m2, m3 = (estado(cliente, c) for c in codigos)
    assert [m["ciclo"] for m in (m1, m2, m3)] == [1, 2, 2]
    assert [m["execucao"]["fase"] for m in (m1, m2, m3)] == [
        "Pausada",
        "Em execução",
        "Falhou",
    ]
    assert m2["estado_atual"] == "Alerta" and m3["estado_atual"] == "Falha"
    comando(cliente, "M-01", "retomar")
    assert avancar(cliente, m1, m2, m3) == 1
    comando(cliente, "M-02", "interromper")
    assert concluir(cliente, "M-01")["execucao"]["fase"] == "Concluída"
    csv = cliente.get("/api/maquinas/todas/csv").data.decode("utf-8-sig")
    udis = [int(r["identificador"]) for r in DictReader(StringIO(csv))]
    assert len(udis) == len(set(udis)) == 10
    reaberto = cliente_em(tmp_path)
    assert [estado(reaberto, c)["estatisticas"]["quantidade"] for c in codigos] == [
        5,
        3,
        2,
    ]
    for codigo, alerta in zip(codigos, (0, 3, 0)):
        assert estado(reaberto, codigo)["estatisticas"]["alertas"] == alerta
        ocorrencias = reaberto.get(
            "/api/ocorrencias", query_string={"origem": codigo}
        ).json
        assert all(o["equipamento"] == codigo for o in ocorrencias["ocorrencias"])


def test_ocorrencia_recorte_experimento_e_exportacao(tmp_path):
    cliente = cliente_em(tmp_path)
    codigo = "M-01"
    configurar(cliente, codigo, 101, {"ciclos": 16})
    comando(cliente, codigo, "iniciar")
    concluir(cliente, codigo)
    demo = cliente.post("/api/ocorrencias/demonstracao")
    assert demo.status_code == 201 and demo.json["ciclo"] == 28
    udi = int(demo.json["udi"])
    selecao = {"origem": codigo, "ocorrencia": demo.json["ocorrencia"]}
    ocorrencia = cliente.get("/api/ocorrencias", query_string=selecao).json
    assert ocorrencia["quantidade"] == 25
    assert ocorrencia["selecao"]["inicio"] == 4 and ocorrencia["selecao"]["fim"] == 28
    assert ocorrencia["ocorrencia"] in ocorrencia["ocorrencias"]
    assert ocorrencia["detecao"] == estado(cliente, codigo)["historico"][-1]

    selecao = {**selecao, "inicio": 20, "fim": 28, "fonte": "Simulação"}
    recorte = cliente.get("/api/ocorrencias", query_string=selecao).json
    assert recorte["quantidade"] == recorte["resumo"]["quantidade"] == 9
    assert recorte["resumo"]["medicoes"]["desgaste"]["media"] == 64
    csv = cliente.get("/api/ocorrencias/csv", query_string=selecao)
    evidencias = list(DictReader(StringIO(csv.data.decode("utf-8-sig"))))
    assert [int(r["ciclo"]) for r in evidencias] == list(range(20, 29))
    assert int(evidencias[-1]["identificador"]) == udi
    originais = (tmp_path / "simulacoes.csv").read_bytes()

    caminho = "/api/investigacao/operacoes"
    for metodo in ("insercao", "intercalacao", "heap"):
        ordem = cliente.post(
            caminho,
            json={
                "selecao": selecao,
                "operacao": "ordenacao",
                "estrategia": metodo,
                "atributo": "torque",
            },
        ).json
        esperado = sorted(
            recorte["registros"], key=lambda r: (r["torque"], r["identificador"])
        )
        assert ordem["equivalentes"] and ordem["menores"] == esperado
        assert ordem["metricas"][0]["tempo_ns"] > 0
        assert ordem["metricas"][0]["movimentacoes"] > 0
    for alvo, esperado in ((udi, recorte["detecao"]), (0, None)):
        busca = cliente.post(
            caminho,
            json={
                "selecao": selecao,
                "operacao": "busca",
                "udi": alvo,
            },
        ).json
        assert busca["equivalentes"] and busca["registro"] == esperado
        assert len(busca["metricas"]) == 4
    hash_demo = cliente.post(
        caminho,
        json={
            "selecao": selecao,
            "operacao": "hash",
            "udi": udi,
            "capacidade": 1,
        },
    ).json
    assert hash_demo["equivalentes"] and hash_demo["diagnostico"]["colisoes"] >= 8
    assert hash_demo["consulta_apos_remocao"] is None
    assert (tmp_path / "simulacoes.csv").read_bytes() == originais
    assert cliente.get("/api/ocorrencias/csv", query_string=selecao).data == csv.data

    experimento = cliente.post(
        "/api/experimentos",
        json={
            "aba": "hash",
            "selecao": selecao,
            "tamanhos": [2, 5, 9],
        },
    )
    assert experimento.status_code == 202
    limite = monotonic() + 20
    while monotonic() < limite:
        andamento = cliente.get("/api/experimentos/estado").json
        if andamento["estado"] != "Executando":
            break
        sleep(0.05)
    assert andamento["estado"] == "Concluído", andamento
    url = "/api/experimentos/hash"
    resultado = cliente.get(url, query_string=selecao).json
    assert resultado["origem"]["registros_disponiveis"] == 9
    assert resultado["origem"]["recorte_fonte"] == "Simulação"
    assinatura = sha256(csv.data.removeprefix(b"\xef\xbb\xbf")).hexdigest()
    assert resultado["origem"]["conteudo_sha256"] == assinatura
    assert not resultado["recorte_alterado"]
    exportado = cliente.get(url + "/csv", query_string=selecao)
    assert len(list(DictReader(StringIO(exportado.data.decode("utf-8-sig"))))) == 45
    assert assinatura.encode() in exportado.data
    assert (tmp_path / "simulacoes.csv").read_bytes() == originais

    assert (
        cliente.patch(f"/api/registros/{udi}", json={"torque": 24}).status_code == 200
    )
    alterado = cliente.get(url, query_string=selecao).json
    assert (
        alterado["recorte_alterado"]
        and alterado["origem"]["conteudo_sha256"] == assinatura
    )
    assert cliente.get(url + "/csv", query_string=selecao).data == exportado.data
    assert (tmp_path / "simulacoes.csv").read_bytes() == originais
