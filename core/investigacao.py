"""Seleção de evidências e execução operacional dos algoritmos acadêmicos."""

from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from threading import RLock
from time import perf_counter_ns
from typing import Callable, TypeVar

from .algoritmos import BUSCAS, ORDENS, BuscaHash, IndiceBusca, Metricas, chave_de
from .dominio import RegistroIndustrial, inteiro
from .estatisticas import resumir
from .experimentos import ColecaoCarga
from .repositorio import gravar_csv, medir_consulta
from .servicos import ServicoIndustrial
from .simulacao import EQUIPAMENTOS, EQUIPAMENTOS_NOME

ORIGENS = {
    **{codigo: (f"Histórico da {codigo}", "Simulado") for codigo in EQUIPAMENTOS},
    "frota": ("Históricos combinados", "Simulado"),
    "ai4i": ("Base AI4I 2020", "Original sintético"),
    "trabalho": ("Coleção de trabalho", "Coleção editável"),
    "controlado": ("Conjunto experimental controlado", "Derivado da AI4I 2020"),
}

Resultado = TypeVar("Resultado")


def medir(acao: Callable[[], Resultado]) -> tuple[int, Resultado]:
    """Cronometra uma chamada sem instrumentação."""
    inicio = perf_counter_ns()
    resultado = acao()
    return perf_counter_ns() - inicio, resultado


def id_ocorrencia(equipamento: str, ciclo: int) -> str:
    """Gera a referência estável da observação persistida."""
    return f"OC-{equipamento}-{ciclo:06d}"


@dataclass(frozen=True, slots=True)
class SelecaoRegistros:
    """Identifica a procedência e os limites da investigação."""

    origem: str
    ocorrencia: str = ""
    inicio: int | None = None
    fim: int | None = None
    equipamento: str = ""
    fonte: str = ""
    status: str = ""

    @classmethod
    def criar(cls, valores: Mapping, padrao: str = "controlado") -> "SelecaoRegistros":
        """Valida os parâmetros de recorte vindos da interface."""
        origem = valores.get("origem") or padrao
        if not isinstance(origem, str) or origem not in ORIGENS:
            raise ValueError("Origem de dados inválida.")
        ocorrencia = valores.get("ocorrencia") or ""
        if not isinstance(ocorrencia, str) or len(ocorrencia) > 64:
            raise ValueError("Identificador de ocorrência inválido.")
        if ocorrencia and origem not in EQUIPAMENTOS:
            raise ValueError("Selecione a máquina da ocorrência.")
        inicio, fim = (
            inteiro(valores[chave], "Ciclo", 1)
            if valores.get(chave) not in ("", None)
            else None
            for chave in ("inicio", "fim")
        )
        if inicio is not None and fim is not None and inicio > fim:
            raise ValueError("O ciclo inicial deve ser menor ou igual ao final.")
        equipamento = valores.get("equipamento") or ""
        fonte = valores.get("fonte") or ""
        status = valores.get("status") or ""
        if equipamento not in ("", *EQUIPAMENTOS, "Sem equipamento"):
            raise ValueError("Equipamento inválido.")
        if fonte not in ("", "AI4I", "Simulação", "Manual", "Importação"):
            raise ValueError("Fonte inválida.")
        if status not in ("", "Normal", "Alerta", "Falha"):
            raise ValueError("Estado inválido.")
        if origem in ("ai4i", "controlado") and (
            inicio is not None or fim is not None or any((equipamento, fonte, status))
        ):
            raise ValueError(
                "Esta origem usa a base completa, sem filtros de operação."
            )
        return cls(origem, ocorrencia, inicio, fim, equipamento, fonte, status)


@dataclass(frozen=True, slots=True)
class RecorteIndustrial:
    """Reúne a entrada comum e as evidências registradas na máquina."""

    selecao: SelecaoRegistros
    registros: tuple[RegistroIndustrial, ...]
    ocorrencias: list[dict]
    ocorrencia: dict | None = None

    def metadados(self, *, experimental: bool = False) -> dict:
        """Informa procedência e distribuição de UDIs antes das transformações."""
        nome, natureza = ORIGENS[self.selecao.origem]
        chaves = sorted(r.identificador for r in self.registros)
        saltos = [b - a for a, b in zip(chaves, chaves[1:])]
        distribuicao = (
            "Sem chaves"
            if not chaves
            else "Chave única"
            if not saltos
            else "Regular e consecutiva"
            if min(saltos) == max(saltos) == 1
            else "Regular com lacunas"
            if min(saltos) == max(saltos)
            else "Irregular, com lacunas"
        )
        ciclos = [r.ciclo for r in self.registros if r.ciclo]
        return {
            "selecao": asdict(self.selecao),
            "origem_nome": nome,
            "natureza": natureza,
            "quantidade": len(chaves),
            "distribuicao_udi": distribuicao,
            "udi_minimo": str(chaves[0]) if chaves else None,
            "udi_maximo": str(chaves[-1]) if chaves else None,
            "ciclo_minimo": min(ciclos, default=None),
            "ciclo_maximo": max(ciclos, default=None),
            "natureza_entrada": "Amostras ou entradas derivadas"
            if experimental
            else natureza,
        }

    def assinatura(self) -> str:
        """Identifica o conteúdo exato que alimenta uma medição experimental."""
        return sha256(gravar_csv(self.registros).encode("utf-8")).hexdigest()

    def procedencia_experimental(self) -> dict:
        """Acrescenta a origem, os filtros e a assinatura do conjunto congelado."""
        metadados = self.metadados(experimental=True)
        return {
            "origem_entrada": metadados["origem_nome"],
            "natureza_entrada": metadados["natureza_entrada"],
            "distribuicao_udi_origem": metadados["distribuicao_udi"],
            "registros_disponiveis": metadados["quantidade"],
            "conteudo_sha256": self.assinatura(),
            **{f"recorte_{k}": v for k, v in metadados["selecao"].items()},
        }


class ServicoInvestigacao:
    """Resolve ocorrências, recortes e índices de consulta por seleção."""

    def __init__(
        self, industrial: ServicoIndustrial, original: tuple[RegistroIndustrial, ...]
    ) -> None:
        self._industrial = industrial
        self._original = original
        self._trava = RLock()
        self._indices: OrderedDict[
            SelecaoRegistros,
            tuple[tuple[RegistroIndustrial, ...], dict[str, IndiceBusca]],
        ] = OrderedDict()

    def selecionar(self, selecao: SelecaoRegistros) -> RecorteIndustrial:
        """Obtém uma entrada imutável sem mesclar as origens selecionadas."""
        if selecao.origem in ("ai4i", "controlado"):
            return RecorteIndustrial(selecao, self._original, [])
        trabalho, arquivo, eventos = self._industrial.evidencia()
        if selecao.origem == "trabalho":
            registros = tuple(r for r in trabalho if self._corresponde(r, selecao))
            return RecorteIndustrial(selecao, registros, [])
        historico = tuple(
            r for r in arquivo if selecao.origem in (r.equipamento, "frota")
        )
        vigentes = {r.identificador: r for r in trabalho if r.fonte == "Simulação"}
        ocorrencias = self._ocorrencias(historico, eventos, vigentes)
        ocorrencia = None
        if selecao.ocorrencia:
            ocorrencia = next(
                (o for o in ocorrencias if o["id"] == selecao.ocorrencia), None
            )
            if ocorrencia is None:
                raise LookupError("Ocorrência não encontrada para o equipamento.")
            ciclo = ocorrencia["ciclo"]
            selecao = replace(
                selecao,
                inicio=selecao.inicio
                if selecao.inicio is not None
                else max(1, ciclo - 24),
                fim=selecao.fim if selecao.fim is not None else ciclo,
            )
            if selecao.inicio > selecao.fim:
                raise ValueError("O ciclo inicial deve ser menor ou igual ao final.")
        registros = tuple(
            vigente
            for r in historico
            if (vigente := vigentes.get(r.identificador)) is not None
            and self._corresponde(vigente, selecao)
        )
        return RecorteIndustrial(selecao, registros, ocorrencias, ocorrencia)

    @staticmethod
    def _corresponde(r: RegistroIndustrial, selecao: SelecaoRegistros) -> bool:
        return (
            (selecao.inicio is None or r.ciclo >= selecao.inicio)
            and (selecao.fim is None or r.ciclo <= selecao.fim)
            and (
                not selecao.equipamento
                or (r.equipamento or "Sem equipamento") == selecao.equipamento
            )
            and (not selecao.fonte or r.fonte == selecao.fonte)
            and (not selecao.status or r.status == selecao.status)
        )

    @staticmethod
    def _ocorrencias(historico: tuple, eventos: tuple, vigentes: dict) -> list[dict]:
        contexto = {}
        for evento in eventos:
            if evento["estado"] in ("Alerta", "Falha") and (
                evento.get("motivos") or evento["descricao"] == "Mudança de estado"
            ):
                contexto.setdefault((evento["equipamento"], evento["ciclo"]), evento)
        ocorrencias = []
        for r in reversed(historico):
            if r.status not in ("Alerta", "Falha"):
                continue
            evento = contexto.get((r.equipamento, r.ciclo), {})
            ocorrencias.append(
                {
                    "id": id_ocorrencia(r.equipamento, r.ciclo),
                    "equipamento": r.equipamento,
                    "tipo": r.status,
                    "estado": r.status,
                    "ciclo": r.ciclo,
                    "udi": str(r.identificador),
                    "disponivel": r.identificador in vigentes,
                    "revisado": r.identificador in vigentes
                    and vigentes[r.identificador] != r,
                    "descricao": evento.get(
                        "descricao", f"{r.status} registrado na medição"
                    ),
                    "motivos": evento.get("motivos", []),
                }
            )
        return ocorrencias

    def resumir(self, recorte: RecorteIndustrial) -> dict:
        """Calcula a análise descritiva e localiza o registro detectado no recorte."""
        ocorrencia = recorte.ocorrencia
        udi = int(ocorrencia["udi"]) if ocorrencia else None
        registros = recorte.registros
        detecao = next((r for r in registros if r.identificador == udi), None)
        return {
            **recorte.metadados(),
            "ocorrencias": recorte.ocorrencias,
            "ocorrencia": ocorrencia,
            "resumo": resumir(registros),
            "detecao": detecao,
            "maquina": EQUIPAMENTOS_NOME.get(recorte.selecao.origem),
            "registros": registros[-100:],
            "serie": registros[-300:],
        }

    def ordenar(
        self, recorte: RecorteIndustrial, metodo: str, atributo: str, quantidade: int
    ) -> dict:
        """Mede estratégias intercambiáveis e compara a saída com o oráculo."""
        if metodo != "todas" and metodo not in ORDENS:
            raise ValueError("Estratégia de ordenação inválida.")
        chave = chave_de(atributo)
        esperado = sorted(recorte.registros, key=chave)
        metricas = []
        saida = []
        for nome in ORDENS if metodo == "todas" else (metodo,):
            estrategia = ORDENS[nome]
            contagem = Metricas()
            instrumentada = estrategia.ordenar(recorte.registros, chave, contagem)
            tempo_ns, saida = medir(
                lambda: estrategia.ordenar(recorte.registros, chave)
            )
            metricas.append(
                {
                    "estrategia": nome,
                    "tempo_ns": tempo_ns,
                    "comparacoes": contagem.comparacoes,
                    "movimentacoes": contagem.movimentacoes,
                    "espaco_auxiliar_posicoes": contagem.espaco_auxiliar,
                    "valido": saida == instrumentada == esperado,
                }
            )
        return {
            "metricas": metricas,
            "equivalentes": all(m["valido"] for m in metricas),
            "menores": saida[:quantidade],
            "maiores": saida[-quantidade:][::-1],
        }

    def consultar(self, recorte: RecorteIndustrial, metodo: str, udi: int) -> dict:
        """Consulta o mesmo UDI e mede o preparo por estratégia sobre a mesma entrada."""
        if metodo != "todas" and metodo not in BUSCAS:
            raise ValueError("Estratégia de consulta inválida.")
        esperado = next((r for r in recorte.registros if r.identificador == udi), None)
        metricas = []
        diagnostico = None
        for nome in BUSCAS if metodo == "todas" else (metodo,):
            preparo, indice, reutilizado = self._preparar(
                recorte, nome, frio=metodo == "todas"
            )
            medida = medir_consulta(indice, udi, nome, preparo, reutilizado)
            registro = medida.pop("registro")
            metricas.append({**medida, "valido": registro == esperado})
            if nome == "hash":
                diagnostico = indice.diagnostico()
        return {
            "registro": registro,
            "metricas": metricas,
            "diagnostico": diagnostico,
            "equivalentes": all(m["valido"] for m in metricas),
        }

    def _preparar(self, recorte: RecorteIndustrial, nome: str, *, frio: bool) -> tuple:
        if frio:
            tempo, indice = medir(lambda: BUSCAS[nome].preparar(recorte.registros))
            return tempo, indice, False
        with self._trava:
            selecao = recorte.selecao
            anterior = self._indices.get(selecao)
            if anterior is None or anterior[0] != recorte.registros:
                self._indices[selecao] = (recorte.registros, {})
            self._indices.move_to_end(selecao)
            if len(self._indices) > 12:
                self._indices.popitem(last=False)
            _, indices = self._indices[selecao]
            if nome in indices:
                return 0, indices[nome], True
            tempo, indice = medir(lambda: BUSCAS[nome].preparar(recorte.registros))
            indices[nome] = indice
            return tempo, indice, False

    def demonstrar_hash(
        self, recorte: RecorteIndustrial, udi: int, capacidade: int
    ) -> dict:
        """Mede inserção, correção e remoção em uma cópia privada da seleção."""
        preparo, indice = medir(
            lambda: BuscaHash(capacidade).preparar(recorte.registros)
        )
        existentes = indice.diagnostico()
        original = medir_consulta(indice, udi, "hash", preparo)
        novo_udi = (
            max((r.identificador for r in recorte.registros), default=udi) + capacidade
        )
        novo = RegistroIndustrial(novo_udi, produto="Amostra para demonstração da hash")
        revisto = replace(novo, torque=novo.torque + 1)
        etapas = []
        for nome, acao, esperado in (
            ("Inserção", lambda: indice.inserir(novo), novo),
            ("Correção", lambda: indice.inserir(revisto), revisto),
            ("Remoção", lambda: indice.remover(novo_udi), None),
        ):
            duracao, _ = medir(acao)
            verificado = medir_consulta(indice, novo_udi, "hash", 0, True)
            registro = verificado.pop("registro")
            etapas.append(
                {
                    **verificado,
                    "etapa": nome,
                    "atualizacao_ns": duracao,
                    "valido": registro == esperado,
                    "encontrado": registro is not None,
                }
            )
        return {
            "metricas": etapas,
            "diagnostico_inicial": existentes,
            "diagnostico": indice.diagnostico(),
            "registro": original["registro"],
            "consulta_apos_remocao": registro,
            "udi_teste": str(novo_udi),
            "consulta_original": {k: v for k, v in original.items() if k != "registro"},
            "equivalentes": all(m["valido"] for m in etapas),
        }

    def comparar_cargas(
        self, recorte: RecorteIndustrial, udi: int, consultas: int
    ) -> dict:
        """Compara consultas repetidas e manutenção incremental em dados isolados."""
        registros = list(recorte.registros)
        alvo = next((r for r in registros if r.identificador == udi), None)
        novo = RegistroIndustrial(
            max((r.identificador for r in registros), default=udi) + 1
        )
        revisto = replace(novo, torque=novo.torque + 1)
        estatico = [("buscar", udi)] * consultas + [("buscar", novo.identificador)] * 3
        dinamico = [("buscar", udi)] * consultas + [
            ("inserir", novo),
            ("buscar", novo.identificador),
            ("alterar", revisto),
            ("buscar", novo.identificador),
            ("remover", novo.identificador),
            ("buscar", novo.identificador),
        ]
        saida = []
        for nome in BUSCAS:
            for rotulo, roteiro, finais in (
                ("Estática", estatico, [None, None, None]),
                ("Dinâmica", dinamico, [novo, revisto, None]),
            ):
                preparo, indice = medir(lambda: ColecaoCarga(registros, nome))
                busca_ns = atualizacao_ns = 0
                resultados = []
                inicio = perf_counter_ns()
                for acao, valor in roteiro:
                    tempo, registro = medir(lambda: indice.aplicar(acao, valor))
                    if acao == "buscar":
                        busca_ns += tempo
                        resultados.append(registro)
                    else:
                        atualizacao_ns += tempo
                total = preparo + perf_counter_ns() - inicio
                reconstruir = (
                    medir(lambda: BUSCAS[nome].preparar(registros))[0]
                    if finais[0]
                    else None
                )
                saida.append(
                    {
                        "estrategia": nome,
                        "cenario": rotulo,
                        "preparo_ns": preparo,
                        "consulta_ns": busca_ns,
                        "atualizacao_ns": atualizacao_ns,
                        "tempo_ns": total,
                        "reconstrucao_ns": reconstruir,
                        "valido": resultados == [alvo] * consultas + finais,
                    }
                )
        return {"metricas": saida, "equivalentes": all(m["valido"] for m in saida)}
