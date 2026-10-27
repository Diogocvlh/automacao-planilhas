"""Verificações offline; não importam coletores nem acessam serviços externos."""

import json
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import config


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.base_file = Path(self.folder.name) / "bases.json"

    def write_base(self, **changes):
        base = {
            "usuario_env": "TEST_USER",
            "senha_env": "TEST_PASSWORD",
            "celulas": {"celula_s10": "B5"},
            **changes,
        }
        self.base_file.write_text(json.dumps({"BASE_DEMO": base}), encoding="utf-8")
        os.environ.update(
            VIBRA_BASES_FILE=str(self.base_file),
            TEST_USER="usuario_ficticio",
            TEST_PASSWORD="senha_ficticia_apenas_teste",
        )

    def test_missing_variable_has_actionable_name(self):
        with self.assertRaisesRegex(ValueError, "GOOGLE_SPREADSHEET_ID"):
            config.variavel_obrigatoria("GOOGLE_SPREADSHEET_ID")

    def test_example_placeholder_is_not_a_configured_secret(self):
        os.environ["TEST_PASSWORD"] = "SUBSTITUA_SENHA"
        with self.assertRaises(ValueError):
            config.variavel_obrigatoria("TEST_PASSWORD")

    def test_loads_credentials_from_named_environment_variables(self):
        self.write_base()
        bases = config.carregar_bases_vibra()
        self.assertEqual(bases["BASE_DEMO"]["usuario"], "usuario_ficticio")
        self.assertEqual(bases["BASE_DEMO"]["celula_s10"], "B5")

    def test_rejects_inline_secret_fields(self):
        self.write_base(senha="nao_permitido")
        with self.assertRaisesRegex(ValueError, "usuario_env"):
            config.carregar_bases_vibra()

    def test_missing_secret_error_does_not_echo_another_secret(self):
        self.write_base()
        del os.environ["TEST_PASSWORD"]
        with self.assertRaises(ValueError) as error:
            config.carregar_bases_vibra()
        self.assertIn("TEST_PASSWORD", str(error.exception))
        self.assertNotIn("usuario_ficticio", str(error.exception))

    def test_rejects_formula_instead_of_cell_address(self):
        self.write_base(celulas={"celula_s10": "=IMPORTDATA(A1)"})
        with self.assertRaisesRegex(ValueError, "formato A1"):
            config.carregar_bases_vibra()

    def test_rejects_unknown_product_key(self):
        self.write_base(celulas={"produto_invalido": "B5"})
        with self.assertRaisesRegex(ValueError, "Produto"):
            config.carregar_bases_vibra()

    def test_rejects_invalid_json_without_echoing_contents(self):
        self.base_file.write_text("conteudo_privado_invalido", encoding="utf-8")
        os.environ["VIBRA_BASES_FILE"] = str(self.base_file)
        with self.assertRaises(ValueError) as error:
            config.carregar_bases_vibra()
        self.assertNotIn("conteudo_privado_invalido", str(error.exception))

    def test_google_requires_a_real_local_file(self):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(Path(self.folder.name) / "missing.json")
        with self.assertRaisesRegex(ValueError, "não existe"):
            config.credencial_google()

    def test_relative_paths_are_resolved_from_project(self):
        self.assertEqual(config.caminho_local("secrets/test.json"), config.ROOT / "secrets/test.json")

    def test_discount_defaults_to_zero_and_accepts_decimal(self):
        self.assertEqual(config.desconto_por_litro(), 0.0)
        os.environ["IPIRANGA_DESCONTO_POR_LITRO"] = "0.1"
        self.assertEqual(config.desconto_por_litro(), 0.1)

    def test_discount_rejects_negative_nonfinite_and_invalid_values(self):
        for value in ("-1", "NaN", "Infinity", "abc", "1e999999"):
            with self.subTest(value=value):
                os.environ["IPIRANGA_DESCONTO_POR_LITRO"] = value
                with self.assertRaises(ValueError):
                    config.desconto_por_litro()

    def test_execution_requires_an_explicit_cli_flag(self):
        with patch("sys.argv", ["coletor.py"]), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                config.confirmar_execucao("Teste offline")
        self.assertEqual(error.exception.code, 2)

    def test_execution_accepts_an_explicit_cli_flag_without_side_effects(self):
        with patch("sys.argv", ["coletor.py", "--executar"]):
            config.confirmar_execucao("Teste offline")


if __name__ == "__main__":
    unittest.main()
