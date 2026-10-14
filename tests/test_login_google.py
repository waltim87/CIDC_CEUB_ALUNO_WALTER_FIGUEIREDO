"""Login com Google (OAuth PKCE do Supabase) e validação do "Complete seus dados"."""

import base64
import hashlib
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlparse

from app import auth
from app.voluntarios import validar_dados_basicos

SEGREDOS = {"SUPABASE_URL": "https://projeto.supabase.co", "SUPABASE_ANON_KEY": "anon"}


class TestLinkGoogle(unittest.TestCase):
    def setUp(self) -> None:
        auth._logins_pendentes().clear()
        auth.st.session_state.pop("cidc_estado_google", None)

    def _link(self, habilitado: bool = True) -> str | None:
        with mock.patch.object(auth, "_segredo", side_effect=SEGREDOS.get), \
             mock.patch.object(auth, "google_habilitado", return_value=habilitado):
            return auth.link_google()

    def test_sem_provedor_ativo_nao_mostra_botao(self) -> None:
        self.assertIsNone(self._link(habilitado=False))

    def test_link_usa_pkce_e_verificador_fica_no_servidor(self) -> None:
        link = self._link()
        partes = urlparse(link)
        q = {k: v[0] for k, v in parse_qs(partes.query).items()}
        self.assertEqual(f"{partes.scheme}://{partes.netloc}{partes.path}", "https://projeto.supabase.co/auth/v1/authorize")
        self.assertEqual(q["provider"], "google")
        self.assertEqual(q["code_challenge_method"], "s256")
        estado = parse_qs(urlparse(q["redirect_to"]).query)["cidc_estado"][0]
        self.assertTrue(q["redirect_to"].startswith(auth.URL_APP_PADRAO))
        verificador = auth._logins_pendentes()[estado][0]
        self.assertNotIn(verificador, link)
        esperado = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
        self.assertEqual(q["code_challenge"], esperado)

    def test_mesma_sessao_reaproveita_o_estado(self) -> None:
        self.assertEqual(self._link(), self._link())
        self.assertEqual(len(auth._logins_pendentes()), 1)


class TestCompletarDados(unittest.TestCase):
    def test_validacoes(self) -> None:
        self.assertIn("termo", validar_dados_basicos("Maria Silva", "97 99999-0000", "1302405", False))
        self.assertIn("nome completo", validar_dados_basicos("Maria", "97 99999-0000", "1302405", True))
        self.assertIn("DDD", validar_dados_basicos("Maria Silva", "99999", "1302405", True))
        self.assertIn("município", validar_dados_basicos("Maria Silva", "(97) 99999-0000", None, True))
        self.assertIsNone(validar_dados_basicos("Maria Silva", "(97) 99999-0000", "1302405", True))


if __name__ == "__main__":
    unittest.main()
