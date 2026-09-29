import pytest

from app.config import get_settings
from app.notifications.mailer import MailerError, send_email


def test_message_has_single_to_no_cc_bcc_and_utf8_subject(mailpit):
    send_email("a@example.test", "Nhắc hạn free time – Đỏ", "<p>Container <b>ABCU1234567</b></p>")
    (message,) = mailpit.to("a@example.test")
    assert [a["Address"] for a in message["To"]] == ["a@example.test"]
    assert message["Cc"] == [] and message["Bcc"] == []
    assert message["Subject"] == "Nhắc hạn free time – Đỏ"
    assert "ABCU1234567" in message["HTML"]


@pytest.mark.parametrize(("to", "subject"), [("a@example.test", "x\nBcc: evil@example.test"), ("a@example.test\n", "x")])
def test_header_injection_rejected_before_connecting(mailpit, to, subject):
    with pytest.raises(ValueError, match="xuống dòng"):
        send_email(to, subject, "<p>x</p>")
    assert mailpit.count() == 0


def test_smtp_unreachable_raises_mailer_error(monkeypatch):
    monkeypatch.setattr(get_settings(), "smtp_port", 1)  # cổng đóng
    with pytest.raises(MailerError):
        send_email("a@example.test", "x", "<p>x</p>")
