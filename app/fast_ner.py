"""Быстрая NER-идентификация ФИО и адресов без маркеров (раздел 4 SPEC).

detect_names — таблица правил ФИО и один цикл, как RULES в detectors.py.
Регэкспы собраны из коротких именованных фрагментов; сложность функций ≤ 10.
"""
from __future__ import annotations

import bisect
import re
from dataclasses import dataclass
from typing import Callable

from app.detectors import Span
from app.lexicon import FAMOUS_SURNAMES, FIRST_NAMES, ORG_ADDR_CTX, STOP_TITLE_WORDS

# --- короткие именованные фрагменты регэкспов ---------------------------------

_WORD = r"[А-ЯЁ][А-ЯЁа-яё]+"
_INITIALS = r"[А-ЯЁ]\.\s*[А-ЯЁ]\."
_PATRONYMIC = r"[А-ЯЁ][А-ЯЁа-яё]*?(?i:(?:ович|евич|ьич|инич|овна|евна|ична)[а-яё]*)"
_SURNAME_SUFFIX = r"(?:ов|ев|ин|ын|ск|цк|их|ых|ко|ук|юк|ян|ич|дзе)[а-яё]{0,3}$"

# Полное имя: Фамилия Имя Отчество или Имя Отчество Фамилия.
_FULL_NAME = re.compile(
    r"(?<![А-ЯЁа-яё])(?:(?:" + _WORD + r")\s+(?:" + _WORD + r")\s+(?:" + _PATRONYMIC + r")"
    r"|(?:" + _WORD + r")\s+(?:" + _PATRONYMIC + r")\s+(?:" + _WORD + r"))(?![А-ЯЁа-яё])"
)
# Имя Отчество.
_IMYA_OTCH = re.compile(
    r"(?<![А-ЯЁа-яё])(" + _WORD + r")\s+(" + _PATRONYMIC + r")(?![А-ЯЁа-яё])"
)
# Фамилия И.О. / И.О. Фамилия.
_FAM_INITIALS = re.compile(
    r"(?<![А-ЯЁа-яё])(?:(?:" + _WORD + r")\s+(?:" + _INITIALS + r")"
    r"|(?:" + _INITIALS + r")\s+(?:" + _WORD + r"))(?![А-ЯЁа-яё])"
)
# Перекрывающиеся пары слов через lookahead.
_PAIR = re.compile(r"\b(?=(" + _WORD + r")\s+(" + _WORD + r")\b)")
# Одиночное имя после маркера.
_SINGLE = re.compile(r"(?:меня\s+зовут|зовут|звать|имя)\s+(" + _WORD + r")")

_SURNAME_RE = re.compile(_SURNAME_SUFFIX)
_FAMOUS_RE = re.compile(r"\b(?:" + "|".join(sorted(FAMOUS_SURNAMES)) + r")\b")
_WORD_RE = re.compile(_WORD)


@dataclass
class _Rule:
    """Правило ФИО: регэксп, приоритет, группы-спаны, валидатор, признак пары."""

    regex: re.Pattern
    priority: int
    groups: tuple[int, ...] = (0,)
    validator: Callable[[str], bool] | None = None
    pair: bool = False


def _surname_like(word: str) -> bool:
    """Слово похоже на фамилию по суффиксу."""
    return _SURNAME_RE.search(word) is not None


def _pair_ok(value: str) -> bool:
    """Одно слово — имя из словаря, другое — похоже на фамилию."""
    w1, w2 = value.split()[:2]
    a = w1.lower() in FIRST_NAMES
    b = w2.lower() in FIRST_NAMES
    return (a and _surname_like(w2)) or (b and _surname_like(w1))


def _single_ok(value: str) -> bool:
    """Одиночное слово — имя из словаря."""
    return value.lower() in FIRST_NAMES


def _imya_otch_ok(value: str) -> bool:
    """Первое слово пары «Имя Отчество» — имя из словаря."""
    return value.split()[0].lower() in FIRST_NAMES


# --- таблица правил ФИО (раздел 4 SPEC) ---------------------------------------

_NAME_RULES: tuple[_Rule, ...] = (
    _Rule(_FULL_NAME, 80),
    _Rule(_FAM_INITIALS, 76),
    _Rule(_IMYA_OTCH, 74, validator=_imya_otch_ok),
    _Rule(_PAIR, 72, pair=True, validator=_pair_ok),
    _Rule(_SINGLE, 70, groups=(1,), validator=_single_ok),
)


def _strip_title(text: str, start: int, end: int) -> int:
    """Отрезает обращение из STOP_TITLE_WORDS в начале спана."""
    while start < end:
        m = _WORD_RE.match(text, start, end)
        if m is None or m.group(0).lower() not in STOP_TITLE_WORDS:
            break
        start = m.end()
        while start < end and text[start].isspace():
            start += 1
    return start


def _famous_in_window(text: str, start: int, end: int) -> bool:
    """Публичная фамилия в окне 30 символов до матча + сам матч."""
    window = text[max(0, start - 30):end].lower()
    return _FAMOUS_RE.search(window) is not None


def detect_names(text: str) -> list[Span]:
    """Один цикл по _NAME_RULES: возвращает спаны ФИО (перекрытия не разрешает)."""
    spans: list[Span] = []
    for rule in _NAME_RULES:
        for m in rule.regex.finditer(text):
            if rule.pair:
                if m.group(1) is None or m.group(2) is None:
                    continue
                value = text[m.start(1):m.end(2)]
                if rule.validator is not None and not rule.validator(value):
                    continue
                spans.append(Span(m.start(1), m.end(2), "fio", rule.priority))
                continue
            for g in rule.groups:
                value = m.group(g)
                if value is None:
                    continue
                if rule.validator is not None and not rule.validator(value):
                    continue
                spans.append(Span(*m.span(g), "fio", rule.priority))
    return _clean_names(text, spans)


def _clean_names(text: str, spans: list[Span]) -> list[Span]:
    """Отрезает обращение и отбрасывает публичных лиц."""
    result: list[Span] = []
    for s in spans:
        start = _strip_title(text, s.start, s.end)
        if start >= s.end or _famous_in_window(text, start, s.end):
            continue
        result.append(Span(start, s.end, "fio", s.priority, s.meta))
    return result


# --- адрес: короткие именованные фрагменты ------------------------------------

_CITY = r"[А-ЯЁ][А-ЯЁа-яё-]+"
_HOUSE = r"\d+(?:\s*к\.?\s*\d+)?"
_STREET_TYPES = r"ул\.|улица|пр-т|проспект\w*|пр\.|пер\.|переулок|бул\.|бульвар|ш\.|шоссе|наб\.|набережная|пл\.|площадь|проезд|тупик"

# Город после «г./гор./город(е)».
_ADDR_CITY = re.compile(r"(?:г\.|гор\.|город\w*)\s*[:]?\s*(" + _CITY + r")")
# Улица после типа.
_ADDR_STREET_AFTER = re.compile(r"(?:" + _STREET_TYPES + r")\s*[:]?\s*(" + _CITY + r")")
# Улица перед типом (прилагательное).
_ADDR_STREET_BEFORE = re.compile(r"(" + _CITY + r")\s+(?:" + _STREET_TYPES + r")")
# Дом после «д./дом».
_ADDR_HOUSE = re.compile(r"(?:д\.|дом)\s*[:]?\s*(" + _HOUSE + r")")
# Дом после названия улицы/типа.
_ADDR_HOUSE_AFTER = re.compile(r"(?:" + _STREET_TYPES + r")\s*,?\s*(" + _HOUSE + r")")
# Квартира/офис.
_ADDR_FLAT = re.compile(r"(?:кв\.|квартира|офис|оф\.)\s*[:]?\s*(\d+)")
# Регион: «Московская область», «Республика Татарстан».
_ADDR_REGION = re.compile(r"(" + _CITY + r")\s+(?:область|край|округ)|(?:республика)\s+(" + _CITY + r")")

# Крупные города без «г.» (bare — подтверждает движок).
_CITIES: tuple[str, ...] = (
    "Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань",
    "Нижний Новгород", "Челябинск", "Самара", "Омск", "Ростов-на-Дону",
    "Уфа", "Красноярск", "Воронеж", "Пермь", "Волгоград", "Краснодар",
    "Саратов", "Тюмень", "Тольятти", "Ижевск", "Барнаул", "Ульяновск",
    "Иркутск", "Хабаровск", "Ярославль", "Владивосток", "Махачкала",
    "Томск", "Оренбург", "Кемерово", "Новокузнецк", "Рязань", "Астрахань",
    "Набережные Челны", "Пенза", "Липецк", "Киров", "Чебоксары", "Тула",
    "Калининград", "Балашиха", "Курск", "Севастополь", "Сочи", "Ставрополь",
    "Улан-Удэ", "Тверь", "Магнитогорск", "Иваново", "Брянск", "Белгород",
    "Сургут", "Владимир", "Нижний Тагил", "Архангельск", "Чита",
    "Симферополь", "Калуга", "Смоленск", "Волжский", "Якутск", "Саранск",
    "Череповец", "Курган", "Вологда", "Орёл", "Владикавказ", "Подольск",
    "Грозный", "Мурманск", "Тамбов", "Стерлитамак", "Петрозаводск",
    "Кострома", "Нижневартовск", "Новороссийск", "Йошкар-Ола", "Таганрог",
    "Комсомольск-на-Амуре", "Сыктывкар", "Нальчик", "Шахты", "Дзержинск",
    "Орск", "Братск", "Энгельс", "Ангарск", "Благовещенск", "Старый Оскол",
    "Великий Новгород", "Королёв", "Химки", "Псков", "Бийск", "Прокопьевск",
    "Балаково", "Армавир", "Северодвинск", "Люберцы", "Норильск",
    "Петропавловск-Камчатский", "Сызрань", "Каменск-Уральский",
    "Новочеркасск", "Златоуст", "Электросталь", "Альметьевск", "Салават",
    "Миасс", "Керчь", "Копейск", "Пятигорск", "Майкоп", "Коломна",
    "Одинцово", "Хасавюрт", "Находка", "Уссурийск", "Домодедово",
    "Нефтеюганск", "Батайск", "Новочебоксарск", "Серпухов", "Щёлково",
    "Кисловодск", "Первоуральск", "Орехово-Зуево", "Нефтекамск",
    "Черкесск", "Дербент", "Октябрьский", "Камышин", "Димитровград",
    "Обнинск", "Новый Уренгой", "Каспийск", "Назрань", "Ессентуки",
    "Троицк", "Ногинск", "Новошахтинск", "Сергиев Посад", "Жуковский",
    "Артём", "Северск", "Зеленоград", "Раменское", "Мичуринск",
)


def _city_forms(name: str) -> set[str]:
    """Именительный + простые косвенные падежи города."""
    low = name.lower()
    forms = {low}
    if low.endswith("а"):
        stem = low[:-1]
        forms |= {stem + e for e in ("ы", "е", "у", "ой")}
    elif low.endswith("ь"):
        stem = low[:-1]
        forms |= {stem + e for e in ("и", "ю", "ью")}
    elif low.endswith("й"):
        stem = low[:-1]
        forms |= {stem + e for e in ("я", "ю", "ем", "е")}
    elif low.endswith("и"):
        forms |= {low + e for e in ("х", "м")}
    else:
        forms |= {low + e for e in ("а", "у", "е", "ом")}
    return forms


_BARE_CITIES = frozenset(f for c in _CITIES for f in _city_forms(c)) | {"россия"}
_ADDR_BARE = re.compile(r"\b(" + "|".join(sorted(_BARE_CITIES)) + r")\b", re.IGNORECASE)

# Граница предложения: перенос строки или .!? после слова ≥4 букв с заглавной дальше.
_SENT_END = re.compile(r"[А-ЯЁа-яёA-Za-z]{4,}[.!?]\s+(?=[А-ЯЁA-Z])")


@dataclass
class _AddrRule:
    """Правило адреса: регэксп, группы-спаны, признак bare."""

    regex: re.Pattern
    groups: tuple[int, ...] = (0,)
    bare: bool = False


# --- таблица правил адреса (раздел 4 SPEC) ------------------------------------

_ADDR_RULES: tuple[_AddrRule, ...] = (
    _AddrRule(_ADDR_CITY, (1,)),
    _AddrRule(_ADDR_STREET_AFTER, (1,)),
    _AddrRule(_ADDR_STREET_BEFORE, (1,)),
    _AddrRule(_ADDR_REGION, (1, 2)),
    _AddrRule(_ADDR_HOUSE, (1,)),
    _AddrRule(_ADDR_HOUSE_AFTER, (1,)),
    _AddrRule(_ADDR_FLAT, (1,)),
    _AddrRule(_ADDR_BARE, (1,), bare=True),
)


def _sentence_starts(text: str) -> list[int]:
    """Границы предложений: 0, после переноса строки и после .!? с заглавной дальше."""
    starts = [0]
    starts.extend(m.end() for m in _SENT_END.finditer(text))
    starts.extend(i + 1 for i, ch in enumerate(text) if ch == "\n")
    return sorted(starts)


def detect_addresses(text: str) -> list[Span]:
    """Один цикл по _ADDR_RULES: возвращает спаны адресов (перекрытия не разрешает)."""
    spans: list[Span] = []
    for rule in _ADDR_RULES:
        for m in rule.regex.finditer(text):
            for g in rule.groups:
                value = m.group(g)
                if value is None:
                    continue
                meta = {"bare": True} if rule.bare else {}
                spans.append(Span(*m.span(g), "address", 0, meta))
    if not spans:
        return spans
    starts = _sentence_starts(text)
    ctx = [m.start() for m in ORG_ADDR_CTX.finditer(text)]
    out: list[Span] = []
    for s in spans:
        sent_start = starts[bisect.bisect_right(starts, s.start) - 1]
        if bisect.bisect_left(ctx, sent_start) == bisect.bisect_left(ctx, s.start):
            out.append(s)
    return out


def detect_names_and_addresses(text: str) -> list[Span]:
    """ФИО и адреса одним вызовом."""
    return detect_names(text) + detect_addresses(text)