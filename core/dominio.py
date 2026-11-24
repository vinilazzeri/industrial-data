"""Entidade imutável e validação das medições industriais."""

from dataclasses import dataclass
from math import isfinite


def inteiro(
    valor: object, nome: str, minimo: int = 0, maximo: int | None = None
) -> int:
    """Aceita inteiros e suas representações decimais sem truncar valores."""
    if type(valor) is int:
        numero = valor
    elif (
        isinstance(valor, str) and valor.strip().isascii() and valor.strip().isdecimal()
    ):
        numero = int(valor)
    else:
        raise ValueError(f"{nome} deve ser um inteiro.")
    if numero < minimo or (maximo is not None and numero > maximo):
        faixa = (
            f"entre {minimo} e {maximo}"
            if maximo is not None
            else f"a partir de {minimo}"
        )
        raise ValueError(f"{nome} deve estar {faixa}.")
    return numero


def real(
    valor: object, nome: str, minimo: float = 0, maximo: float | None = None
) -> float:
    """Converte e valida medições finitas dentro da faixa."""
    try:
        if isinstance(valor, bool):
            raise ValueError
        numero = float(valor)
    except (TypeError, ValueError, OverflowError) as erro:
        raise ValueError(f"{nome} deve ser numérico.") from erro
    if (
        not isfinite(numero)
        or numero < minimo
        or (maximo is not None and numero > maximo)
    ):
        raise ValueError(f"{nome} está fora da faixa permitida.")
    return numero


@dataclass(frozen=True, slots=True)
class RegistroIndustrial:
    """Representa uma observação com UDI e procedência explícita."""

    identificador: int
    produto: str = ""
    tipo: str = "L"
    temperatura_ar: float = 300.0
    temperatura_processo: float = 310.0
    rpm: int = 1500
    torque: float = 40.0
    desgaste: int = 0
    falha: int = 0
    twf: int = 0
    hdf: int = 0
    pwf: int = 0
    osf: int = 0
    rnf: int = 0
    fonte: str = "Manual"
    equipamento: str = ""
    ciclo: int = 0
    alerta: int = 0

    def __post_init__(self) -> None:
        """Normaliza os tipos e valida as categorias de cada observação."""
        for campo in ("identificador", "rpm", "desgaste", "ciclo"):
            object.__setattr__(self, campo, inteiro(getattr(self, campo), campo))
        for campo in ("temperatura_ar", "temperatura_processo", "torque"):
            object.__setattr__(self, campo, real(getattr(self, campo), campo))
        for campo in ("falha", "twf", "hdf", "pwf", "osf", "rnf", "alerta"):
            object.__setattr__(self, campo, inteiro(getattr(self, campo), campo, 0, 1))
        if self.tipo not in ("L", "M", "H"):
            raise ValueError("O tipo do produto deve ser L, M ou H.")
        if self.fonte not in ("AI4I", "Manual", "Importação", "Simulação"):
            raise ValueError("Fonte inválida.")
        if self.equipamento not in ("", "M-01", "M-02", "M-03"):
            raise ValueError("Equipamento inválido.")
        if not isinstance(self.produto, str) or len(self.produto) > 100:
            raise ValueError("O produto deve ser um texto de até 100 caracteres.")
        if self.fonte == "Simulação" and (not self.equipamento or not self.ciclo):
            raise ValueError("Um registro de simulação exige equipamento e ciclo.")
        if self.fonte == "AI4I" and (self.equipamento or self.ciclo):
            raise ValueError("Os registros AI4I não possuem equipamento ou ciclo.")

    @property
    def status(self) -> str:
        """Deriva o estado, dando precedência à falha."""
        if self.falha:
            return "Falha"
        return "Alerta" if self.alerta else "Normal"
