"""
Formularze WTForms dla operacji handlowych.

FlexibleDecimalField – podklasa DecimalField akceptująca przecinek
jako separator dziesiętny. Rozwiązanie zgodne z dokumentacją WTForms:
https://wtforms.readthedocs.io/en/stable/fields/#wtforms.fields.DecimalField

Metoda process_formdata() jest oficjalnym punktem rozszerzania pól WTForms
– zamienia przecinek na kropkę zanim DecimalField spróbuje sparsować wartość.
"""
from decimal import Decimal
from flask_wtf import FlaskForm
from wtforms import fields, HiddenField, SubmitField
from wtforms.validators import DataRequired, NumberRange

MIN_AMOUNT = Decimal('0.0001')  # Decimal – unika błędów porównania float vs Decimal


class FlexibleDecimalField(fields.DecimalField):
    """
    DecimalField akceptujący przecinek jako separator dziesiętny.

    Polska przeglądarka wysyła "0,0001" zamiast "0.0001".
    process_formdata() jest wywoływane przez WTForms przed parsowaniem –
    zamiana przecinka na kropkę w tym miejscu jest standardowym rozwiązaniem.
    """

    def process_formdata(self, valuelist):
        if valuelist:
            valuelist[0] = valuelist[0].replace(",", ".")
        return super().process_formdata(valuelist)


class BuyForm(FlaskForm):
    coin_id = HiddenField()
    amount = FlexibleDecimalField(
        "Ilość",
        validators=[
            DataRequired(message="Podaj ilość."),
            NumberRange(
                min=MIN_AMOUNT,
                message="Minimalna wartość transakcji to $0.01. Wpisz większą ilość.",
            ),
        ],
        places=4,
    )
    submit = SubmitField("Kup")


class SellForm(FlaskForm):
    coin_id = HiddenField()
    amount = FlexibleDecimalField(
        "Ilość",
        validators=[
            DataRequired(message="Podaj ilość."),
            NumberRange(
                min=MIN_AMOUNT,
                message="Minimalna wartość transakcji to $0.01. Wpisz większą ilość.",
            ),
        ],
        places=4,
    )
    submit = SubmitField("Sprzedaj")
