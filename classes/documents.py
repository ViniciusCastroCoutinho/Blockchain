"""
Funções puras de normalização e checagem de documentos (CRM, CPF, CNPJ).

Não consultam cadastro nenhum — só formato e dígito verificador. Quem cruza
isso com os cadastros locais é o PrescriptionContract (classes/contract.py).
"""
import random
import re

_SEPARATORS = re.compile(r"[\s.\-/]")


# ----------------------------------------------------------------------
# CRM
# ----------------------------------------------------------------------
def normalize_crm(crm) -> str:
    """
    CRM não tem dígito verificador público, então só padronizamos a escrita
    para que "12345/AM", "12345-am" e "12345 AM" virem a mesma chave: "12345AM".
    """
    value = _SEPARATORS.sub("", str(crm or "")).upper()
    if value.startswith("CRM"):
        value = value[3:]
    return value


def is_crm_format(crm) -> bool:
    """Formato mínimo: só letras/números e pelo menos um dígito."""
    value = normalize_crm(crm)
    return bool(value) and value.isalnum() and any(c.isdigit() for c in value)


# ----------------------------------------------------------------------
# CPF
# ----------------------------------------------------------------------
def normalize_cpf(cpf) -> str:
    """Remove pontos, traços e espaços: '529.982.247-25' -> '52998224725'."""
    return _SEPARATORS.sub("", str(cpf or ""))


def is_cpf_format(cpf) -> bool:
    return re.fullmatch(r"\d{11}", normalize_cpf(cpf)) is not None


def _cpf_digit(digits: str) -> int:
    # pesos decrescentes começando em len+1 (10..2 para o 1º DV, 11..2 para o 2º)
    total = sum(int(d) * w for d, w in zip(digits, range(len(digits) + 1, 1, -1)))
    return (total * 10) % 11 % 10


def is_cpf_checksum_valid(cpf) -> bool:
    """Algoritmo padrão dos dois dígitos verificadores do CPF."""
    value = normalize_cpf(cpf)
    if not is_cpf_format(value):
        return False
    if len(set(value)) == 1:  # 000.000.000-00, 111.111.111-11... passam no cálculo mas são inválidos
        return False
    return _cpf_digit(value[:9]) == int(value[9]) and _cpf_digit(value[:10]) == int(value[10])


def complete_cpf(base9: str) -> str:
    """Recebe os 9 primeiros dígitos e devolve o CPF com os DVs corretos."""
    first = _cpf_digit(base9)
    second = _cpf_digit(base9 + str(first))
    return f"{base9}{first}{second}"


def generate_cpf() -> str:
    while True:
        cpf = complete_cpf("".join(random.choice("0123456789") for _ in range(9)))
        if len(set(cpf)) > 1:
            return cpf


def format_cpf(cpf) -> str:
    v = normalize_cpf(cpf)
    return f"{v[:3]}.{v[3:6]}.{v[6:9]}-{v[9:]}" if len(v) == 11 else str(cpf)


# ----------------------------------------------------------------------
# CNPJ
# ----------------------------------------------------------------------
# Obs.: a partir de jul/2026 a Receita passou a emitir CNPJ alfanumérico
# (12 primeiros caracteres podem ser letras, os 2 DVs continuam numéricos).
# O cálculo é o mesmo módulo 11, usando (código ASCII - 48) como valor de
# cada caractere — para dígitos isso dá exatamente o próprio dígito, então
# CNPJs numéricos antigos continuam funcionando sem mudança.
_CNPJ_W1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
_CNPJ_W2 = [6] + _CNPJ_W1


def normalize_cnpj(cnpj) -> str:
    """Remove pontos, barra, traços e espaços: '11.222.333/0001-81' -> '11222333000181'."""
    return _SEPARATORS.sub("", str(cnpj or "")).upper()


def is_cnpj_format(cnpj) -> bool:
    return re.fullmatch(r"[0-9A-Z]{12}\d{2}", normalize_cnpj(cnpj)) is not None


def _cnpj_digit(chars: str, weights) -> int:
    total = sum((ord(c) - 48) * w for c, w in zip(chars, weights))
    remainder = total % 11
    return 0 if remainder < 2 else 11 - remainder


def is_cnpj_checksum_valid(cnpj) -> bool:
    """Algoritmo padrão (módulo 11) dos dois dígitos verificadores do CNPJ."""
    value = normalize_cnpj(cnpj)
    if not is_cnpj_format(value):
        return False
    if len(set(value)) == 1:
        return False
    return (
        _cnpj_digit(value[:12], _CNPJ_W1) == int(value[12])
        and _cnpj_digit(value[:13], _CNPJ_W2) == int(value[13])
    )


def complete_cnpj(base12: str) -> str:
    base12 = base12.upper()
    first = _cnpj_digit(base12, _CNPJ_W1)
    second = _cnpj_digit(base12 + str(first), _CNPJ_W2)
    return f"{base12}{first}{second}"


def generate_cnpj() -> str:
    # 8 dígitos de raiz + "0001" (matriz), como nos CNPJs reais
    return complete_cnpj("".join(random.choice("0123456789") for _ in range(8)) + "0001")


def format_cnpj(cnpj) -> str:
    v = normalize_cnpj(cnpj)
    return f"{v[:2]}.{v[2:5]}.{v[5:8]}/{v[8:12]}-{v[12:]}" if len(v) == 14 else str(cnpj)
