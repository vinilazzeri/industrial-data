"""Fábrica Flask, páginas e endpoints JSON/CSV."""

import hashlib
import os
import platform
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from .dominio import RegistroIndustrial, inteiro
from .estatisticas import resumir
from .experimentos import ABAS, ConfiguracaoExperimento
from .investigacao import (
    ORIGENS,
    RecorteIndustrial,
    SelecaoRegistros,
    ServicoInvestigacao,
    id_ocorrencia,
)
from .projecao import ProjecaoTelemetria
from .repositorio import RepositorioRegistros, gravar_csv, ler_csv
from .servicos import Configuracoes, ServicoIndustrial
from .simulacao import (
    EQUIPAMENTOS,
    EQUIPAMENTOS_NOME,
    ConflitoOperacional,
    SimuladorIndustrial,
    celsius,
)
from .trabalhos import TrabalhosExperimentos, csv_metricas

PAGINAS = (
    ("painel", "/", "Visão Geral", "Centro de operações", "activity"),
    ("maquinas", "/maquinas", "Máquinas", "Controle de máquinas", "cpu"),
    (
        "ocorrencias",
        "/ocorrencias",
        "Análise de Ocorrências",
        "Análise de ocorrências",
        "search",
    ),
    ("registros", "/registros", "Registros", "Registros industriais", "database"),
    (
        "laboratorio",
        "/laboratorio",
        "Laboratório de Algoritmos",
        "Laboratório de algoritmos",
        "flask",
    ),
    ("relatorios", "/relatorios", "Relatórios", "Relatórios de operação", "chart"),
    ("dados", "/dados", "Dados e Configurações", "Dados e configurações", "settings"),
)
ABA_NOMES = {
    "ordenacao": "Ordenação",
    "busca": "Busca",
    "hash": "Tabela Hash",
    "sistema": "Custo do sistema",
}


def _objeto_json() -> dict:
    corpo = request.get_json()
    if not isinstance(corpo, dict):
        raise ValueError("Envie um objeto JSON.")
    return corpo


def _csv(conteudo: str, nome: str) -> Response:
    return Response(
        "\ufeff" + conteudo,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{nome}.csv"'},
    )


def _registro_json(registro: RegistroIndustrial | None) -> dict | None:
    if registro is None:
        return None
    dados = asdict(registro)
    if registro.identificador > 2**53 - 1:
        dados["identificador"] = str(registro.identificador)
    dados["status"] = registro.status
    if registro.fonte == "Simulação":
        dados["temperatura_c"] = celsius(registro.temperatura_processo)
    return dados


def _maquina_json(maquina: dict) -> dict:
    ultima = maquina["ultima"]
    return {
        **maquina,
        "ultima": _registro_json(maquina["ultima"]),
        "historico": [_registro_json(r) for r in maquina["historico"]],
        "ocorrencia_recente": id_ocorrencia(ultima.equipamento, ultima.ciclo)
        if ultima and ultima.status in ("Alerta", "Falha")
        else None,
    }


def _painel_json(painel: dict) -> dict:
    return {
        **painel,
        "maquinas": [_maquina_json(m) for m in painel["maquinas"]],
        "eventos": [_evento_json(e) for e in painel["eventos"]],
    }


def _evento_json(evento: dict) -> dict:
    diagnostico = (
        evento["ciclo"] > 0
        and evento["estado"] in ("Alerta", "Falha")
        and (evento.get("motivos") or evento["descricao"] == "Mudança de estado")
    )
    return {
        **evento,
        "ocorrencia": id_ocorrencia(evento["equipamento"], evento["ciclo"])
        if diagnostico
        else None,
    }


def _ultima_medicao(
    aba: str, trabalhos: TrabalhosExperimentos, referencia: TrabalhosExperimentos
) -> dict | None:
    return trabalhos.resultado(aba) or referencia.resultado(aba)


def criar_app(configuracao: dict | None = None) -> Flask:
    """Monta uma instância local isolável para testes."""
    raiz = Path(__file__).resolve().parent.parent
    app = Flask(
        __name__, template_folder=raiz / "templates", static_folder=raiz / "static"
    )
    app.config.from_mapping(
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,
        PASTA_INSTANCIA=Path(
            os.environ.get("INDUSTRIALDATA_INSTANCIA", raiz / "instancia")
        ),
        BASE_ORIGINAL=raiz / "data" / "ai4i2020.csv",
    )
    app.config.update(configuracao or {})
    pasta = Path(app.config["PASTA_INSTANCIA"])
    original = Path(app.config["BASE_ORIGINAL"])
    conteudo = original.read_bytes()
    base = tuple(ler_csv(conteudo.decode("utf-8-sig")))
    repositorio = RepositorioRegistros(pasta / "registros.csv", original)
    simulador = SimuladorIndustrial(pasta / "simulacoes.csv")
    configuracoes = Configuracoes(pasta / "configuracoes.json")
    servico = ServicoIndustrial(
        repositorio,
        simulador,
        configuracoes,
        ProjecaoTelemetria(pasta / "ajustes_simulacao.csv"),
    )
    trabalhos = TrabalhosExperimentos(pasta / "experimentos", base)
    referencia = TrabalhosExperimentos(raiz / "docs" / "resultados", base)
    investigacao = ServicoInvestigacao(servico, base)

    @app.errorhandler(ValueError)
    @app.errorhandler(LookupError)
    def erro_validacao(erro: Exception):
        codigo = 404 if isinstance(erro, LookupError) else 400
        return jsonify(erro=str(erro)), codigo

    @app.errorhandler(ConflitoOperacional)
    def erro_operacional(erro: ConflitoOperacional):
        return jsonify(erro=str(erro)), 409

    @app.errorhandler(HTTPException)
    def erro_http(erro: HTTPException):
        mensagens = {
            400: "Corpo da requisição inválido.",
            404: "Recurso não encontrado.",
            405: "Método não permitido.",
            413: "O arquivo excede 8 MB.",
            415: "Formato de conteúdo inválido. Envie JSON na requisição.",
        }
        return jsonify(
            erro=mensagens.get(erro.code, "Não foi possível atender à requisição.")
        ), erro.code

    def pagina(chave: str, titulo: str) -> str:
        return render_template(
            f"{chave}.html",
            paginas=PAGINAS,
            pagina=chave,
            titulo=titulo,
            equipamentos=EQUIPAMENTOS,
            equipamentos_nome=EQUIPAMENTOS_NOME,
            configuracoes=configuracoes.obter(),
            abas=ABA_NOMES,
            origens=ORIGENS,
        )

    def renderizar(chave: str, titulo: str):
        return lambda: pagina(chave, titulo)

    for chave, url, _, titulo, _ in PAGINAS:
        app.add_url_rule(url, chave, renderizar(chave, titulo))

    registrar_rotas_operacionais(app, servico, investigacao)
    registrar_rotas_investigacao(app, investigacao, servico)

    def contexto_experimento(recorte: RecorteIndustrial) -> str:
        selecao = recorte.selecao
        if selecao.origem == "controlado":
            return ""
        return hashlib.sha256(repr(selecao).encode("utf-8")).hexdigest()[:24]

    def medicao_selecionada(aba: str, *, comparar_recorte: bool = False) -> dict | None:
        recorte = investigacao.selecionar(SelecaoRegistros.criar(request.args))
        contexto = contexto_experimento(recorte)
        resultado = (
            trabalhos.resultado(aba, contexto)
            if contexto
            else _ultima_medicao(aba, trabalhos, referencia)
        )
        if resultado and comparar_recorte and contexto:
            procedencia = resultado.get("origem", {})
            resultado["recorte_alterado"] = (
                procedencia.get("conteudo_sha256") != recorte.assinatura()
            )
            resultado["quantidade_atual"] = len(recorte.registros)
        return resultado

    @app.route("/api/configuracoes", methods=["GET", "PATCH"])
    def configurar():
        if request.method == "PATCH":
            return jsonify(configuracoes.atualizar(_objeto_json()))
        return jsonify(configuracoes.obter())

    @app.get("/api/dados")
    def api_dados():
        return jsonify(
            quantidade=len(base),
            sha256=hashlib.sha256(conteudo).hexdigest(),
            tipos=Counter(r.tipo for r in base),
            trabalho=len(repositorio.listar()),
            simulacoes=len(simulador.registros()),
            python=platform.python_version(),
            ambiente=platform.platform(),
            original=original.name,
            resultados=sum(
                _ultima_medicao(aba, trabalhos, referencia) is not None for aba in ABAS
            ),
        )

    @app.get("/api/relatorios")
    def api_relatorios():
        painel = servico.painel()
        return jsonify(
            maquinas=[_maquina_json(m) for m in painel["maquinas"]],
            simulacao=resumir(simulador.registros()),
            ai4i=resumir(base),
            resultados={
                aba: medicao["resumo"]
                for aba in ABAS
                if (medicao := _ultima_medicao(aba, trabalhos, referencia))
            },
        )

    @app.post("/api/experimentos")
    def iniciar_experimento():
        valores = configuracoes.obter()
        corpo = _objeto_json()
        selecao = corpo.pop("selecao", {})
        if not isinstance(selecao, dict):
            raise ValueError("Seleção de experimento inválida.")
        recorte = investigacao.selecionar(SelecaoRegistros.criar(selecao))
        parametros = {
            "semente": valores["semente"],
            "repeticoes": valores["repeticoes"],
            **corpo,
        }
        cfg = ConfiguracaoExperimento.criar(parametros)
        try:
            return jsonify(
                trabalhos.iniciar(
                    cfg,
                    base=recorte.registros,
                    contexto=contexto_experimento(recorte),
                    origem=recorte.procedencia_experimental(),
                )
            ), 202
        except RuntimeError as erro:
            return jsonify(erro=str(erro)), 409

    @app.get("/api/experimentos/estado")
    def estado_experimento():
        return jsonify(trabalhos.estado())

    @app.get("/api/experimentos/<aba>")
    def resultado_experimento(aba: str):
        resultado = medicao_selecionada(aba, comparar_recorte=True)
        if resultado is None:
            return jsonify(None)
        return jsonify({k: v for k, v in resultado.items() if k != "brutos"})

    @app.get("/api/experimentos/<aba>/csv")
    def exportar_experimento(aba: str):
        resultado = medicao_selecionada(aba)
        tipo = request.args.get("tipo", "brutos")
        if tipo not in ("brutos", "resumo", "compensacao"):
            raise ValueError("Tipo de métricas inválido.")
        if not resultado or not resultado[tipo]:
            raise LookupError("Ainda não há métricas deste tipo.")
        return _csv(csv_metricas(resultado[tipo]), f"{aba}_{tipo}")

    return app


def registrar_rotas_investigacao(
    app: Flask,
    investigacao: ServicoInvestigacao,
    servico: ServicoIndustrial,
) -> None:
    """Publica recortes, operações e exportações do fluxo de investigação."""

    def recorte_ocorrencia() -> RecorteIndustrial:
        selecao = SelecaoRegistros.criar(request.args, "M-01")
        if selecao.origem not in EQUIPAMENTOS:
            raise ValueError("Selecione a máquina da ocorrência.")
        return investigacao.selecionar(selecao)

    @app.get("/api/ocorrencias")
    def listar_ocorrencias():
        recorte = recorte_ocorrencia()
        resultado = investigacao.resumir(recorte)
        for chave in ("serie", "registros"):
            resultado[chave] = [_registro_json(r) for r in resultado[chave]]
        resultado["detecao"] = _registro_json(resultado["detecao"])
        return jsonify(resultado)

    @app.post("/api/ocorrencias/demonstracao")
    def demonstrar_ocorrencia():
        registro = servico.demonstrar_ocorrencia()
        return jsonify(
            ocorrencia=id_ocorrencia(registro.equipamento, registro.ciclo),
            udi=str(registro.identificador),
            ciclo=registro.ciclo,
            equipamento=registro.equipamento,
        ), 201

    @app.get("/api/ocorrencias/csv")
    def exportar_evidencias():
        recorte = recorte_ocorrencia()
        sufixo = recorte.selecao.ocorrencia or recorte.selecao.origem
        return _csv(gravar_csv(recorte.registros), f"evidencias_{sufixo}")

    @app.get("/api/investigacao/origem")
    def caracterizar_origem():
        recorte = investigacao.selecionar(SelecaoRegistros.criar(request.args))
        return jsonify(recorte.metadados())

    @app.post("/api/investigacao/operacoes")
    def operar_recorte():
        corpo = _objeto_json()
        selecao = corpo.get("selecao", {})
        if not isinstance(selecao, dict):
            raise ValueError("Seleção de registros inválida.")
        recorte = investigacao.selecionar(SelecaoRegistros.criar(selecao))
        if recorte.selecao.origem == "controlado":
            raise ValueError("Use o conjunto controlado no modo acadêmico.")
        operacao = corpo.get("operacao")
        estrategia = corpo.get("estrategia", "todas")
        configuracao = {"operacao": operacao, "estrategia_solicitada": estrategia}
        if not isinstance(estrategia, str):
            raise ValueError("Estratégia inválida.")
        if operacao == "ordenacao":
            atributo = corpo.get("atributo", "temperatura_processo")
            quantidade = inteiro(corpo.get("quantidade", 10), "Quantidade", 1, 100)
            configuracao.update(atributo=atributo, quantidade_extremos=quantidade)
            resultado = investigacao.ordenar(recorte, estrategia, atributo, quantidade)
            for chave in ("menores", "maiores"):
                resultado[chave] = [_registro_json(r) for r in resultado[chave]]
        elif operacao in ("busca", "hash", "sistema"):
            udi = inteiro(corpo.get("udi"), "UDI")
            configuracao["udi_consultado"] = str(udi)
            if operacao == "busca":
                resultado = investigacao.consultar(recorte, estrategia, udi)
            elif operacao == "hash":
                capacidade = inteiro(
                    corpo.get("capacidade", 17), "Capacidade", 1, 100000
                )
                configuracao["capacidade"] = capacidade
                resultado = investigacao.demonstrar_hash(recorte, udi, capacidade)
                resultado["consulta_apos_remocao"] = _registro_json(
                    resultado["consulta_apos_remocao"]
                )
            else:
                consultas = inteiro(corpo.get("consultas", 100), "Consultas", 1, 1000)
                configuracao["consultas_repetidas"] = consultas
                resultado = investigacao.comparar_cargas(recorte, udi, consultas)
            if "registro" in resultado:
                resultado["registro"] = _registro_json(resultado["registro"])
        else:
            raise ValueError("Operação de investigação inválida.")
        return jsonify(
            {**recorte.metadados(), **resultado, "configuracao": configuracao}
        )


def registrar_rotas_operacionais(
    app: Flask,
    servico: ServicoIndustrial,
    investigacao: ServicoInvestigacao,
) -> None:
    """Expõe o painel, as máquinas e os registros editáveis."""

    def recorte_consultado() -> RecorteIndustrial | None:
        if not request.args.get("origem"):
            return None
        return investigacao.selecionar(SelecaoRegistros.criar(request.args))

    def registros_filtrados() -> list[RegistroIndustrial]:
        recorte = recorte_consultado()
        if recorte:
            filtros = {
                k: request.args[k] for k in ("ordem", "atributo") if k in request.args
            }
            return servico.filtrar(filtros, recorte.registros)
        return servico.filtrar(request.args)

    @app.get("/api/painel")
    def api_painel():
        return jsonify(
            _painel_json(servico.painel(completo=request.args.get("leve") != "1"))
        )

    @app.post("/api/operacao/avancar")
    def avancar_operacao():
        versoes = _objeto_json().get("versoes")
        if not isinstance(versoes, dict) or versoes.keys() - set(EQUIPAMENTOS):
            raise ValueError("Informe as versões dos lotes por equipamento.")
        for token in versoes.values():
            if (
                not isinstance(token, dict)
                or not isinstance(token.get("id"), str)
                or type(token.get("versao")) is not int
                or token["versao"] < 0
            ):
                raise ValueError("Versão de lote inválida.")
        resultado = servico.avancar(versoes)
        return jsonify(
            gerados=resultado["gerados"], painel=_painel_json(resultado["painel"])
        )

    @app.post("/api/maquinas/iniciar")
    def iniciar_todas():
        return jsonify(iniciadas=servico.iniciar())

    @app.post("/api/maquinas/executar")
    def executar_todas():
        return jsonify(gerados=servico.executar())

    @app.route("/api/maquinas/<codigo>", methods=["GET", "PATCH"])
    def maquina(codigo: str):
        if request.method == "PATCH":
            return jsonify(
                _maquina_json(servico.configurar_maquina(codigo, _objeto_json()))
            )
        return jsonify(_maquina_json(servico.detalhar(codigo)))

    @app.post("/api/maquinas/<codigo>/<acao>")
    def acao_maquina(codigo: str, acao: str):
        corpo = _objeto_json() if request.is_json and request.content_length else {}
        lote = corpo.get("lote")
        if "lote" in corpo and not isinstance(lote, str):
            raise ValueError("Identificador de lote inválido.")
        if acao == "iniciar":
            return jsonify(iniciadas=servico.iniciar(codigo, lote=lote))
        if acao in ("reiniciar", "pausar", "retomar", "interromper"):
            servico.comandar(codigo, acao, lote=lote)
            return jsonify(gerados=0)
        if acao not in ("executar", "falha"):
            raise LookupError("Ação não encontrada.")
        return jsonify(
            gerados=servico.executar(codigo, forcar_falha=acao == "falha", lote=lote)
        )

    @app.get("/api/maquinas/<codigo>/estatisticas")
    def estatisticas_maquina(codigo: str):
        return jsonify(servico.detalhar(codigo)["estatisticas"])

    @app.get("/api/maquinas/<codigo>/historico")
    def historico_maquina(codigo: str):
        limite = inteiro(request.args.get("limite", "100"), "Limite", 1, 1000)
        inicio = request.args.get("inicio")
        fim = request.args.get("fim")
        inicio = inteiro(inicio, "Ciclo inicial") if inicio else None
        fim = inteiro(fim, "Ciclo final") if fim else None
        if inicio is not None and fim is not None and inicio > fim:
            raise ValueError("O ciclo final deve ser maior ou igual ao inicial.")
        historico = servico.simulador.historico(codigo, limite, inicio, fim)
        historico["historico"] = [_registro_json(r) for r in historico["historico"]]
        historico["eventos"] = [_evento_json(e) for e in historico["eventos"]]
        return jsonify(historico)

    @app.get("/api/maquinas/<codigo>/csv")
    def exportar_maquina(codigo: str):
        if codigo not in (*EQUIPAMENTOS, "todas"):
            raise LookupError("Equipamento não encontrado.")
        registros = (
            r
            for r in servico.simulador.registros()
            if codigo == "todas" or r.equipamento == codigo
        )
        return _csv(gravar_csv(registros), f"simulacao_{codigo}")

    @app.get("/api/registros")
    def listar_registros():
        pagina = inteiro(request.args.get("pagina", "1"), "Página", 1)
        limite = inteiro(request.args.get("limite", "25"), "Tamanho da página", 1, 100)
        registros = registros_filtrados()
        inicio = (pagina - 1) * limite
        return jsonify(
            total=len(registros),
            pagina=pagina,
            limite=limite,
            registros=[_registro_json(r) for r in registros[inicio : inicio + limite]],
        )

    @app.post("/api/registros")
    def inserir_registro():
        valores = _objeto_json()
        if not valores.keys() <= RegistroIndustrial.__dataclass_fields__.keys() - {
            "fonte",
            "ciclo",
        }:
            raise ValueError("Há campos desconhecidos ou protegidos no cadastro.")
        if "identificador" not in valores:
            raise ValueError("Informe o UDI.")
        registro = RegistroIndustrial(**valores)
        servico.importar([registro])
        return jsonify(_registro_json(registro)), 201

    @app.route("/api/registros/<int:udi>", methods=["PATCH", "DELETE"])
    def modificar_registro(udi: int):
        if request.method == "PATCH":
            return jsonify(_registro_json(servico.atualizar(udi, _objeto_json())))
        servico.remover(udi)
        return "", 204

    @app.get("/api/registros/consulta")
    def consultar_registro():
        udi = inteiro(request.args.get("udi"), "UDI")
        estrategia = request.args.get("estrategia", "binaria")
        recorte = recorte_consultado()
        if recorte:
            if estrategia == "todas":
                raise ValueError("Use o laboratório para comparar estratégias.")
            dados = investigacao.consultar(recorte, estrategia, udi)
            resposta = {**dados["metricas"][0], "registro": dados["registro"]}
        else:
            resposta = servico.consultar(udi, estrategia)
        resposta["registro"] = _registro_json(resposta["registro"])
        return jsonify(resposta)

    @app.get("/api/registros/manutencao")
    def manutencao_registros():
        return jsonify(servico.manutencao())

    @app.post("/api/registros/importar")
    def importar_registros():
        arquivo = request.files.get("arquivo")
        if arquivo is None:
            raise ValueError("Selecione um arquivo CSV.")
        try:
            texto = arquivo.read().decode("utf-8-sig")
        except UnicodeError as erro:
            raise ValueError("Salve o CSV em UTF-8 e tente novamente.") from erro
        registros = ler_csv(texto, "Importação")
        return jsonify(importados=servico.importar(registros)), 201

    @app.get("/api/registros/csv")
    def exportar_registros():
        return _csv(gravar_csv(registros_filtrados()), "registros")
