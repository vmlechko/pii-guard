"""Типы персональных данных (ПД) и их русские метки.

Единый источник истины для всех детекторов и маскирования: перечисление типов,
список всех типов и словарь русских меток для логов и метрик.
"""
from __future__ import annotations

from enum import Enum


class PII(str, Enum):
    """Типы персональных данных, которые умеет находить и маскировать модуль."""

    FIO = "fio"
    BIRTH_DATE = "birth_date"
    BIRTH_PLACE = "birth_place"
    PASSPORT = "passport"
    CITIZENSHIP = "citizenship"
    PASSPORT_ISSUER = "passport_issuer"
    DEPT_CODE = "dept_code"
    PASSPORT_DATE = "passport_date"
    DRIVER_LICENSE = "driver_license"
    ADDRESS = "address"
    EMAIL = "email"
    PHONE = "phone"
    INN = "inn"
    CARD = "card"
    CVV = "cvv"
    CARD_PIN = "card_pin"
    CARD_HOLDER = "card_holder"
    SNILS = "snils"


# Русские метки типов ПД — для логов и метрик (никогда не текст, только тип).
PII_LABEL_RU: dict[str, str] = {
    PII.FIO.value: "ФИО",
    PII.BIRTH_DATE.value: "дата рождения",
    PII.BIRTH_PLACE.value: "место рождения",
    PII.PASSPORT.value: "паспорт",
    PII.CITIZENSHIP.value: "гражданство",
    PII.PASSPORT_ISSUER.value: "орган выдачи",
    PII.DEPT_CODE.value: "код подразделения",
    PII.PASSPORT_DATE.value: "дата выдачи",
    PII.DRIVER_LICENSE.value: "водительское удостоверение",
    PII.ADDRESS.value: "адрес",
    PII.EMAIL.value: "email",
    PII.PHONE.value: "телефон",
    PII.INN.value: "ИНН",
    PII.CARD.value: "номер карты",
    PII.CVV.value: "CVV",
    PII.CARD_PIN.value: "PIN-код",
    PII.CARD_HOLDER.value: "держатель карты",
    PII.SNILS.value: "СНИЛС",
}

# Все типы ПД в порядке объявления — для политик «все типы» и метрик.
ALL_TYPES: list[str] = [member.value for member in PII]