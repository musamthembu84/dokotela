import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from core.config import settings


class EmailService:

    @staticmethod
    def send_email(to_email, subject, template, context):
        msg = MIMEMultipart()
        msg['From'] = settings.EMAIL_HOST_USER
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(template, 'html'))

        with smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT) as server:
            server.starttls()
            server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
            server.send_message(msg)
            server.quit()
