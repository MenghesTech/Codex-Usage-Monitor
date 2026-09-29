from src.widget import codex_failure_text


def test_missing_codex_has_its_own_public_status():
    assert codex_failure_text("not_found") == "●  Codex no encontrado"
    assert codex_failure_text("not_found", compact=True) == "● Codex no encontrado"


def test_real_codex_failure_keeps_error_status():
    assert codex_failure_text("error") == "●  Error de Codex"
    assert codex_failure_text("error", compact=True) == "● ERROR"
