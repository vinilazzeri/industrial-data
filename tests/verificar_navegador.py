"""Validação opcional no Edge: python -m tests.verificar_navegador PASTA_NOVA."""

import argparse
import logging
import re
from contextlib import contextmanager
from csv import DictReader
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import make_server

from core.web import criar_app
from tests.teste_validacao_final import CENARIOS


@contextmanager
def servidor(pasta):
    app = criar_app({"PASTA_INSTANCIA": pasta})
    servidor_http = make_server("127.0.0.1", 0, app, threaded=True)
    tarefa = Thread(target=servidor_http.serve_forever, daemon=True)
    tarefa.start()
    try:
        yield f"http://127.0.0.1:{servidor_http.port}"
    finally:
        servidor_http.shutdown()
        tarefa.join()
        servidor_http.server_close()


def linhas_download(pagina, botao, destino):
    with pagina.expect_download() as captura:
        botao.click()
    captura.value.save_as(destino)
    with destino.open(encoding="utf-8-sig", newline="") as arquivo:
        return list(DictReader(arquivo))


def investigar(pagina, pasta):
    expect(pagina.locator("#detecao-ocorrencia")).to_contain_text("Falha")
    expect(pagina.locator("#detecao-ocorrencia")).to_contain_text("Desgaste")
    contexto = parse_qs(urlsplit(pagina.url).query)
    assert contexto["origem"] == ["M-01"]
    assert contexto["inicio"] == ["1"] and contexto["fim"] == ["12"]
    udi = contexto["udi"][0]
    evidencias = linhas_download(
        pagina,
        pagina.get_by_role("link", name="Exportar evidências"),
        pasta / "evidencias.csv",
    )
    assert len(evidencias) == 12 and evidencias[-1]["identificador"] == udi
    pagina.get_by_role("button", name="Identificar extremos").click()
    metricas = pagina.locator("[data-metricas-analise]")
    expect(metricas.locator("tbody tr")).to_have_count(3)
    pagina.get_by_role("button", name="Localizar uma medição").click()
    pagina.get_by_role("button", name="Consultar UDI").click()
    expect(metricas.locator("tbody tr")).to_have_count(4)
    expect(pagina.locator("[data-registro-analise]")).to_contain_text(udi)
    assert (
        len(
            linhas_download(
                pagina,
                pagina.get_by_role("button", name="Exportar métricas"),
                pasta / "metricas.csv",
            )
        )
        == 4
    )
    pagina.screenshot(path=pasta / "ocorrencia.png", full_page=True)

    pagina.get_by_role("link", name="Abrir em Registros").click()
    expect(pagina.locator("#tabela-registros tbody tr")).to_have_count(12)
    filtro = pagina.locator('#filtros-registros [name="fonte"]')
    filtro.select_option("Manual")
    expect(pagina.locator("#total-registros")).to_contain_text("0 registros")
    link = pagina.get_by_role("link", name="Comparar estratégias de busca")
    expect(link).to_have_attribute("href", re.compile("fonte=Manual"))
    filtro.select_option("")
    expect(pagina.locator("#tabela-registros tbody tr")).to_have_count(12)
    link.click()
    expect(pagina.locator("#contexto-lab")).to_contain_text(contexto["ocorrencia"][0])
    expect(pagina.locator("#contexto-lab")).to_contain_text("12 registros")
    pagina.get_by_role("button", name="Tabela Hash", exact=True).click()
    pagina.get_by_role("button", name="Demonstrar tabela hash").click()
    expect(metricas).to_contain_text("Remoção")
    pagina.get_by_role("button", name="Custo do sistema", exact=True).click()
    pagina.get_by_role("button", name="Comparar cargas").click()
    expect(metricas.locator("tbody tr")).to_have_count(8)

    pagina.get_by_role("button", name="Investigação experimental acadêmica").click()
    pagina.get_by_role("button", name="Tabela Hash", exact=True).click()
    pagina.get_by_label("Tamanhos").fill("2, 5, 10")
    pagina.get_by_role("button", name="Executar experimento").click()
    expect(pagina.locator("#resultado-lab-info")).to_contain_text("Histórico da M-01")
    expect(pagina.locator("#tabela-lab tbody tr")).to_have_count(3)
    pagina.get_by_label("Origem dos dados").select_option("controlado")
    expect(pagina.locator("#contexto-lab")).to_contain_text("10.000 registros")
    for nome in ("Ordenação", "Busca", "Tabela Hash", "Custo do sistema"):
        pagina.get_by_role("button", name=nome, exact=True).click()
        expect(pagina.locator("#interpretacao-lab")).to_contain_text("menor tempo")
        with pagina.expect_download() as grafico:
            pagina.get_by_role("button", name="Gráfico PNG").click()
        destino = pasta / f"grafico-{nome.lower().replace(' ', '-')}.png"
        grafico.value.save_as(destino)
        assert destino.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    pagina.screenshot(path=pasta / "laboratorio.png", full_page=True)
    pagina.get_by_role("link", name="Voltar à investigação").click()
    pagina.set_viewport_size({"width": 390, "height": 844})
    expect(pagina.locator("#detecao-ocorrencia")).to_contain_text(udi)
    assert pagina.evaluate("document.documentElement.scrollWidth === innerWidth")


def verificar_cenario(navegador, pasta, cenario):
    codigo, semente, config, ciclos, situacoes, _ = cenario
    with (
        servidor(pasta) as base,
        navegador.new_context(
            viewport={"width": 1440, "height": 1000}, accept_downloads=True
        ) as contexto,
    ):
        pagina = contexto.new_page()
        erros = []
        pagina.on("pageerror", lambda erro: erros.append(str(erro)))
        pagina.set_default_timeout(10000)
        url = f"{base}/api/maquinas/{codigo}"
        if config.get("demonstracao"):
            pagina.goto(base + "/ocorrencias")
            pagina.get_by_role("button", name="Executar cenário demonstrativo").click()
            investigar(pagina, pasta)
            pagina.set_viewport_size({"width": 1440, "height": 1000})
        else:
            assert pagina.request.patch(
                base + "/api/configuracoes", data={"semente": semente}
            ).ok
            assert pagina.request.patch(url, data={**config, "ciclos": ciclos}).ok
        pagina.goto(base + "/maquinas?maquina=" + codigo)
        cartao = pagina.locator(f'[data-unidade="{codigo}"]')
        estado = cartao.locator("[data-estado]")
        animacao = cartao.locator(".peca-movel").first
        if not config.get("demonstracao"):
            cartao.get_by_role("button", name="Iniciar", exact=True).click()
            if situacoes[0] != "Falha":
                expect(estado).to_have_text(
                    "Alerta" if situacoes[0] == "Alerta" else "Operando"
                )
                expect(animacao).to_have_css("animation-play-state", "running")
                if semente == 303:
                    cartao.get_by_role("button", name="Pausar", exact=True).click()
                    expect(estado).to_have_text("Pausada")
                    expect(animacao).to_have_css("animation-play-state", "paused")
                    cartao.get_by_role("button", name="Retomar", exact=True).click()
                    expect(animacao).to_have_css("animation-play-state", "running")
                    cartao.get_by_role("button", name="Interromper", exact=True).click()
                    expect(estado).to_have_text("Parada")
                    assert (
                        pagina.request.get(url).json()["execucao"]["fase"]
                        == "Interrompida"
                    )
                    cartao.get_by_role("button", name="Iniciar", exact=True).click()
        final = "Falha" if situacoes[-1] == "Falha" else "Parada"
        expect(estado).to_have_text(final)
        expect(animacao).to_have_css("animation-play-state", "paused")
        expect(pagina.locator("#historico-maquina tbody tr")).to_have_count(
            len(situacoes)
        )
        pagina.locator("#gerar-estatisticas").click()
        expect(pagina.get_by_text("Ciclos executados", exact=True)).to_be_visible()
        historico = pagina.request.get(url + "/historico").json()["historico"]
        pontos = [{"x": r["ciclo"], "y": r["temperatura_c"]} for r in historico]
        pagina.locator("#historico-campo").select_option("temperatura_processo")
        pagina.wait_for_function(
            "pontos => JSON.stringify(Chart.getChart('grafico-maquina')?.data.datasets[0].data) === JSON.stringify(pontos)",
            arg=pontos,
        )
        if final == "Falha":
            expect(pagina.locator("#eventos-maquina")).to_contain_text("Falha")
        pagina.screenshot(path=pasta / "maquina.png", full_page=True)
        if codigo == "M-02" and semente == 203:
            cartao.get_by_role("button", name="Reiniciar", exact=True).click()
            expect(estado).to_have_text("Parada")
            assert pagina.request.patch(
                url, data={"temperatura_c": 36.85, "ciclos": 2}
            ).ok
            pagina.reload()
            cartao.get_by_role("button", name="Iniciar", exact=True).click()
            expect(pagina.locator("#historico-maquina tbody tr")).to_have_count(3)
            expect(estado).to_have_text("Parada")
        assert not erros, erros


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pasta", type=Path)
    argumentos = parser.parse_args()
    argumentos.pasta.mkdir(parents=True)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    with sync_playwright() as playwright:
        navegador = playwright.chromium.launch(channel="msedge")
        print(f"Microsoft Edge {navegador.version}", flush=True)
        for numero, cenario in enumerate(CENARIOS, 1):
            verificar_cenario(
                navegador, argumentos.pasta / f"cenario-{numero:02}", cenario
            )
            print(f"Cenário {numero}: navegador aprovado", flush=True)


if __name__ == "__main__":
    main()
