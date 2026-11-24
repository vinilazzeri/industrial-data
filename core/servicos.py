"""Serviços de consulta, simulação e configuração da aplicação."""

import json
from dataclasses import asdict
from pathlib import Path
from threading import RLock
from time import perf_counter_ns

from .algoritmos import BUSCAS, ORDENS, chave_de
from .dominio import RegistroIndustrial, inteiro
from .projecao import ProjecaoTelemetria
from .repositorio import RepositorioRegistros, escrever_atomicamente, medir_consulta
from .simulacao import EQUIPAMENTOS, LimitesOperacionais, SimuladorIndustrial


class Configuracoes:
    """Configurações validadas e persistidas no diretório da instância."""

    def __init__(self, caminho: Path) -> None:
        self._caminho = caminho
        self._trava = RLock()
        self._valores = {
            "semente": 42,
            "repeticoes": 5,
            "limites": asdict(LimitesOperacionais()),
        }
        if caminho.exists():
            self._valores = self._validar(
                json.loads(caminho.read_text(encoding="utf-8"))
            )

    def _validar(self, alteracoes: dict) -> dict:
        if set(alteracoes) - self._valores.keys():
            raise ValueError("Configuração desconhecida.")
        limites = alteracoes.get("limites", {})
        if (
            not isinstance(limites, dict)
            or set(limites) - self._valores["limites"].keys()
        ):
            raise ValueError("Limites operacionais inválidos.")
        return {
            "semente": inteiro(
                alteracoes.get("semente", self._valores["semente"]),
                "Semente",
                0,
                2**32 - 1,
            ),
            "repeticoes": inteiro(
                alteracoes.get("repeticoes", self._valores["repeticoes"]),
                "Repetições",
                5,
                15,
            ),
            "limites": asdict(
                LimitesOperacionais(**{**self._valores["limites"], **limites})
            ),
        }

    def obter(self) -> dict:
        """Devolve uma cópia independente da configuração vigente."""
        with self._trava:
            return {**self._valores, "limites": self._valores["limites"].copy()}

    def atualizar(self, alteracoes: dict) -> dict:
        """Valida e persiste todas as alterações em uma única transação."""
        with self._trava:
            valores = self._validar(alteracoes)
            escrever_atomicamente(self._caminho, json.dumps(valores, indent=2))
            self._valores = valores
            return self.obter()


class ServicoIndustrial:
    """Orquestra fontes e garante uma visão consistente e sem UDIs repetidos."""

    def __init__(
        self,
        repositorio: RepositorioRegistros,
        simulador: SimuladorIndustrial,
        configuracoes: Configuracoes,
        projecao: ProjecaoTelemetria,
    ) -> None:
        self.repositorio = repositorio
        self.simulador = simulador
        self.configuracoes = configuracoes
        self._projecao = projecao
        self._trava = RLock()
        self._trabalho = self._telemetria = None
        self._registros: tuple[RegistroIndustrial, ...] = ()
        self._indices = {}
        self._manutencao: dict | None = None

    def registros(self) -> tuple[RegistroIndustrial, ...]:
        """Consolida as duas fontes e invalida índices quando sua origem muda."""
        with self._trava:
            trabalho = self.repositorio.listar()
            telemetria = self.simulador.registros()
            if trabalho is not self._trabalho or telemetria is not self._telemetria:
                simulado = tuple(
                    registro
                    for original in telemetria
                    if (registro := self._projecao.visivel(original)) is not None
                )
                self._registros = (*trabalho, *simulado)
                self._trabalho, self._telemetria = trabalho, telemetria
                self._indices.clear()
            return self._registros

    def filtrar(
        self,
        filtros: dict,
        base: tuple[RegistroIndustrial, ...] | None = None,
    ) -> list[RegistroIndustrial]:
        """Aplica filtros e ordena pelas estratégias disponíveis."""
        equipamento = filtros.get("equipamento", "")
        fonte = filtros.get("fonte", "")
        status = filtros.get("status", "")
        ordem = filtros.get("ordem", "intercalacao")
        atributo = filtros.get("atributo", "identificador")
        if equipamento not in ("", "Sem equipamento", *EQUIPAMENTOS):
            raise ValueError("Filtro de equipamento inválido.")
        if fonte not in ("", "AI4I", "Manual", "Importação", "Simulação"):
            raise ValueError("Filtro de fonte inválido.")
        if status not in ("", "Normal", "Alerta", "Falha"):
            raise ValueError("Filtro de status inválido.")
        if ordem not in ORDENS:
            raise ValueError("Algoritmo de ordenação inválido.")
        registros = [
            r
            for r in (self.registros() if base is None else base)
            if (not equipamento or (r.equipamento or "Sem equipamento") == equipamento)
            and (not fonte or r.fonte == fonte)
            and (not status or r.status == status)
        ]
        return ORDENS[ordem].ordenar(registros, chave_de(atributo))

    def consultar(self, identificador: int, estrategia: str) -> dict:
        """Consulta toda a coleção e mede preparação e busca separadamente."""
        if estrategia not in BUSCAS:
            raise ValueError("Estratégia de busca inválida.")
        with self._trava:
            registros = self.registros()
            reutilizado = estrategia in self._indices
            preparo_ns = 0
            if not reutilizado:
                inicio = perf_counter_ns()
                self._indices[estrategia] = BUSCAS[estrategia].preparar(registros)
                preparo_ns = perf_counter_ns() - inicio
            return medir_consulta(
                self._indices[estrategia],
                identificador,
                estrategia,
                preparo_ns,
                reutilizado,
            )

    def importar(self, registros: list[RegistroIndustrial]) -> int:
        """Importa dados editáveis e impede sobreposição com a telemetria."""
        with self._trava:
            chaves_telemetria = {r.identificador for r in self.simulador.registros()}
            for registro in registros:
                if registro.identificador in chaves_telemetria:
                    raise ValueError(
                        f"UDI {registro.identificador} pertence à telemetria."
                    )
            antes = self.registros()
            inicio = perf_counter_ns()
            quantidade = self.repositorio.importar(registros)
            self._registrar_manutencao("Inserção ou importação", inicio, antes)
            return quantidade

    def _registrar_manutencao(self, operacao: str, inicio: int, antes: tuple) -> None:
        persistencia = perf_counter_ns() - inicio
        descartados = list(self._indices)
        inicio = perf_counter_ns()
        alterado = self.registros() is not antes
        self._manutencao = {
            "operacao": operacao,
            "persistencia_ns": persistencia,
            "sincronizacao_ns": perf_counter_ns() - inicio,
            "invalidos": descartados if alterado else [],
            "alterado": alterado,
        }

    def manutencao(self) -> dict | None:
        """Devolve a última medição de manutenção da coleção."""
        with self._trava:
            return self._manutencao

    def executar(
        self,
        codigo: str | None = None,
        forcar_falha: bool = False,
        *,
        lote: str | None = None,
    ) -> int:
        """Reserva UDIs acima da coleção e executa um lote com os limites atuais."""
        with self._trava:
            self._validar_lote(codigo, lote)
            maior = self._maior_udi_trabalho()
            configuracoes = self.configuracoes.obter()
            return self.simulador.executar(
                codigo,
                maior,
                configuracoes["semente"],
                LimitesOperacionais(**configuracoes["limites"]),
                forcar_falha,
            )

    def _maior_udi_trabalho(self) -> int:
        return max((r.identificador for r in self.repositorio.listar()), default=-1)

    def _validar_lote(self, codigo: str | None, lote: str | None) -> None:
        if codigo is not None and lote is not None:
            self.simulador.validar_lote(codigo, lote)

    def iniciar(self, codigo: str | None = None, *, lote: str | None = None) -> int:
        """Abre lotes com uma cópia da semente e dos limites globais."""
        with self._trava:
            self._validar_lote(codigo, lote)
            cfg = self.configuracoes.obter()
            return self.simulador.iniciar(
                codigo,
                cfg["semente"],
                LimitesOperacionais(**cfg["limites"]),
            )

    def avancar(self, versoes: dict[str, dict]) -> dict:
        """Reserva UDIs e devolve o painel após a gravação dos ciclos solicitados."""
        with self._trava:
            gerados = self.simulador.avancar(versoes, self._maior_udi_trabalho())
            return {"gerados": gerados, "painel": self.painel(completo=False)}

    def demonstrar_ocorrencia(self) -> RegistroIndustrial:
        """Registra o cenário didático reservando UDIs da coleção."""
        with self._trava:
            return self.simulador.demonstrar(self._maior_udi_trabalho())

    def evidencia(
        self,
    ) -> tuple[
        tuple[RegistroIndustrial, ...],
        tuple[RegistroIndustrial, ...],
        tuple[dict, ...],
    ]:
        """Fornece a coleção consultável e o contexto arquivado no mesmo snapshot."""
        with self._trava:
            return (
                self.registros(),
                self.simulador.registros(),
                self.simulador.eventos(),
            )

    def comandar(self, codigo: str, acao: str, *, lote: str | None = None) -> None:
        """Coordena comandos de controle com os avanços de ciclo."""
        with self._trava:
            self._validar_lote(codigo, lote)
            if acao == "reiniciar":
                self.simulador.reiniciar(codigo)
            else:
                self.simulador.comandar(codigo, acao)

    def configurar_maquina(self, codigo: str, alteracoes: dict) -> dict:
        """Atualiza parâmetros e devolve o mesmo snapshot da máquina."""
        with self._trava:
            self.simulador.configurar(codigo, alteracoes)
            return self.detalhar(codigo)

    def detalhar(self, codigo: str, *, completo: bool = True) -> dict:
        """Consulta uma máquina com os limites globais atuais."""
        with self._trava:
            return self.simulador.detalhar(
                codigo, padrao=self._limites_globais(), completo=completo
            )

    def _limites_globais(self) -> LimitesOperacionais:
        return LimitesOperacionais(**self.configuracoes.obter()["limites"])

    def _ciclo_arquivado(self, identificador: int) -> RegistroIndustrial | None:
        return next(
            (r for r in self.simulador.registros() if r.identificador == identificador),
            None,
        )

    def atualizar(self, identificador: int, alteracoes: dict) -> RegistroIndustrial:
        """Altera um registro editável sem modificar sua chave."""
        with self._trava:
            antes = self.registros()
            original = self._ciclo_arquivado(identificador)
            inicio = perf_counter_ns()
            if original is not None:
                anterior = self._projecao.visivel(original)
                registro = self._projecao.aplicar(original, alteracoes)
                if registro != anterior:
                    self._telemetria = None
            else:
                registro = self.repositorio.atualizar(identificador, alteracoes)
            self._registrar_manutencao("Correção", inicio, antes)
            return registro

    def remover(self, identificador: int) -> None:
        """Remove um registro da cópia de trabalho."""
        with self._trava:
            antes = self.registros()
            original = self._ciclo_arquivado(identificador)
            inicio = perf_counter_ns()
            if original is None:
                self.repositorio.remover(identificador)
            else:
                self._projecao.aplicar(original, None)
                self._telemetria = None
            self._registrar_manutencao("Remoção", inicio, antes)

    def painel(self, *, completo: bool = True) -> dict:
        """Calcula indicadores e séries das três máquinas sob o mesmo snapshot."""
        with self._trava:
            limites = self._limites_globais()
            maquinas = [
                self.simulador.detalhar(codigo, 60, limites, completo=completo)
                for codigo in EQUIPAMENTOS
            ]
            return {
                "maquinas": maquinas,
                "eventos": self.simulador.eventos(20)[::-1],
                "operando": sum(
                    m["execucao"]["fase"] == "Em execução" for m in maquinas
                ),
                "gerados": sum(m["estatisticas"]["quantidade"] for m in maquinas),
                "alertas": sum(m["estatisticas"]["alertas"] for m in maquinas),
                "falhas": sum(m["estatisticas"]["falhas"] for m in maquinas),
            }
