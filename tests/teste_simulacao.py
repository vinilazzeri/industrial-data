from core.simulacao import SimuladorIndustrial


def test_maquinas_independentes(tmp_path):
    caminho = tmp_path / "simulacoes.csv"
    simulador = SimuladorIndustrial(caminho)
    simulador.configurar("M-01", {"rpm": 2222, "torque": 33, "ciclos": 4})
    simulador.executar("M-01", 0)
    primeira = simulador.detalhar("M-01")
    assert primeira["estatisticas"]["quantidade"] == 4
    assert primeira["estatisticas"]["medicoes"]["rpm"]["media"] > 2100
    assert simulador.detalhar("M-02")["estado"] == "Parada"
    simulador.executar("M-02", 4, forcar_falha=True)
    assert simulador.detalhar("M-02")["estado"] == "Falha"
    assert simulador.executar("M-02", 5) == 0
    simulador.reiniciar("M-02")
    segunda = simulador.detalhar("M-02")
    assert segunda["estado"] == "Parada"
    assert segunda["estatisticas"]["falhas"] == 1
    assert simulador.detalhar("M-01") == primeira
    assert SimuladorIndustrial(caminho).detalhar("M-02") == segunda


def test_desgaste_alerta_falha_e_estatisticas(tmp_path):
    from core.simulacao import LimitesOperacionais

    simulador = SimuladorIndustrial(tmp_path / "simulacoes.csv")
    simulador.configurar("M-03", {"modo": "Desgaste acelerado", "ciclos": 12})
    assert simulador.executar("M-03", 0, limites=LimitesOperacionais(desgaste=25)) == 4
    maquina = simulador.detalhar("M-03")
    assert [r.desgaste for r in maquina["historico"]] == [8, 16, 24, 32]
    assert maquina["estatisticas"]["alertas"] == 1
    assert maquina["estatisticas"]["falhas"] == 1
    assert maquina["estatisticas"]["medicoes"]["desgaste"]["media"] == 20
    assert maquina["estatisticas"]["medicoes"]["desgaste"]["mediana"] == 20
    assert [e["estado"] for e in simulador.eventos()] == ["Operando", "Alerta", "Falha"]
