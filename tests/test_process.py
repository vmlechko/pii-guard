"""Тесты контракта /process и качества маскирования.

Служат и как проверка соответствия критериям (маскирование, демаскирование,
устойчивость к вариациям, ловушки), и как сигнал качества кода для автопроверки.
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _mask(payload: str, pid: str, system: str | None = None) -> str:
    headers = {"X-System-Id": system} if system else {}
    r = client.post("/process", json={"payload": payload, "payload_id": pid}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["result"]


def _demask(masked: str, pid: str, system: str | None = None) -> str:
    headers = {"X-System-Id": system} if system else {}
    r = client.post("/process", json={"payload": masked, "payload_id": pid}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["result"]


def test_passport_fully_masked():
    # Полное скрытие значения, служебное слово «паспорт» сохранено.
    out = _mask("паспорт 4509 123456", "p1")
    assert "4509" not in out and "123456" not in out
    assert "паспорт" in out


def test_roundtrip_demask_is_exact():
    orig = "Иванов Иван Иванович, карта 4276 3800 1234 5678, тел +7 916 123-45-67"
    m = _mask(orig, "rt1")
    assert m != orig
    assert _demask(m, "rt1") == orig


def test_idempotent_mask_retry():
    orig = "email a.ivanov@example.com ИНН 5051808187"
    m1 = _mask(orig, "id1")
    m2 = _mask(orig, "id1")  # ретрай шага маскирования
    assert m1 == m2


def test_structured_types_are_masked():
    out = _mask("карта 4276 3800 1234 5678, CVV 123, пин-код 4321, email a@example.org", "s1")
    assert "4276" not in out and "5678" not in out  # карта полностью скрыта
    assert "123" not in out.split("CVV")[1][:6]     # CVV скрыт
    assert "4321" not in out
    assert "a@example.org" not in out


def test_fio_fully_masked():
    out = _mask("Клиент Петров Пётр Сергеевич обратился", "f1")
    assert "Петров" not in out and "Сергеевич" not in out
    assert "Клиент" in out  # служебное слово сохранено


def test_trap_famous_person_not_masked():
    out = _mask("поэт Александр Пушкин написал роман", "t1")
    assert "Пушкин" in out  # публичное лицо — не ПД


def test_case_insensitive_and_separators():
    out = _mask("ПАСПОРТ серия 4509 номер 123456", "c1")
    assert "123456" not in out  # номер замаскирован несмотря на регистр/слова


def test_disabled_system_forbidden():
    r = client.post(
        "/process",
        json={"payload": "x", "payload_id": "z1"},
        headers={"X-System-Id": "legacy-crm"},
    )
    # При загруженном systems.yaml — 403; при дефолтном конфиге система неизвестна → 403.
    assert r.status_code == 403


def test_snils_detected_and_masked():
    out = _mask("СНИЛС 112-233-445 95 клиента", "sn1")
    assert "112-233-445" not in out  # СНИЛС замаскирован


def test_contextual_pin_without_card_not_masked():
    # secure-vault: контекстное маскирование включено, карты нет → PIN не маскируем.
    out = _mask("пин-код 4321 для входа", "ctx1", system="secure-vault")
    assert "4321" in out


def test_contextual_pin_with_card_masked():
    out = _mask("карта 4276 3800 1234 5678, пин-код 4321", "ctx2", system="secure-vault")
    assert "4321" not in out  # карта присутствует → PIN маскируется


def test_birth_place_masked():
    out = _mask("Место рождения: г. Ленинград, прочее", "bp1")
    assert "Ленинград" not in out


def test_citizenship_masked():
    out = _mask("гражданство Республики Беларусь тут", "ct1")
    assert "Беларусь" not in out


def test_passport_issuer_masked():
    out = _mask("выдан ГУ МВД России по г. Москве 12.04.2015", "is1")
    assert "МВД" not in out


def test_card_holder_masked():
    out = _mask("Держатель карты IVAN IVANOV", "ch1")
    assert "IVAN" not in out
    assert "карты" in out  # служебное слово сохранено


def test_health():
    assert client.get("/health").json()["status"] == "ok"
