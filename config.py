"""Configuração local validada, sem chamadas de rede e sem segredos versionados."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from decimal import Decimal, InvalidOperation
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def carregar_ambiente() -> None:
    """Carrega somente o .env deste projeto, sem substituir variáveis do processo."""
    if (ROOT / ".env").is_file():
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=False)


def variavel_obrigatoria(nome: str) -> str:
    valor = os.environ.get(nome, "").strip()
    if not valor or valor.startswith("SUBSTITUA_"):
        raise ValueError(f"Configure a variável {nome} no ambiente local.")
    return valor


def caminho_local(valor: str) -> Path:
    caminho = Path(valor).expanduser()
    return caminho if caminho.is_absolute() else ROOT / caminho


def credencial_google() -> str:
    caminho = caminho_local(variavel_obrigatoria("GOOGLE_APPLICATION_CREDENTIALS"))
    if not caminho.is_file():
        raise ValueError("O arquivo configurado em GOOGLE_APPLICATION_CREDENTIALS não existe.")
    return str(caminho)


def validar_google() -> None:
    variavel_obrigatoria("GOOGLE_SPREADSHEET_ID")
    credencial_google()


def carregar_bases_vibra() -> dict:
    caminho = caminho_local(variavel_obrigatoria("VIBRA_BASES_FILE"))
    try:
        bases = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("Não foi possível ler o JSON local de bases Vibra.") from exc
    if not isinstance(bases, dict) or not bases:
        raise ValueError("Configure pelo menos uma base no JSON local.")
    resultado = {}
    for alias, base in bases.items():
        if not isinstance(alias, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,49}", alias):
            raise ValueError("Use aliases de base com letras maiúsculas, números e sublinhado.")
        if not isinstance(base, dict) or set(base) != {"usuario_env", "senha_env", "celulas"}:
            raise ValueError("Cada base deve conter usuario_env, senha_env e celulas.")
        for campo in ("usuario_env", "senha_env"):
            if not isinstance(base[campo], str) or not re.fullmatch(r"[A-Z][A-Z0-9_]+", base[campo]):
                raise ValueError("Informe nomes de variáveis de ambiente para as credenciais.")
        celulas = base["celulas"]
        if not isinstance(celulas, dict) or not celulas:
            raise ValueError("Cada base precisa de um mapeamento de células.")
        for chave, celula in celulas.items():
            if not re.fullmatch(r"celula_(s10|s500|gasolina)(_[1-9][0-9]*)?", chave):
                raise ValueError("Produto de célula inválido na configuração local.")
            if not isinstance(celula, str) or not re.fullmatch(r"[A-Z]{1,3}[1-9][0-9]*", celula):
                raise ValueError("Informe células no formato A1, sem fórmulas ou intervalos.")
        resultado[alias] = {
            "usuario": variavel_obrigatoria(base["usuario_env"]),
            "senha": variavel_obrigatoria(base["senha_env"]),
            **celulas,
        }
    return resultado


def desconto_por_litro() -> float:
    try:
        valor = Decimal(os.environ.get("IPIRANGA_DESCONTO_POR_LITRO", "0"))
    except InvalidOperation as exc:
        raise ValueError("IPIRANGA_DESCONTO_POR_LITRO deve ser um número decimal.") from exc
    if not valor.is_finite() or valor < 0:
        raise ValueError("IPIRANGA_DESCONTO_POR_LITRO deve ser finito e não negativo.")
    resultado = float(valor)
    if not math.isfinite(resultado):
        raise ValueError("IPIRANGA_DESCONTO_POR_LITRO está fora do intervalo suportado.")
    return resultado


def confirmar_execucao(descricao: str, permitir_aba: bool = False) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=descricao)
    parser.add_argument(
        "--executar", action="store_true",
        help="Autoriza este processo local a acessar o portal e alterar a planilha configurada.",
    )
    if permitir_aba:
        parser.add_argument("--aba", help="Nome da aba de destino no formato Preço dd-mm.")
    argumentos = parser.parse_args()
    if not argumentos.executar:
        parser.error("nenhuma ação executada: use --executar após revisar sua configuração")
    if permitir_aba and argumentos.aba is not None:
        try:
            if not re.fullmatch(r"Preço [0-9]{2}-[0-9]{2}", argumentos.aba):
                raise ValueError
            datetime.strptime(f"2000 {argumentos.aba}", "%Y Preço %d-%m")
        except ValueError:
            parser.error("informe --aba no formato Preço dd-mm, com uma data válida")
    return argumentos
