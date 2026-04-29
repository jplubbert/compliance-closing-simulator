"""Utilidades compartidas."""

import random

_MULTIPLICADORES_DV = (2, 3, 4, 5, 6, 7)


def calcular_dv(numero: int) -> str:
    """Dígito verificador chileno (módulo 11)."""
    suma = 0
    i = 0
    n = numero
    while n > 0:
        suma += (n % 10) * _MULTIPLICADORES_DV[i % len(_MULTIPLICADORES_DV)]
        n //= 10
        i += 1
    resto = 11 - (suma % 11)
    if resto == 11:
        return "0"
    if resto == 10:
        return "K"
    return str(resto)


def generar_rut_valido() -> str:
    """RUT con formato 8 dígitos + espacio + DV (10 caracteres totales)."""
    base = random.randint(0, 99_999_999)
    base_str = str(base).zfill(8)
    return f"{base_str} {calcular_dv(base)}"
