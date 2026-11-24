"""Delineamento reprodutível, medições isoladas e cargas controladas."""

import gc
import platform
import tracemalloc
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from functools import partial
from itertools import product
from math import ceil
from random import Random
from statistics import fmean, median, quantiles
from time import perf_counter_ns

from .algoritmos import (
    BUSCAS,
    ORDENS,
    BuscaHash,
    EstrategiaBusca,
    EstrategiaOrdenacao,
    Metricas,
    chave_de,
)
from .dominio import RegistroIndustrial, inteiro

ABAS = ("ordenacao", "busca", "hash", "sistema")
TAMANHOS = (500, 2000, 8000)
DISTRIBUICOES_ORDEM = ("Aleatória", "Ordenada", "Inversa", "Repetições")
DISTRIBUICOES_BUSCA = ("Regular", "Lacunas e concentração")
CARGAS = (0.25, 0.50, 0.75)


@dataclass(frozen=True)
class ConfiguracaoExperimento:
    """Define o tamanho e as condições de um conjunto de experimentos."""

    aba: str
    tamanhos: tuple[int, ...] = TAMANHOS
    repeticoes: int = 5
    consultas: int = 1000
    semente: int = 42
    atributo: str = "torque"
    operacoes: int = 100

    @classmethod
    def criar(cls, parametros: dict) -> "ConfiguracaoExperimento":
        """Valida o delineamento antes de ocupar o executor."""
        if set(parametros) - set(cls.__dataclass_fields__):
            raise ValueError("Configuração experimental desconhecida.")
        aba = parametros.get("aba")
        if aba not in ABAS:
            raise ValueError("Aba experimental inválida.")
        tamanhos = parametros.get("tamanhos", TAMANHOS)
        if not isinstance(tamanhos, (list, tuple)) or not 1 <= len(tamanhos) <= 3:
            raise ValueError("Informe de um a três tamanhos.")
        tamanhos = tuple(inteiro(n, "Tamanho", 2, 8000) for n in tamanhos)
        if len(set(tamanhos)) != len(tamanhos):
            raise ValueError("Os tamanhos devem ser distintos.")
        consultas = inteiro(parametros.get("consultas", 1000), "Consultas", 1000, 10000)
        if consultas % 2:
            raise ValueError(
                "Use um número par de consultas para dividir o lote em 50/50."
            )
        atributo = parametros.get("atributo", "torque")
        chave_de(atributo)
        if atributo == "identificador":
            raise ValueError("Escolha uma medição que possa ter valores repetidos.")
        return cls(
            aba,
            tamanhos,
            inteiro(parametros.get("repeticoes", 5), "Repetições", 5, 15),
            consultas,
            inteiro(parametros.get("semente", 42), "Semente", 0, 2**32 - 1),
            atributo,
            inteiro(parametros.get("operacoes", 100), "Mutações", 3, 1000),
        )


def _tempo(acao: Callable) -> tuple[int, object]:
    inicio = perf_counter_ns()
    resultado = acao()
    return perf_counter_ns() - inicio, resultado


def _pico(acao: Callable) -> int:
    gc.collect()
    tracemalloc.start()
    try:
        acao()
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def _base_ordenacao(
    base: Sequence, tamanho: int, distribuicao: str, atributo: str, semente: int
) -> list[RegistroIndustrial]:
    amostra = Random(semente).sample(base, tamanho)
    chave = chave_de(atributo)
    if distribuicao == "Repetições":
        amostra = [replace(r, **{atributo: i % 5 + 300}) for i, r in enumerate(amostra)]
    if distribuicao in ("Ordenada", "Inversa"):
        amostra = ORDENS["intercalacao"].ordenar(amostra, chave)
        if distribuicao == "Inversa":
            amostra.reverse()
    return amostra


def _lote(
    base: Sequence, tamanho: int, distribuicao: str, quantidade: int, semente: int
) -> tuple[list, list[int], list]:
    aleatorio = Random(semente)
    amostra = aleatorio.sample(base, tamanho)
    if distribuicao == "Regular":
        chaves = [i * 2 for i in range(tamanho)]
    else:
        chaves = [
            2 * i if i < tamanho // 2 else 2 * (tamanho + 17 * (i - tamanho // 2) ** 2)
            for i in range(tamanho)
        ]
    registros = [replace(r, identificador=chave) for r, chave in zip(amostra, chaves)]
    mapa = {r.identificador: r for r in registros}  # Oráculo fora das medições.
    alvos = [aleatorio.choice(chaves) for _ in range(quantidade // 2)]
    lacunas_pares = [chave + 2 for chave in chaves if chave + 2 not in mapa]
    for indice in range(quantidade // 2):
        if distribuicao != "Regular" and indice % 2:
            alvos.append(aleatorio.choice(lacunas_pares))
        else:
            alvos.append(aleatorio.choice(chaves) + 1)
    aleatorio.shuffle(alvos)
    aleatorio.shuffle(registros)
    return registros, alvos, [mapa.get(alvo) for alvo in alvos]


def _operacoes(
    registros: list, alvos: list[int], mutacoes: int, semente: int
) -> tuple[list, list]:
    aleatorio = Random(semente)
    mapa = {r.identificador: r for r in registros}
    proximo = max(mapa) + 2
    roteiro, esperado = [], []
    for numero, alvo in enumerate(alvos):
        while len(roteiro) - len(esperado) < (numero + 1) * mutacoes // len(alvos):
            ordem = (len(roteiro) - len(esperado)) % 3
            if ordem == 0:
                registro = replace(registros[0], identificador=proximo)
                proximo += 2
                mapa[registro.identificador] = registro
                roteiro.append(("inserir", registro))
            elif ordem == 1:
                chave = aleatorio.choice(tuple(mapa))
                registro = replace(mapa[chave], torque=mapa[chave].torque + 1)
                mapa[chave] = registro
                roteiro.append(("alterar", registro))
            else:
                chave = aleatorio.choice(tuple(mapa))
                del mapa[chave]
                roteiro.append(("remover", chave))
        roteiro.append(("buscar", alvo))
        esperado.append(mapa.get(alvo))
    return roteiro, esperado


class ColecaoCarga:
    """Aplica mutações com manutenção incremental da estrutura em memória."""

    def __init__(
        self, registros: list, estrategia: str, busca: EstrategiaBusca | None = None
    ) -> None:
        busca = BUSCAS[estrategia] if busca is None else busca
        self._ordenada = estrategia in ("binaria", "interpolacao")
        self._hash = estrategia == "hash"
        if self._hash:
            self._indice = busca.preparar(registros)
            self._registros = []
        else:
            self._registros = (
                ORDENS["intercalacao"].ordenar(registros, chave_de("identificador"))
                if self._ordenada
                else list(registros)
            )
            self._indice = type(busca)(self._registros)

    def _posicao(self, chave: int) -> int:
        if not self._ordenada:
            for posicao, registro in enumerate(self._registros):
                if registro.identificador == chave:
                    return posicao
            return len(self._registros)
        inicio, fim = 0, len(self._registros)
        while inicio < fim:
            meio = (inicio + fim) // 2
            if self._registros[meio].identificador < chave:
                inicio = meio + 1
            else:
                fim = meio
        return inicio

    def aplicar(
        self,
        acao: str,
        argumento: RegistroIndustrial | int,
        metricas: Metricas | None = None,
    ) -> RegistroIndustrial | None:
        """Executa uma ação do roteiro mantendo seu índice consistente."""
        if acao == "buscar":
            return self._indice.buscar(argumento, metricas)
        if self._hash:
            if acao == "remover":
                self._indice.remover(argumento)
            else:
                self._indice.inserir(argumento)
        elif acao == "inserir" and not self._ordenada:
            self._registros.append(argumento)
        else:
            chave = argumento if acao == "remover" else argumento.identificador
            posicao = self._posicao(chave)
            if acao == "remover":
                del self._registros[posicao]
            elif acao == "alterar":
                self._registros[posicao] = argumento
            else:
                self._registros.insert(posicao, argumento)
        return None


def _ordenar(
    registros: list,
    atributo: str,
    estrategia: EstrategiaOrdenacao | None,
    repeticoes: int,
) -> Iterator[dict]:
    chave = chave_de(atributo)
    metrica = Metricas()
    referencia = sorted(registros, key=chave)
    if estrategia is None:
        acao = partial(sorted, registros, key=chave)
        verificado = acao()
    else:
        acao = partial(estrategia.ordenar, registros, chave)
        verificado = estrategia.ordenar(registros, chave, metrica)
    if verificado != referencia:
        raise RuntimeError(f"Ordenação divergente ({type(estrategia).__name__}).")
    # A verificação também aquece a estratégia com a entrada integral.
    tempos = [_tempo(acao)[0] for _ in range(repeticoes)]
    for tempo in tempos:
        yield {
            "tempo_ns": tempo,
            "pico_bytes": _pico(acao),
            "comparacoes": metrica.comparacoes if estrategia is not None else None,
            "movimentacoes": metrica.movimentacoes if estrategia is not None else None,
            "espaco_auxiliar_posicoes": (
                metrica.espaco_auxiliar if estrategia is not None else None
            ),
        }


def _buscar(
    registros: list,
    alvos: list,
    esperado: list,
    metodo: str,
    estrategia: EstrategiaBusca,
    repeticoes: int,
    medir_prefixos: bool,
) -> Iterator[dict]:
    preparar = partial(estrategia.preparar, registros)
    indice = preparar()
    metrica = Metricas()
    passos = [[], []]
    resultado = []
    for alvo in alvos:
        anterior = metrica.comparacoes
        registro = indice.buscar(alvo, metrica)
        passos[registro is not None].append(metrica.comparacoes - anterior)
        resultado.append(registro)
    if resultado != esperado:
        raise RuntimeError(f"Busca divergente ({metodo}).")

    def consultar(indice_preparado, chaves: list) -> list:
        return [indice_preparado.buscar(alvo) for alvo in chaves]

    diagnosticar = getattr(indice, "diagnostico", None) if metodo == "hash" else None
    if not medir_prefixos and diagnosticar is None:
        raise ValueError("O estudo de fator de carga exige um índice com diagnóstico.")
    diagnostico = diagnosticar() if diagnosticar is not None else {}
    prefixos = (
        {q: alvos[:q] for q in sorted({1, 10, 50, 100, 250, 500, 1000, len(alvos)})}
        if medir_prefixos
        else {}
    )
    for chaves in prefixos.values():
        consultar(indice, chaves)
    tempos = []
    for _ in range(repeticoes):
        preparo, preparado = _tempo(preparar)
        consulta, _ = _tempo(partial(consultar, preparado, alvos))
        parciais = {
            f"total_q{q}_ns": preparo
            + (
                consulta
                if q == len(alvos)
                else _tempo(partial(consultar, preparado, chaves))[0]
            )
            for q, chaves in prefixos.items()
        }
        tempos.append((preparo, consulta, parciais))
    for preparo, consulta, parciais in tempos:
        yield {
            "tempo_ns": preparo + consulta,
            "preparo_ns": preparo,
            "consulta_ns": consulta,
            "consulta_unitaria_ns": consulta / len(alvos),
            "pico_bytes": _pico(lambda: consultar(preparar(), alvos)),
            "comparacoes": metrica.comparacoes,
            "passos_ausente": fmean(passos[0]),
            "passos_presente": fmean(passos[1]),
            **diagnostico,
            **parciais,
        }


def _carga(
    registros: list,
    roteiro: list,
    esperado: list,
    metodo: str,
    repeticoes: int,
    estrategia: EstrategiaBusca,
    colecao: Callable[[list, str, EstrategiaBusca], ColecaoCarga],
) -> Iterator[dict]:
    preparar = partial(colecao, registros, metodo, estrategia)

    def executar(metrica: Metricas | None = None) -> list:
        indice = preparar()
        encontrados = []
        for acao, argumento in roteiro:
            resultado = indice.aplicar(acao, argumento, metrica)
            if acao == "buscar":
                encontrados.append(resultado)
        return encontrados

    metrica = Metricas()
    if executar(metrica) != esperado:
        raise RuntimeError(f"Carga divergente ({metodo}).")
    registros_finais = {r.identificador: r for r in registros}
    mutacoes = len(roteiro) - len(esperado)
    for acao, argumento in roteiro:
        if acao == "remover":
            del registros_finais[argumento]
        elif acao in ("inserir", "alterar"):
            registros_finais[argumento.identificador] = argumento
    base_final = tuple(registros_finais.values())
    tempos = []
    for _ in range(repeticoes):
        preparo, indice = _tempo(preparar)
        consulta = atualizacao = 0
        inicio_total = perf_counter_ns()
        for acao, argumento in roteiro:
            inicio = perf_counter_ns()
            indice.aplicar(acao, argumento)
            duracao = perf_counter_ns() - inicio
            if acao == "buscar":
                consulta += duracao
            else:
                atualizacao += duracao
        total = perf_counter_ns() - inicio_total + preparo
        tempos.append((total, preparo, consulta, atualizacao))
    for total, preparo, consulta, atualizacao in tempos:
        yield {
            "tempo_ns": total,
            "preparo_ns": preparo,
            "consulta_ns": consulta,
            "atualizacao_ns": atualizacao,
            "reconstrucao_ns": _tempo(partial(estrategia.preparar, base_final))[0]
            if mutacoes
            else None,
            "consulta_unitaria_ns": consulta / len(esperado),
            "pico_bytes": _pico(executar),
            "comparacoes": metrica.comparacoes,
            "mutacoes_executadas": mutacoes,
        }


def _resumir(linhas: list[dict], contexto: dict) -> dict:
    resumo = {**contexto, "repeticoes": len(linhas)}
    for campo in (
        nome for nome in linhas[0] if nome not in contexto and nome != "repeticao"
    ):
        valores = [linha[campo] for linha in linhas if linha[campo] is not None]
        if valores:
            quartis = quantiles(valores, method="inclusive")
            resumo[f"{campo}_mediana"] = median(valores)
            resumo[f"{campo}_iiq"] = quartis[2] - quartis[0]
    return resumo


def _compensacao(resumos: list[dict], consultas: int) -> list[dict]:
    grupos = {}
    for linha in resumos:
        grupos.setdefault((linha["tamanho"], linha["distribuicao"]), {})[
            linha["algoritmo"]
        ] = linha
    pontos = []
    for (tamanho, distribuicao), metodos in grupos.items():
        referencia = metodos["sequencial"]
        for nome, linha in metodos.items():
            if nome == "sequencial":
                continue
            ganho = (
                referencia["consulta_unitaria_ns_mediana"]
                - linha["consulta_unitaria_ns_mediana"]
            )
            sobrecusto = linha["preparo_ns_mediana"] - referencia["preparo_ns_mediana"]
            ponto = None if ganho <= 0 else max(1, ceil(sobrecusto / ganho))
            pontos_testados = [
                q
                for q in sorted({1, 10, 50, 100, 250, 500, 1000, consultas})
                if linha[f"total_q{q}_ns_mediana"]
                <= referencia[f"total_q{q}_ns_mediana"]
            ]
            pontos.append(
                {
                    "tamanho": tamanho,
                    "distribuicao": distribuicao,
                    "algoritmo": nome,
                    "consultas_limite": consultas,
                    "estimativa_modelo": ponto,
                    "consultas_compensacao": pontos_testados[0]
                    if pontos_testados
                    else None,
                }
            )
    return pontos


class ExecutorExperimentos:
    """Executa estratégias sobre a mesma entrada por configuração."""

    def __init__(
        self,
        *,
        ordenacoes: Mapping[str, EstrategiaOrdenacao] | None = None,
        buscas: Mapping[str, EstrategiaBusca] | None = None,
        hash_por_capacidade: Callable[[int], BuscaHash] = BuscaHash,
        colecao: Callable[[list, str, EstrategiaBusca], ColecaoCarga] = ColecaoCarga,
    ) -> None:
        """Compõe as estratégias por papel no protocolo fixo de comparação.

        A coleção mutável padrão usa os contratos de armazenamento das buscas
        nativas. Forneça um adaptador de coleção para estruturas diferentes.
        """
        if (ordenacoes and ordenacoes.keys() - ORDENS.keys()) or (
            buscas and buscas.keys() - BUSCAS.keys()
        ):
            raise ValueError("Estratégia fora do protocolo experimental.")
        self._ordenacoes = {**ORDENS, **(ordenacoes or {})}
        self._buscas = {**BUSCAS, **(buscas or {})}
        self._hash_por_capacidade = hash_por_capacidade
        self._colecao = colecao

    def executar(
        self,
        cfg: ConfiguracaoExperimento,
        base: Sequence[RegistroIndustrial],
        progresso: Callable[[int, int], None] = lambda concluidos, total: None,
    ) -> dict:
        """Retorna as passagens cronometradas, seus resumos e pontos de compensação."""
        if max(cfg.tamanhos) > len(base):
            raise ValueError("A base experimental não tem registros suficientes.")
        brutos, resumos = [], []
        distribuicoes = {
            "ordenacao": DISTRIBUICOES_ORDEM,
            "busca": DISTRIBUICOES_BUSCA,
            "hash": ("Lacunas e concentração",),
            "sistema": ("Estática", "Dinâmica"),
        }[cfg.aba]
        metodos = (
            (*self._ordenacoes, "nativo")
            if cfg.aba == "ordenacao"
            else ("hash",)
            if cfg.aba == "hash"
            else tuple(self._buscas)
        )
        cargas = CARGAS if cfg.aba == "hash" else (None,)
        total = len(cfg.tamanhos) * len(distribuicoes) * len(metodos) * len(cargas)
        ambiente = {
            "python": platform.python_version(),
            "plataforma": platform.platform(),
            "implementacao_python": platform.python_implementation(),
            "processador": platform.processor() or platform.machine(),
        }
        progresso(0, total)
        for tamanho, distribuicao in product(cfg.tamanhos, distribuicoes):
            semente = cfg.semente + tamanho
            if cfg.aba == "ordenacao":
                registros = _base_ordenacao(
                    base, tamanho, distribuicao, cfg.atributo, semente
                )
            else:
                perfil = (
                    "Lacunas e concentração" if cfg.aba == "sistema" else distribuicao
                )
                registros, alvos, esperado = _lote(
                    base, tamanho, perfil, cfg.consultas, semente
                )
                if cfg.aba == "sistema":
                    mutacoes = cfg.operacoes if distribuicao == "Dinâmica" else 0
                    roteiro, esperado = _operacoes(registros, alvos, mutacoes, semente)
            for metodo, carga in product(metodos, cargas):
                contexto = {
                    "aba": cfg.aba,
                    "tamanho": tamanho,
                    "distribuicao": distribuicao,
                    "algoritmo": metodo,
                    "semente": semente,
                    "semente_base": cfg.semente,
                    "atributo": cfg.atributo
                    if cfg.aba == "ordenacao"
                    else "identificador",
                    "consultas": cfg.consultas if cfg.aba != "ordenacao" else 0,
                    "mutacoes_planejadas": cfg.operacoes
                    if distribuicao == "Dinâmica"
                    else 0,
                    "carga_alvo": carga,
                    "unidade_tempo": "ns",
                    "unidade_memoria": "bytes",
                    **ambiente,
                }
                if cfg.aba == "ordenacao":
                    medicoes = _ordenar(
                        registros,
                        cfg.atributo,
                        self._ordenacoes.get(metodo),
                        cfg.repeticoes,
                    )
                elif cfg.aba == "sistema":
                    medicoes = _carga(
                        registros,
                        roteiro,
                        esperado,
                        metodo,
                        cfg.repeticoes,
                        self._buscas[metodo],
                        self._colecao,
                    )
                else:
                    estrategia = (
                        self._buscas[metodo]
                        if carga is None
                        else self._hash_por_capacidade(ceil(len(registros) / carga))
                    )
                    medicoes = _buscar(
                        registros,
                        alvos,
                        esperado,
                        metodo,
                        estrategia,
                        cfg.repeticoes,
                        medir_prefixos=cfg.aba == "busca",
                    )
                linhas = [
                    {**contexto, "repeticao": i, **medicao}
                    for i, medicao in enumerate(medicoes, 1)
                ]
                brutos.extend(linhas)
                resumos.append(_resumir(linhas, contexto))
                progresso(len(resumos), total)
        return {
            "configuracao": asdict(cfg),
            "ambiente": ambiente,
            "brutos": brutos,
            "resumo": resumos,
            "compensacao": _compensacao(resumos, cfg.consultas)
            if cfg.aba == "busca"
            else [],
        }
