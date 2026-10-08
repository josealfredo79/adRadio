from app.models.user import User
from app.services.chat_quick_asks import SALES_QUICK_ASKS, chat_quick_asks


def test_iaradio_account_gets_sales_buttons():
    assert chat_quick_asks(User(email="TecnologicoTlaxiaco@gmail.com")) == SALES_QUICK_ASKS


def test_other_businesses_keep_default_buttons():
    assert chat_quick_asks(User(email="tacos@example.com")) is None
    assert chat_quick_asks(User(email=None)) is None
