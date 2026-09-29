"""Gửi email qua SMTP (dev/prod đều là Mailpit): một người nhận, chống chèn header, lỗi mạng bọc thành MailerError."""

import smtplib
from email.message import EmailMessage

from app.config import get_settings

TEXT_FALLBACK = "Vui lòng xem email ở dạng HTML."
SMTP_TIMEOUT_SECONDS = 10


class MailerError(Exception):
    """Không gửi được email (SMTP lỗi hoặc không kết nối được)."""


def send_email(to: str, subject: str, html: str) -> None:
    if any(ch in value for value in (to, subject) for ch in "\r\n"):
        raise ValueError("Địa chỉ nhận và tiêu đề không được chứa xuống dòng")
    settings = get_settings()
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = settings.smtp_from, to, subject
    message.set_content(TEXT_FALLBACK)
    message.add_alternative(html, subtype="html")
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password.get_secret_value())
            smtp.send_message(message)
    except (smtplib.SMTPException, OSError) as error:
        raise MailerError(str(error)) from error
