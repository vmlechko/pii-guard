"""Структурная идентификация ПД по таблице правил раздела 3 SPEC.

Один цикл по RULES, без веток на каждый тип. Возвращает сырые спаны (возможны
перекрытия и дубли) — их разрешает engine после подтверждения bare-спанов.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from app.pii_types import PII

# --- короткие именованные фрагменты регэкспов ---------------------------------

_DATE_ISO = r"\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}"
_DATE_DMY = r"\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}"
# ISO первым, чтобы «1990-03-05» не разбирался как DMY «1990-03».
_DATE = rf"(?:{_DATE_ISO}|{_DATE_DMY})"

_PHONE_SEP = r"[\s\-()]*"
_PHONE = r"(?:\+7|8|7)" + _PHONE_SEP + r"\d{3}" + _PHONE_SEP + r"\d{3}" + _PHONE_SEP + r"\d{2}" + _PHONE_SEP + r"\d{2}"

_SNILS = r"\d{3}[\s-]?\d{3}[\s-]?\d{3}[\s-]?\d{2}"
_DL = r"\d{2}\s?\d{2}\s?\d{6}"
_CARD = r"\d(?:[ \-]?\d){12,18}"
_MONTHS = r"(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)"
_FIO_MARKERS = r"ФИО|клиент\w*|пациент\w*|заявитель\w*|плательщик\w*|получатель\w*|на\s+имя"

# Значение с заглавной до запятой/точки/переноса; точка внутри не допускается.
_CAP_VALUE = r"[А-ЯЁA-Z][^,.;\n]*"
# То же, но точка не обрывает (для значений с «г.»/«гор.»).
_CAP_VALUE_DOT = r"[А-ЯЁA-Z][^,\n]*"
# Значение с любой буквы до запятой/переноса (для «гор. Омск» и т.п.).
_VALUE_DOT = r"[А-ЯЁа-яёA-Za-z][^,\n]*"


def kw(alternatives: str) -> str:
    """Регистронезависимые ключевые слова с lookahead-префильтром по первым буквам."""
    firsts = "".join(alt[0] for alt in alternatives.split("|") if alt)
    chars = "".join(dict.fromkeys(firsts + firsts.upper() + firsts.lower()))
    return rf"(?=[{chars}])(?i:{alternatives})"


# --- валидаторы ---------------------------------------------------------------

def luhn_ok(digits: str) -> bool:
    """Проверка контрольной суммы Luhn по цифрам."""
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


_INN10 = (2, 4, 10, 3, 5, 9, 4, 6, 8)
_INN11 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
_INN12 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)


def inn_ok(value: str) -> bool:
    """Контрольная сумма ИНН (10 или 12 цифр)."""
    digits = re.sub(r"\D", "", value)
    if len(digits) == 10:
        return sum(int(d) * w for d, w in zip(digits, _INN10, strict=False)) % 11 % 10 == int(digits[9])
    if len(digits) == 12:
        c1 = sum(int(d) * w for d, w in zip(digits, _INN11, strict=False)) % 11 % 10
        c2 = sum(int(d) * w for d, w in zip(digits, _INN12, strict=False)) % 11 % 10
        return c1 == int(digits[10]) and c2 == int(digits[11])
    return False


def snils_ok(value: str) -> bool:
    """Контрольная сумма СНИЛС по первым 9 цифрам."""
    digits = re.sub(r"\D", "", value)
    if len(digits) != 11:
        return False
    total = sum(int(d) * (9 - i) for i, d in enumerate(digits[:9])) % 101
    if total in (100, 101):
        total = 0
    return total == int(digits[9:11])


def card_ok(value: str) -> bool:
    """Номер карты проходит Luhn (разделители игнорируются)."""
    return luhn_ok(re.sub(r"\D", "", value))


def phone_ok(value: str) -> bool:
    """6–11 цифр в номере телефона."""
    return 6 <= len(re.sub(r"\D", "", value)) <= 11


def plausible_birth_year(year: int) -> bool:
    """Год рождения правдоподобен: [1900, текущий−14]."""
    return 1900 <= year <= datetime.now().year - 14


def _year_from_date(value: str) -> int | None:
    """Извлекает год из даты; двузначный год расширяет (90→1990, 05→2005)."""
    parts = re.findall(r"\d{2,4}", value)
    if not parts:
        return None
    for p in parts:
        if len(p) == 4:
            return int(p)
    y = int(parts[-1])
    return y + (1900 if y >= 70 else 2000)


def _birth_year_ok(value: str) -> bool:
    """Дата рождения правдоподобна по году."""
    year = _year_from_date(value)
    return year is not None and plausible_birth_year(year)


# --- структуры ----------------------------------------------------------------

@dataclass
class Span:
    """Спан ПД в тексте; meta["bare"] — требует подтверждения контекстом."""

    start: int
    end: int
    type: str
    priority: int = 0
    meta: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Rule:
    """Правило детекции: регэксп, тип, приоритет, группы-спаны, валидатор."""

    regex: re.Pattern
    pii_type: str
    priority: int
    groups: tuple[int, ...] = (0,)
    validator: Callable[[str], bool] | None = None
    bare: bool = False


# --- таблица правил раздела 3 -------------------------------------------------

RULES: tuple[Rule, ...] = (
    Rule(re.compile(r"\b[\w.+\-]+@[A-Za-z0-9\-]+\.[A-Za-z0-9.\-]+\b"), PII.EMAIL.value, 90),
    Rule(re.compile(r"(?<!\d)" + _PHONE + r"(?!\d)"), PII.PHONE.value, 80),
    Rule(
        re.compile(kw(r"тел\.?|телефон\w*|моб\.?|phone") + r"\s*[:]?\s*(\d[\d\s\-()]{5,10})"),
        PII.PHONE.value, 79, groups=(1,), validator=phone_ok,
    ),
    Rule(re.compile(_CARD), PII.CARD.value, 95, validator=card_ok),
    Rule(
        re.compile(kw(r"карт\w*|card|pan") + r"\s*[:]?\s*(" + _CARD + r")"),
        PII.CARD.value, 93, groups=(1,),
    ),
    Rule(
        re.compile(r"(?i)\b(?:cvv2?|cvc2?)\b\s*[:]?\s*(\d{3})"),
        PII.CVV.value, 95, groups=(1,),
    ),
    Rule(
        re.compile(kw(r"пин|pin") + r"(?:[\s-]?код)?(?:\s+карты)?\s*[:]?\s*(\d{4})"),
        PII.CARD_PIN.value, 95, groups=(1,),
    ),
    Rule(
        re.compile(kw(r"держатель\s+карты|cardholder") + r"\s*[:]?\s*([А-ЯЁA-Z][\w\-]*(?:\s+[А-ЯЁA-Z][\w\-]*){0,2})"),
        PII.CARD_HOLDER.value, 84, groups=(1,),
    ),
    Rule(
        re.compile(kw(r"паспорт\w*") + r"\s*[:]?\s*(?:серия\s*)?(\d{2}\s?\d{2})\s*(?:номер|№)?\s*(\d{6})"),
        PII.PASSPORT.value, 88, groups=(1, 2),
    ),
    Rule(
        re.compile(r"(?<!\d)(\d{2}\s?\d{2})(?:\s+|\s*(?:№|номер)\s*)(\d{6})(?!\d)"),
        PII.PASSPORT.value, 70, groups=(1, 2),
    ),
    Rule(
        re.compile(kw(r"код\s+подразделения|к/п|к\.п\.") + r"\s*[:]?\s*(\d{3}-?\d{3})"),
        PII.DEPT_CODE.value, 76, groups=(1,),
    ),
    Rule(re.compile(r"(?<!\d)(\d{3}-\d{3})(?!\d)"), PII.DEPT_CODE.value, 75, groups=(1,), bare=True),
    Rule(
        re.compile(kw(r"дата\s+выдачи|выдан") + r".{0,80}?(" + _DATE + r")"),
        PII.PASSPORT_DATE.value, 72, groups=(1,),
    ),
    Rule(
        re.compile(kw(r"выдан") + r"\s*" + _DATE + r"\s*(" + _CAP_VALUE_DOT + r")"),
        PII.PASSPORT_ISSUER.value, 70, groups=(1,),
    ),
    Rule(
        re.compile(kw(r"выдан") + r"\s*(" + _CAP_VALUE_DOT + r"?)\s+" + _DATE),
        PII.PASSPORT_ISSUER.value, 70, groups=(1,),
    ),
    Rule(
        re.compile(kw(r"водительское\s+удостоверение|в/у|права") + r"\s*[:№]?\s*(" + _DL + r")"),
        PII.DRIVER_LICENSE.value, 85, groups=(1,),
    ),
    Rule(
        re.compile(kw(r"ИНН") + r".{0,12}?(\d{12}|\d{10})(?!\d)"),
        PII.INN.value, 92, groups=(1,), validator=inn_ok,
    ),
    Rule(re.compile(r"(?<!\d)(\d{12}|\d{10})(?!\d)"), PII.INN.value, 60, groups=(1,), validator=inn_ok),
    Rule(
        re.compile(kw(r"СНИЛС") + r"\s*[:]?\s*(" + _SNILS + r")"),
        PII.SNILS.value, 94, groups=(1,), validator=snils_ok,
    ),
    Rule(re.compile(r"(?<!\d)(" + _SNILS + r")(?!\d)"), PII.SNILS.value, 82, groups=(1,), validator=snils_ok),
    Rule(
        re.compile(kw(r"дата\s+рождения|д\.р\.|родился") + r"\s*[:]?\s*(" + _DATE + r")"),
        PII.BIRTH_DATE.value, 74, groups=(1,),
    ),
    Rule(re.compile(r"(" + _DATE + r")\s*г\.р\."), PII.BIRTH_DATE.value, 74, groups=(1,)),
    Rule(
        re.compile(r"(\d{1,2}\s+" + _MONTHS + r"\s+\d{4})"),
        PII.BIRTH_DATE.value, 55, groups=(1,), validator=_birth_year_ok,
    ),
    Rule(
        re.compile(r"(?<!\d)(" + _DATE + r")(?!\d)"),
        PII.BIRTH_DATE.value, 50, groups=(1,), validator=_birth_year_ok,
    ),
    Rule(
        re.compile(kw(r"место\s+рождения|м\.р\.") + r"\s*[:]?\s*(" + _VALUE_DOT + r")"),
        PII.BIRTH_PLACE.value, 71, groups=(1,),
    ),
    Rule(
        re.compile(kw(r"гражданство") + r"\s*[:]?\s*(" + _CAP_VALUE + r")"),
        PII.CITIZENSHIP.value, 73, groups=(1,),
    ),
    Rule(
        re.compile(kw(r"гражданин\w*") + r"\s*(" + _CAP_VALUE + r")"),
        PII.CITIZENSHIP.value, 73, groups=(1,),
    ),
    Rule(re.compile(kw(r"индекс") + r"\s*[:]?\s*(\d{6})"), PII.ADDRESS.value, 65, groups=(1,)),
    Rule(re.compile(r"(?<!\d)(\d{6})(?=,\s*(?:г\.|гор\.|город|[А-ЯЁ][а-яё]+))"), PII.ADDRESS.value, 63, groups=(1,)),
    Rule(re.compile(r"(Россия|РФ)\s*,\s*индекс"), PII.ADDRESS.value, 63, groups=(1,)),
    Rule(
        re.compile(kw(_FIO_MARKERS) + r"\s*[:]?\s*([А-ЯЁ][А-ЯЁа-яё]+(?:\s+[А-ЯЁ][А-ЯЁа-яё]+){1,2})"),
        PII.FIO.value, 79, groups=(1,),
    ),
)


def _rule_spans(m: re.Match, rule: Rule) -> list[Span]:
    """Спаны одного матча правила: по каждой группе с валидатором."""
    spans: list[Span] = []
    for g in rule.groups:
        value = m.group(g)
        if value is None:
            continue
        if rule.validator is not None and not rule.validator(value):
            continue
        start, end = m.span(g)
        meta = {"bare": True} if rule.bare else {}
        spans.append(Span(start, end, rule.pii_type, rule.priority, meta))
    return spans


def detect_structured(text: str) -> list[Span]:
    """Один цикл по RULES: возвращает сырые спаны (перекрытия не разрешает)."""
    spans: list[Span] = []
    for rule in RULES:
        for m in rule.regex.finditer(text):
            spans += _rule_spans(m, rule)
    return spans


def resolve_overlaps(spans: list[Span]) -> list[Span]:
    """Разрешает перекрытия: приоритет, длина, позиция; байтовая карта занятых позиций."""
    spans.sort(key=lambda s: (-s.priority, -(s.end - s.start), s.start))
    occupied = bytearray(max((s.end for s in spans), default=0))
    result: list[Span] = []
    for s in spans:
        if not any(occupied[s.start:s.end]):
            occupied[s.start:s.end] = b"\x01" * (s.end - s.start)
            result.append(s)
    return result