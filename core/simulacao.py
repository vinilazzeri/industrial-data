"""Máquinas independentes com histórico simulado e reinicialização persistidos."""

import csv
import io
import json
from copy import deepcopy
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from random import Random
from threading import RLock
from uuid import uuid4

from .dominio import RegistroIndustrial, inteiro, real
from .estatisticas import resumir
from .repositorio import CAMPOS, escrever_atomicamente

EQUIPAMENTOS = ("M-01", "M-02", "M-03")
EQUIPAMENTOS_NOME = dict(
    zip(EQUIPAMENTOS, ("Torno CNC", "Fresadora", "Prensa industrial"))
)
MODOS = ("Normal", "Sobrecarga", "Desgaste acelerado", "Personalizado")
NOMES_MEDICOES = {
    "rpm": ("Rotação", "rpm"),
    "torque": ("Torque", "Nm"),
    "temperatura": ("Temperatura", "°C"),
    "desgaste": ("Desgaste", "min"),
}


class ConflitoOperacional(ValueError):
    """Ação incompatível com a condição atual da máquina."""


def celsius(kelvin: float) -> float:
    """Converte para a unidade de apresentação."""
    return round(kelvin - 273.15, 8)


def _receber_temperatura(campos: dict) -> dict:
    campos = campos.copy()
    if "temperatura_c" in campos:
        if "temperatura" in campos:
            raise ValueError("Informe a temperatura em uma única unidade.")
        valor = campos.pop("temperatura_c")
        campos["temperatura"] = (
            round(real(valor, "Temperatura", -73.15, 376.85) + 273.15, 8)
            if valor is not None
            else None
        )
    return campos


@dataclass(frozen=True)
class ParametrosMaquina:
    """Pontos de operação e tamanho do próximo lote."""

    rpm: int = 1500
    torque: float = 40
    temperatura: float = 310
    desgaste: int = 0
    ciclos: int = 24
    modo: str = "Normal"

    def __post_init__(self) -> None:
        for campo, limite in (("rpm", 10000), ("desgaste", 1000), ("ciclos", 500)):
            minimo = 0 if campo == "desgaste" else 1
            object.__setattr__(
                self, campo, inteiro(getattr(self, campo), campo, minimo, limite)
            )
        for campo, minimo, limite in (("torque", 0, 300), ("temperatura", 200, 650)):
            object.__setattr__(
                self, campo, real(getattr(self, campo), campo, minimo, limite)
            )
        if self.modo not in MODOS:
            raise ValueError("Modo operacional inválido.")


@dataclass(frozen=True)
class LimitesOperacionais:
    """Limiar de falha para as quatro variáveis controladas."""

    rpm: float = 2900
    torque: float = 80
    temperatura: float = 324
    desgaste: float = 250

    def __post_init__(self) -> None:
        for campo, minimo, maximo in (
            ("rpm", 1, 10000),
            ("torque", 1, 300),
            ("temperatura", 201, 650),
            ("desgaste", 1, 1000),
        ):
            object.__setattr__(
                self, campo, real(getattr(self, campo), campo, minimo, maximo)
            )

    def avaliar(self, valores: dict[str, float]) -> dict:
        """Classifica as medições e converte os limiares térmicos para Celsius."""
        alertas = {
            "rpm": 0.85 * self.rpm,
            "torque": 0.85 * self.torque,
            "temperatura": self.temperatura - 4,
            "desgaste": 0.8 * self.desgaste,
        }
        leitura = {}
        for campo, (nome, unidade) in NOMES_MEDICOES.items():
            limite = getattr(self, campo)
            valor = valores.get(campo)
            alerta = alertas[campo]
            nivel = "normal"
            if valor is not None and valor >= alerta:
                nivel = "falha" if valor >= limite else "alerta"
            conversao = celsius if campo == "temperatura" else float
            leitura[campo] = {
                "campo": campo,
                "nome": nome,
                "unidade": unidade,
                "nivel": nivel,
                "valor": conversao(valor) if valor is not None else None,
                "alerta": conversao(alerta),
                "limite": conversao(limite),
            }
        return leitura


@dataclass(frozen=True)
class ExecucaoMaquina:
    """Lote com progresso e configuração física congelada no início."""

    id: str = ""
    fase: str = "Inativa"
    versao: int = 0
    realizados: int = 0
    total: int = 0
    semente: int = 42
    limites: LimitesOperacionais = field(default_factory=LimitesOperacionais)

    @property
    def em_aberto(self) -> bool:
        """Indica que o lote ainda pode produzir novos ciclos."""
        return self.fase in ("Em execução", "Pausada")

    def transitar(self, fase: str, realizado: int = 0) -> "ExecucaoMaquina":
        """Atualiza a fase e invalida pedidos pendentes pela versão anterior."""
        return replace(
            self,
            fase=fase,
            versao=self.versao + 1,
            realizados=self.realizados + realizado,
        )


@dataclass(frozen=True)
class SimuladorMaquina:
    """Estado imutável de uma máquina, com avanço determinístico por ciclo."""

    codigo: str
    parametros: ParametrosMaquina
    estado: str = "Parada"
    ciclo: int = 0
    desgaste_atual: int = 0
    execucao: ExecucaoMaquina = field(default_factory=ExecucaoMaquina)
    limites_locais: dict[str, float] = field(default_factory=dict)
    indicadores: dict = field(default_factory=dict)
    motivos: tuple[dict, ...] = ()

    def limites_efetivos(self, padrao: LimitesOperacionais) -> LimitesOperacionais:
        """Sobrepõe os limites específicos do equipamento."""
        return replace(padrao, **self.limites_locais)

    def gerar(
        self,
        identificador: int,
        semente: int,
        limites: LimitesOperacionais,
        falha_forcada: bool,
    ) -> tuple["SimuladorMaquina", RegistroIndustrial]:
        """Aplica o modo escolhido, a variação reprodutível e os limites."""
        ciclo = self.ciclo + 1
        aleatorio = Random(semente * 1000003 + int(self.codigo[-2:]) * 100003 + ciclo)
        p = self.parametros
        sobrecarga = p.modo == "Sobrecarga"
        personalizado = p.modo == "Personalizado"
        rpm = max(1, round(p.rpm * (1.1 if sobrecarga else 1) + aleatorio.gauss(0, 12)))
        torque = max(
            0,
            round(p.torque * (1.45 if sobrecarga else 1) + aleatorio.gauss(0, 0.6), 2),
        )
        temperatura = round(
            p.temperatura + (8 if sobrecarga else 0) + aleatorio.gauss(0, 0.18), 2
        )
        desgaste = max(self.desgaste_atual, p.desgaste) + {
            "Desgaste acelerado": 8,
            "Sobrecarga": 3,
        }.get(p.modo, 1 if personalizado else 2)
        indicadores = limites.avaliar(
            {
                "rpm": rpm,
                "torque": torque,
                "temperatura": temperatura,
                "desgaste": desgaste,
            }
        )
        falhas = tuple(
            info for info in indicadores.values() if info["nivel"] == "falha"
        )
        falha = falha_forcada or bool(falhas)
        alerta = not falha and any(
            info["nivel"] == "alerta" for info in indicadores.values()
        )
        motivos = (
            falhas
            if falha
            else tuple(
                info for info in indicadores.values() if info["nivel"] == "alerta"
            )
        )
        if falha_forcada:
            motivos = (
                {"campo": "manual", "nome": "Falha acionada pelo operador"},
                *motivos,
            )
        estado = "Falha" if falha else ("Alerta" if alerta else "Operando")
        registro = RegistroIndustrial(
            identificador,
            produto=f"{self.codigo}-{ciclo:05d}",
            temperatura_ar=round(temperatura - 10, 2),
            temperatura_processo=temperatura,
            rpm=rpm,
            torque=torque,
            desgaste=desgaste,
            falha=int(falha),
            alerta=int(alerta),
            twf=int(indicadores["desgaste"]["nivel"] == "falha"),
            hdf=int(indicadores["temperatura"]["nivel"] == "falha"),
            osf=int(
                any(
                    indicadores[campo]["nivel"] == "falha"
                    for campo in ("rpm", "torque")
                )
            ),
            fonte="Simulação",
            equipamento=self.codigo,
            ciclo=ciclo,
        )
        return replace(
            self,
            estado=estado,
            ciclo=ciclo,
            desgaste_atual=desgaste,
            indicadores=indicadores,
            motivos=motivos,
        ), registro


class SimuladorIndustrial:
    """Gerencia estado e histórico em uma única transação CSV por ação."""

    def __init__(self, caminho: Path) -> None:
        self._caminho = caminho
        self._trava = RLock()
        self._historico: tuple[RegistroIndustrial, ...] = ()
        self._eventos: tuple[dict, ...] = ()
        self._maquinas = {
            codigo: SimuladorMaquina(codigo, ParametrosMaquina(rpm=rpm, torque=torque))
            for codigo, rpm, torque in zip(
                EQUIPAMENTOS, (1500, 1560, 1440), (40, 44, 37)
            )
        }
        if caminho.exists():
            historico, eventos = [], []
            with caminho.open(encoding="utf-8", newline="") as arquivo:
                for linha in csv.DictReader(arquivo):
                    if linha["categoria"] == "estado":
                        atributos = json.loads(linha["metadados"])
                        atributos["parametros"] = ParametrosMaquina(
                            **atributos["parametros"]
                        )
                        if "execucao" in atributos:
                            execucao = atributos["execucao"]
                            execucao["limites"] = LimitesOperacionais(
                                **execucao["limites"]
                            )
                            atributos["execucao"] = ExecucaoMaquina(**execucao)
                        atributos["motivos"] = tuple(atributos.get("motivos", ()))
                        maquina = SimuladorMaquina(**atributos)
                        self._maquinas[maquina.codigo] = maquina
                    elif linha["categoria"] == "evento":
                        eventos.append(json.loads(linha["metadados"]))
                    else:
                        historico.append(
                            RegistroIndustrial(**{c: linha[c] for c in CAMPOS})
                        )
            self._historico, self._eventos = tuple(historico), tuple(eventos)

    def _salvar(
        self,
        maquinas: dict[str, SimuladorMaquina],
        historico: tuple[RegistroIndustrial, ...],
        eventos: tuple[dict, ...],
    ) -> None:
        arquivo = io.StringIO(newline="")
        escritor = csv.DictWriter(
            arquivo, fieldnames=("categoria", "metadados", *CAMPOS)
        )
        escritor.writeheader()
        escritor.writerows(
            {
                "categoria": "estado",
                "metadados": json.dumps(asdict(maquina), ensure_ascii=False),
            }
            for maquina in maquinas.values()
        )
        escritor.writerows(
            {"categoria": "evento", "metadados": json.dumps(evento, ensure_ascii=False)}
            for evento in eventos
        )
        escritor.writerows(
            {"categoria": "ciclo", **asdict(registro)} for registro in historico
        )
        escrever_atomicamente(self._caminho, arquivo.getvalue())
        self._maquinas, self._historico, self._eventos = maquinas, historico, eventos

    def registros(self) -> tuple[RegistroIndustrial, ...]:
        """Devolve o histórico imutável na ordem de persistência."""
        with self._trava:
            return self._historico

    def eventos(self, limite: int | None = None) -> tuple[dict, ...]:
        """Devolve cópias dos eventos de alteração de estado."""
        with self._trava:
            return deepcopy(
                self._eventos if limite is None else self._eventos[-limite:]
            )

    def _maquina(self, codigo: str) -> SimuladorMaquina:
        if codigo not in self._maquinas:
            raise LookupError("Equipamento não encontrado.")
        return self._maquinas[codigo]

    def validar_lote(self, codigo: str, lote: str) -> None:
        """Recusa um controle originado em outro lote."""
        with self._trava:
            if self._maquina(codigo).execucao.id != lote:
                raise ConflitoOperacional(
                    "O lote mudou. Confira o estado atual da máquina."
                )

    def configurar(self, codigo: str, alteracoes: dict) -> None:
        """Aplica parâmetros à máquina selecionada em uma única gravação."""
        alteracoes = _receber_temperatura(alteracoes)
        locais = alteracoes.pop("limites_locais", {})
        if not isinstance(locais, dict):
            raise ValueError("Informe os limites locais por medição.")
        locais = _receber_temperatura(locais)
        if locais.keys() - NOMES_MEDICOES.keys():
            raise ValueError("Limite operacional desconhecido.")
        if any(
            campo not in {f.name for f in fields(ParametrosMaquina)}
            for campo in alteracoes
        ):
            raise ValueError("Parâmetro de máquina desconhecido.")
        with self._trava:
            maquina = self._maquina(codigo)
            if maquina.execucao.em_aberto:
                raise ConflitoOperacional(
                    "Interrompa ou conclua o lote antes de configurar."
                )
            parametros = replace(maquina.parametros, **alteracoes)
            limites = {**maquina.limites_locais, **locais}
            limites = {
                campo: valor for campo, valor in limites.items() if valor is not None
            }
            validados = LimitesOperacionais(**limites)
            nova = replace(
                maquina,
                parametros=parametros,
                limites_locais={campo: getattr(validados, campo) for campo in limites},
                desgaste_atual=parametros.desgaste
                if "desgaste" in alteracoes
                and parametros.desgaste != maquina.parametros.desgaste
                else maquina.desgaste_atual,
            )
            self._salvar(
                {**self._maquinas, codigo: nova}, self._historico, self._eventos
            )

    @staticmethod
    def _evento(maquina: SimuladorMaquina, descricao: str) -> dict:
        return {
            "equipamento": maquina.codigo,
            "ciclo": maquina.ciclo,
            "estado": maquina.estado,
            "fase": maquina.execucao.fase,
            "descricao": descricao,
            "motivos": list(maquina.motivos),
        }

    def iniciar(
        self,
        codigo: str | None,
        semente: int = 42,
        limites: LimitesOperacionais | None = None,
    ) -> int:
        """Abre um lote por equipamento disponível, sem gerar ciclos."""
        padrao = limites or LimitesOperacionais()
        with self._trava:
            codigos = (
                EQUIPAMENTOS if codigo is None else (self._maquina(codigo).codigo,)
            )
            maquinas, eventos = self._maquinas.copy(), []
            for selecionado in codigos:
                maquina = maquinas[selecionado]
                if maquina.execucao.em_aberto or maquina.estado == "Falha":
                    if codigo is not None:
                        raise ConflitoOperacional(
                            "A máquina já tem um lote aberto ou precisa ser reiniciada."
                        )
                    continue
                execucao = ExecucaoMaquina(
                    id=uuid4().hex,
                    fase="Em execução",
                    total=maquina.parametros.ciclos,
                    semente=semente,
                    limites=maquina.limites_efetivos(padrao),
                )
                nova = replace(
                    maquina,
                    estado="Operando",
                    execucao=execucao,
                    indicadores={},
                    motivos=(),
                )
                maquinas[selecionado] = nova
                eventos.append(self._evento(nova, "Máquina iniciada"))
            if eventos:
                self._salvar(maquinas, self._historico, (*self._eventos, *eventos))
            return len(eventos)

    def comandar(self, codigo: str, acao: str) -> None:
        """Pausa, retoma ou encerra um lote sem gravar medições adicionais."""
        transicoes = {
            "pausar": (("Em execução",), "Pausada", "Máquina pausada"),
            "retomar": (("Pausada",), "Em execução", "Máquina retomada"),
            "interromper": (
                ("Em execução", "Pausada"),
                "Interrompida",
                "Simulação interrompida",
            ),
        }
        origens, fase, mensagem = transicoes[acao]
        with self._trava:
            maquina = self._maquina(codigo)
            if maquina.execucao.fase not in origens:
                raise ConflitoOperacional("A fase atual do lote não permite esta ação.")
            interrompida = fase == "Interrompida"
            nova = replace(
                maquina,
                execucao=maquina.execucao.transitar(fase),
                estado="Parada" if interrompida else maquina.estado,
                motivos=() if interrompida else maquina.motivos,
            )
            self._salvar(
                {**self._maquinas, codigo: nova},
                self._historico,
                (*self._eventos, self._evento(nova, mensagem)),
            )

    def _proximo_udi(self, maior_udi: int) -> int:
        ultimo = self._historico[-1].identificador if self._historico else -1
        return max(maior_udi, ultimo) + 1

    def demonstrar(self, maior_udi: int) -> RegistroIndustrial:
        """Grava o cenário didático de desgaste acelerado da M-01."""
        with self._trava:
            original = self._maquina("M-01")
            if original.execucao.em_aberto:
                raise ConflitoOperacional(
                    "Interrompa o lote da M-01 antes da demonstração."
                )
            limites = LimitesOperacionais(desgaste=96)
            parametros = ParametrosMaquina(ciclos=12, modo="Desgaste acelerado")
            lote = ExecucaoMaquina(
                id=uuid4().hex,
                fase="Em execução",
                total=12,
                limites=limites,
                semente=42,
            )
            maquina = replace(
                original,
                parametros=parametros,
                estado="Operando",
                desgaste_atual=0,
                execucao=lote,
                indicadores={},
                motivos=(),
            )
            eventos = [self._evento(maquina, "Demonstração controlada iniciada")]
            novos = []
            proximo = self._proximo_udi(maior_udi)
            for deslocamento in range(parametros.ciclos):
                anterior = maquina.estado
                maquina, registro = maquina.gerar(
                    proximo + deslocamento, 42, limites, False
                )
                novos.append(registro)
                lote = lote.transitar("Falhou" if registro.falha else "Em execução", 1)
                maquina = replace(maquina, execucao=lote)
                if registro.falha:
                    eventos.append(
                        self._evento(maquina, "Falha demonstrativa por desgaste")
                    )
                    break
                if anterior != maquina.estado and registro.alerta:
                    eventos.append(
                        self._evento(maquina, "Alerta demonstrativo por desgaste")
                    )
            maquina = replace(maquina, parametros=original.parametros)
            self._salvar(
                {**self._maquinas, "M-01": maquina},
                (*self._historico, *novos),
                (*self._eventos, *eventos),
            )
            return novos[-1]

    def avancar(self, versoes: dict[str, dict], maior_udi: int) -> int:
        """Persiste um ciclo por lote ativo que corresponda ao token recebido."""
        with self._trava:
            maquinas, novos, eventos = self._maquinas.copy(), [], []
            proximo = self._proximo_udi(maior_udi)
            for codigo, token in versoes.items():
                anterior = self._maquina(codigo)
                execucao = anterior.execucao
                if execucao.fase != "Em execução" or (execucao.id, execucao.versao) != (
                    token["id"],
                    token["versao"],
                ):
                    continue
                nova, registro = anterior.gerar(
                    proximo, execucao.semente, execucao.limites, False
                )
                fase = (
                    "Falhou"
                    if registro.falha
                    else "Concluída"
                    if execucao.realizados + 1 >= execucao.total
                    else "Em execução"
                )
                nova = replace(nova, execucao=execucao.transitar(fase, 1))
                if registro.falha:
                    eventos.append(self._evento(nova, "Falha registrada"))
                elif nova.estado == "Alerta" and (
                    anterior.estado != nova.estado
                    or [m["campo"] for m in anterior.motivos]
                    != [m["campo"] for m in nova.motivos]
                ):
                    eventos.append(self._evento(nova, "Alerta detectado"))
                elif anterior.estado == "Alerta" and nova.estado == "Operando":
                    eventos.append(self._evento(nova, "Operação normal restabelecida"))
                if fase == "Concluída":
                    nova = replace(nova, estado="Parada", motivos=())
                    eventos.append(self._evento(nova, "Lote concluído"))
                maquinas[codigo] = nova
                novos.append(registro)
                proximo += 1
            if novos:
                self._salvar(
                    maquinas, (*self._historico, *novos), (*self._eventos, *eventos)
                )
            return len(novos)

    def executar(
        self,
        codigo: str | None,
        maior_udi: int,
        semente: int = 42,
        limites: LimitesOperacionais | None = None,
        forcar_falha: bool = False,
    ) -> int:
        """Executa um lote por equipamento e interrompe somente a unidade em falha."""
        limites = limites or LimitesOperacionais()
        with self._trava:
            codigos = (
                EQUIPAMENTOS if codigo is None else (self._maquina(codigo).codigo,)
            )
            maquinas = self._maquinas.copy()
            novos, eventos = [], []
            proximo = self._proximo_udi(maior_udi)
            for selecionado in codigos:
                maquina = maquinas[selecionado]
                if maquina.estado == "Falha":
                    continue
                if forcar_falha and maquina.execucao.fase == "Pausada":
                    raise ConflitoOperacional("Retome o lote para simular uma falha.")
                if maquina.execucao.em_aberto and not forcar_falha:
                    continue
                execucao = maquina.execucao
                limite_maquina = maquina.limites_efetivos(limites)
                semente_maquina = semente
                if execucao.em_aberto:
                    limite_maquina, semente_maquina = execucao.limites, execucao.semente
                for _ in range(1 if forcar_falha else maquina.parametros.ciclos):
                    anterior = maquina.estado
                    maquina, registro = maquina.gerar(
                        proximo, semente_maquina, limite_maquina, forcar_falha
                    )
                    if registro.falha:
                        maquina = replace(
                            maquina,
                            execucao=execucao.transitar(
                                "Falhou", int(execucao.em_aberto)
                            ),
                        )
                    novos.append(registro)
                    proximo += 1
                    if maquina.estado != anterior:
                        eventos.append(
                            self._evento(
                                maquina,
                                "Falha provocada"
                                if forcar_falha
                                else "Mudança de estado",
                            )
                        )
                    if registro.falha:
                        break
                maquinas[selecionado] = maquina
            if novos:
                self._salvar(
                    maquinas, (*self._historico, *novos), (*self._eventos, *eventos)
                )
            return len(novos)

    def reiniciar(self, codigo: str) -> None:
        """Rearma a máquina e restaura o desgaste configurado sem apagar ciclos."""
        with self._trava:
            maquina = self._maquina(codigo)
            if maquina.execucao.em_aberto:
                raise ConflitoOperacional("Interrompa o lote antes de reiniciar.")
            nova = replace(
                maquina,
                estado="Parada",
                desgaste_atual=maquina.parametros.desgaste,
                execucao=ExecucaoMaquina(),
                indicadores={},
                motivos=(),
            )
            evento = self._evento(nova, "Máquina reiniciada")
            self._salvar(
                {**self._maquinas, codigo: nova},
                self._historico,
                (*self._eventos, evento),
            )

    def historico(
        self,
        codigo: str,
        limite: int,
        inicio: int | None = None,
        fim: int | None = None,
    ) -> dict:
        """Filtra os ciclos e eventos pelo intervalo inclusivo."""
        with self._trava:
            self._maquina(codigo)
            inferior, superior = inicio or 0, fim if fim is not None else float("inf")
            registros = [
                r
                for r in self._historico
                if r.equipamento == codigo and inferior <= r.ciclo <= superior
            ]
            if inicio is None and fim is None and len(registros) > limite:
                inferior = registros[-limite].ciclo
            eventos = [
                e
                for e in self._eventos
                if e["equipamento"] == codigo and inferior <= e["ciclo"] <= superior
            ]
            return {
                "historico": registros[-limite:],
                "total_intervalo": len(registros),
                "eventos": deepcopy(eventos[-limite:][::-1]),
            }

    def detalhar(
        self,
        codigo: str,
        limite: int = 100,
        padrao: LimitesOperacionais | None = None,
        *,
        completo: bool = True,
    ) -> dict:
        """Retorna estado, últimos ciclos e estatísticas calculadas no histórico completo."""
        with self._trava:
            maquina = self._maquina(codigo)
            historico = [r for r in self._historico if r.equipamento == codigo]
            ultima = historico[-1] if historico else None
            estatisticas = (
                resumir(historico)
                if completo
                else {
                    "quantidade": len(historico),
                    "alertas": sum(r.alerta for r in historico),
                    "falhas": sum(r.falha for r in historico),
                }
            )
            estatisticas["desgaste_acumulado"] = ultima.desgaste if ultima else None
            padrao = padrao or LimitesOperacionais()
            limites = (
                maquina.execucao.limites
                if maquina.execucao.em_aberto
                else maquina.limites_efetivos(padrao)
            )
            estado_atual = (
                maquina.estado
                if maquina.execucao.em_aberto or maquina.estado == "Falha"
                else "Parada"
            )
            indicadores, motivos, carga = self._diagnostico(
                maquina, limites, estado_atual
            )
            sensores = self._sensores(maquina, ultima, estado_atual)
            return {
                **asdict(maquina),
                "parametros": {
                    **asdict(maquina.parametros),
                    "temperatura_c": celsius(maquina.parametros.temperatura),
                },
                "estado_atual": estado_atual,
                "sensores": sensores,
                "indicadores": deepcopy(indicadores),
                "motivos": deepcopy(motivos),
                "carga_percentual": carga,
                "estatisticas": estatisticas,
                "historico": historico[-limite:],
                "ultima": ultima,
            }

    @staticmethod
    def _sensores(
        maquina: SimuladorMaquina,
        ultima: RegistroIndustrial | None,
        estado: str,
    ) -> dict:
        # Um lote recém-aberto aguarda a primeira leitura própria.
        if maquina.execucao.em_aberto and not maquina.execucao.realizados:
            ultima = None
        return {
            "rpm": ultima.rpm if ultima and estado in ("Operando", "Alerta") else 0,
            "torque": ultima.torque if ultima else None,
            "temperatura_c": celsius(ultima.temperatura_processo) if ultima else None,
            "desgaste": maquina.desgaste_atual,
        }

    @staticmethod
    def _diagnostico(
        maquina: SimuladorMaquina, limites: LimitesOperacionais, estado: str
    ) -> tuple:
        indicadores = maquina.indicadores if estado != "Parada" else {}
        motivos = maquina.motivos if estado != "Parada" else ()
        if estado == "Falha" and not motivos:
            motivos = (
                {"campo": "legado", "nome": "Falha registrada no histórico anterior"},
            )
        carga = None
        if indicadores:
            carga = max(
                100 * indicadores[campo]["valor"] / indicadores[campo]["limite"]
                for campo in ("rpm", "torque")
            )
        return indicadores or limites.avaliar({}), motivos, carga
