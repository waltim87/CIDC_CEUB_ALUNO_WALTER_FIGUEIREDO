"""Chat interno: texto exibido sem formatação vinda da mensagem e horário de Manaus."""

import unittest
from datetime import datetime, timezone

from app.chat import hora_local, rotulo_canal, texto_seguro


class TestChat(unittest.TestCase):
    def test_mensagem_nao_vira_link_imagem_ou_formatacao(self) -> None:
        self.assertEqual(texto_seguro("![x](http://rastreio)"), r"\!\[x\]\(http://rastreio\)")
        self.assertEqual(texto_seguro("**urgente** _agora_"), r"\*\*urgente\*\* \_agora\_")
        self.assertEqual(texto_seguro("<b>oi</b>"), r"\<b\>oi\</b\>")
        self.assertEqual(texto_seguro("linha 1\nlinha 2"), "linha 1  \nlinha 2")
        self.assertEqual(texto_seguro(None), "")

    def test_hora_de_manaus(self) -> None:
        agora = datetime(2026, 10, 14, 18, 0, tzinfo=timezone.utc)
        self.assertEqual(hora_local("2026-10-14T17:30:00+00:00", agora), "13:30")
        self.assertEqual(hora_local("2026-10-13T12:05:00Z", agora), "13/10 08:05")
        self.assertEqual(hora_local(None), "")

    def test_rotulo_por_tipo(self) -> None:
        self.assertEqual(rotulo_canal({"tipo": "comunidades", "nome": "Purus"}), "🛶 Purus")
        self.assertEqual(rotulo_canal({"tipo": "privado", "nome": "Equipe"}), "🔒 Equipe")


if __name__ == "__main__":
    unittest.main()
