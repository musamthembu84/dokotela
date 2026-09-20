import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from core.config import settings
from service.email_templates import (
    welcome_email_template,
    payment_success_email_template,
    booking_confirmation_patient_template,
    booking_confirmation_doctor_template,
)

logger = logging.getLogger(__name__)


class EmailService:

    @staticmethod
    def send_email(to_email: str, subject: str, html_body: str) -> None:
        """
        Send an HTML email using the configured SMTP server.

        Port 465 uses implicit SSL (SMTP_SSL); any other port (e.g. 587)
        uses STARTTLS on a plain connection, so this works with both
        Gmail-style (587) and Afrihost-style (465) mail providers.
        """
        msg = MIMEMultipart()
        msg['From'] = settings.SMTP_FROM
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(html_body, 'html'))

        if settings.SMTP_PORT == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(
                settings.SMTP_HOST, settings.SMTP_PORT, context=context
            ) as server:
                if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                    server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.send_message(msg)
            return

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(msg)

    @staticmethod
    def send_welcome_email(to_email: str, username: str) -> None:
        """
        Send a welcome email to a newly registered user.

        Any failure is logged, not raised, so registration is never
        blocked by an email delivery problem.
        """
        subject = "Welcome to Dokotela \u2014 your medical AI is ready"
        html_body = welcome_email_template(username)

        try:
            EmailService.send_email(to_email, subject, html_body)
        except Exception:
            logger.exception(
                "Failed to send welcome email to %s", to_email
            )

    @staticmethod
    def send_payment_success_email(
        to_email: str,
        username: str,
        amount: str,
        currency: str,
        payment_reference: str | None = None,
    ) -> None:
        """
        Notify a patient that their payment has been received and their
        consultation is confirmed. Failures are logged, not raised, so a
        slow/broken mail server never blocks the payment webhook.
        """
        subject = "Payment received \u2014 your Dokotela consultation is confirmed"
        html_body = payment_success_email_template(
            username, amount, currency, payment_reference
        )

        try:
            EmailService.send_email(to_email, subject, html_body)
        except Exception:
            logger.exception(
                "Failed to send payment success email to %s", to_email
            )

    @staticmethod
    def send_booking_confirmation_emails(
        patient_email: str,
        patient_name: str,
        doctor_email: str,
        doctor_name: str,
        scheduled_at_display: str,
    ) -> None:
        """
        Notify both the patient and the doctor that a video consultation
        has been booked. Each send is independent — if one fails, the
        other still goes out, and neither failure blocks the booking.
        """
        try:
            EmailService.send_email(
                patient_email,
                "Your Dokotela appointment is confirmed",
                booking_confirmation_patient_template(
                    patient_name, doctor_name, scheduled_at_display
                ),
            )
        except Exception:
            logger.exception(
                "Failed to send booking confirmation to patient %s", patient_email
            )

        try:
            EmailService.send_email(
                doctor_email,
                "New appointment booked on Dokotela",
                booking_confirmation_doctor_template(
                    doctor_name, patient_name, scheduled_at_display
                ),
            )
        except Exception:
            logger.exception(
                "Failed to send booking confirmation to doctor %s", doctor_email
            )
