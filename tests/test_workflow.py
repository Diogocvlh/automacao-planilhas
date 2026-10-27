"""Regressões de encadeamento com dependências externas substituídas por mocks."""

import contextlib
import importlib.util
import io
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import config


ROOT = Path(__file__).resolve().parents[1]


def carregar_coletor(nome):
    dependencias = (
        "gspread", "gspread.utils", "google", "google.oauth2",
        "google.oauth2.service_account", "selenium", "selenium.webdriver",
        "selenium.webdriver.chrome", "selenium.webdriver.chrome.service",
        "selenium.webdriver.common", "selenium.webdriver.common.by",
        "selenium.webdriver.support", "selenium.webdriver.support.ui",
        "selenium.webdriver.support.expected_conditions", "webdriver_manager",
        "webdriver_manager.chrome",
    )
    substitutos = {nome: MagicMock() for nome in dependencias}
    spec = importlib.util.spec_from_file_location(f"offline_{nome}", ROOT / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, substitutos):
        spec.loader.exec_module(modulo)
    return modulo


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.preparador = carregar_coletor("rodar_tudo")
        self.coletor = carregar_coletor("vibra")
        self.saida = io.StringIO()
        self.capture = contextlib.redirect_stdout(self.saida)
        self.capture.__enter__()
        self.addCleanup(self.capture.__exit__, None, None, None)

    def configurar_fluxo(self, stack):
        for nome in ("confirmar_execucao", "carregar_ambiente", "validar_google", "carregar_bases_vibra"):
            stack.enter_context(patch.object(self.preparador, nome))
        return stack.enter_context(patch.object(self.preparador.subprocess, "run"))

    def test_preparation_returns_next_business_day_when_today_exists(self):
        class Relogio(datetime):
            @classmethod
            def now(cls):
                return cls(2026, 10, 30)  # Sexta-feira.

        planilha = MagicMock()
        planilha.worksheets.return_value = [MagicMock(title="Preço 30-10")]
        with (
            patch.object(self.preparador, "datetime", Relogio),
            patch.object(self.preparador, "abrir_planilha_do_mes", return_value=planilha),
            patch.object(self.preparador, "encontrar_aba_base"),
            patch.object(self.preparador, "construir_alteracoes_seguras_fob", return_value=([], [])),
            patch.object(self.preparador, "construir_remocoes_validacao_total", return_value=[]),
        ):
            self.assertEqual(self.preparador.preparar_aba(), "Preço 02-11")
        self.assertEqual(planilha.duplicate_sheet.call_args.kwargs["new_sheet_name"], "Preço 02-11")

    def test_workflow_forwards_the_prepared_target_to_the_collector(self):
        with contextlib.ExitStack() as stack:
            executar = self.configurar_fluxo(stack)
            stack.enter_context(patch.object(self.preparador, "preparar_aba", return_value="Preço 02-11"))
            self.preparador.executar_fluxo()
        argumentos = executar.call_args.args[0]
        self.assertEqual(argumentos[-3:], ["--executar", "--aba", "Preço 02-11"])
        self.assertTrue(executar.call_args.kwargs["check"])

    def test_preparation_failure_stops_before_starting_the_collector(self):
        with contextlib.ExitStack() as stack:
            executar = self.configurar_fluxo(stack)
            stack.enter_context(patch.object(self.preparador, "preparar_aba", side_effect=RuntimeError("Falha de teste")))
            with self.assertRaises(RuntimeError):
                self.preparador.executar_fluxo()
        executar.assert_not_called()
        self.assertNotIn("finalizado com sucesso", self.saida.getvalue())

    def test_collector_failure_is_propagated_without_success_message(self):
        with contextlib.ExitStack() as stack:
            executar = self.configurar_fluxo(stack)
            stack.enter_context(patch.object(self.preparador, "preparar_aba", return_value="Preço 02-11"))
            executar.side_effect = self.preparador.subprocess.CalledProcessError(1, ["coletor-ficticio"])
            with self.assertRaises(self.preparador.subprocess.CalledProcessError):
                self.preparador.executar_fluxo()
        self.assertNotIn("finalizado com sucesso", self.saida.getvalue())

    def test_sheet_open_failure_raises_instead_of_silently_returning(self):
        cliente = MagicMock()
        cliente.open_by_key.side_effect = ValueError("detalhe_privado_ficticio")
        with (
            patch.object(self.preparador, "conectar_cliente", return_value=(cliente, "conta_ficticia")),
            patch.object(self.preparador, "variavel_obrigatoria", return_value="planilha_ficticia"),
        ):
            with self.assertRaises(RuntimeError) as error:
                self.preparador.abrir_planilha_do_mes()
        self.assertNotIn("detalhe_privado_ficticio", str(error.exception))

    def test_target_argument_accepts_valid_dates_and_rejects_invalid_dates(self):
        with patch("sys.argv", ["vibra.py", "--executar", "--aba", "Preço 29-02"]):
            argumentos = config.confirmar_execucao("Teste", permitir_aba=True)
        self.assertEqual(argumentos.aba, "Preço 29-02")
        for nome in ("Preço 31-02", "Preço 00-01", "outra aba"):
            with (
                self.subTest(nome=nome),
                patch("sys.argv", ["vibra.py", "--executar", "--aba", nome]),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                config.confirmar_execucao("Teste", permitir_aba=True)

    def executar_base(self, itens, salvar):
        driver = MagicMock()
        driver.find_elements.return_value = itens
        self.coletor.BASES_VIBRA = {
            "BASE_DEMO": {"usuario": "ficticio", "senha": "ficticia", "celula_s10": "B5"},
        }
        with (
            patch.object(self.coletor.webdriver, "Chrome", return_value=driver),
            patch.object(self.coletor, "aceitar_todos_cookies_vibra"),
            patch.object(self.coletor.time, "sleep"),
            patch.object(self.coletor, "salvar_no_google_direto", salvar),
        ):
            with self.assertRaises(RuntimeError):
                self.coletor.rodar_coleta("BASE_DEMO", "Preço 02-11")
        driver.quit.assert_called_once()

    def test_persistence_failure_escapes_item_parsing_and_closes_the_browser(self):
        item = MagicMock()
        item.text = "Diesel S10"
        item.find_element.return_value.text = "6,1234"
        salvar = MagicMock(side_effect=RuntimeError("Falha de persistência fictícia"))
        self.executar_base([item], salvar)
        salvar.assert_called_once_with("B5", "6,1234", "Preço 02-11")

    def test_zero_writes_is_a_failure_instead_of_reported_success(self):
        salvar = MagicMock()
        self.executar_base([], salvar)
        salvar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
