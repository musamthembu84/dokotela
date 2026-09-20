"""
Branded HTML email templates for Dokotela.

Mirrors the dark hero / gradient-text look of the marketing homepage
(slider-area, theme-gradient, btn-default) so that transactional
emails feel consistent with the product rather than generic system
notifications. Email clients can't load external CSS, so all styling
here is inlined.
"""

from core.config import settings

# Brand palette, matching the homepage's dark hero + gradient CTA.
BRAND_DARK_BG = "#0f1226"
BRAND_GRADIENT_START = "#1e3c72"
BRAND_GRADIENT_END = "#4a00e0"
BRAND_TEXT_MUTED = "#c7c9d9"


def _base_template(
    preheader: str,
    body_html: str,
    cta_text: str | None = None,
    cta_url: str | None = None,
) -> str:
    """
    Wrap page-specific content in the shared Dokotela email chrome:
    a dark gradient hero header, a white content card, an optional
    call-to-action button, and a muted footer.
    """

    cta_block = ""
    if cta_text and cta_url:
        cta_block = f"""
        <tr>
          <td align="center" style="padding: 8px 40px 32px 40px;">
            <a href="{cta_url}"
               style="display:inline-block; padding:14px 32px; border-radius:999px;
                      background:linear-gradient(90deg, {BRAND_GRADIENT_START}, {BRAND_GRADIENT_END});
                      color:#ffffff; font-size:15px; font-weight:600;
                      text-decoration:none; letter-spacing:0.2px;">
              {cta_text}
            </a>
          </td>
        </tr>
        """

    return f"""
    <html>
      <body style="margin:0; padding:0; background:#f4f5fb; font-family:'Segoe UI', Helvetica, Arial, sans-serif;">
        <span style="display:none; max-height:0; overflow:hidden;">{preheader}</span>
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
               style="background:#f4f5fb; padding:32px 0;">
          <tr>
            <td align="center">
              <table role="presentation" width="560" cellpadding="0" cellspacing="0"
                     style="background:#ffffff; border-radius:16px; overflow:hidden;
                            box-shadow:0 8px 30px rgba(15,18,38,0.08);">
                <tr>
                  <td style="background:{BRAND_DARK_BG}
                             linear-gradient(135deg, rgba(30,60,114,0.55), rgba(74,0,224,0.55));
                             padding:40px 40px 32px 40px; text-align:center;">
                    <div style="font-size:14px; letter-spacing:3px; text-transform:uppercase;
                                color:{BRAND_TEXT_MUTED}; margin-bottom:12px;">
                      DOKOTELA
                    </div>
                    <div style="font-size:26px; font-weight:700; line-height:1.35;
                                background:linear-gradient(90deg, #7fb2ff, #c58bff);
                                -webkit-background-clip:text; background-clip:text;
                                color:#a9c4ff;">
                      The medical intelligence<br/>that's always on call
                    </div>
                  </td>
                </tr>
                <tr>
                  <td style="padding:40px 40px 8px 40px; color:#1c1e2b; font-size:15px; line-height:1.7;">
                    {body_html}
                  </td>
                </tr>
                {cta_block}
                <tr>
                  <td style="padding:24px 40px 32px 40px; border-top:1px solid #eef0f7;
                             color:#9a9cb3; font-size:12px; line-height:1.6;">
                    You're receiving this email because you have an account with Dokotela.
                    <br/>
                    &copy; Dokotela &mdash; Medical AI chat, and real doctors when you need them.
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """


def welcome_email_template(username: str) -> str:
    body_html = f"""
    <p style="font-size:18px; font-weight:600; margin:0 0 16px 0;">Hi {username}, welcome aboard 👋</p>
    <p style="margin:0 0 16px 0;">
      Your Dokotela account is live. You now have a medical AI in your pocket,
      ready to listen any time of day, plus real doctors on standby when you
      need a second opinion.
    </p>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:20px 0;">
      <tr>
        <td style="padding:12px 0; border-top:1px solid #f0f1f7;">
          <strong>💬 Chat free, anytime</strong><br/>
          <span style="color:#5b5d75;">Describe your symptoms and get instant, judgment-free guidance from our Medical AI.</span>
        </td>
      </tr>
      <tr>
        <td style="padding:12px 0; border-top:1px solid #f0f1f7;">
          <strong>🩺 Real doctors, on demand</strong><br/>
          <span style="color:#5b5d75;">Escalate to a live video consultation with a licensed physician for R600/visit.</span>
        </td>
      </tr>
      <tr>
        <td style="padding:12px 0; border-top:1px solid #f0f1f7;">
          <strong>🔒 Private &amp; secure</strong><br/>
          <span style="color:#5b5d75;">Your conversations and health data are handled with care, every step of the way.</span>
        </td>
      </tr>
    </table>
    <p style="margin:0;">Talk soon,<br/>The Dokotela Team</p>
    """

    return _base_template(
        preheader="Your Dokotela account is ready. Chat with our Medical AI or book a doctor visit.",
        body_html=body_html,
        cta_text="Start with AI",
        cta_url=settings.FRONTEND_BASE_URL,
    )


def payment_success_email_template(
    username: str,
    amount: str,
    currency: str,
    payment_reference: str | None,
) -> str:
    reference_row = ""
    if payment_reference:
        reference_row = f"""
        <tr>
          <td style="padding:10px 0; color:#5b5d75;">Reference</td>
          <td style="padding:10px 0; text-align:right; font-weight:600;">{payment_reference}</td>
        </tr>
        """

    body_html = f"""
    <p style="font-size:18px; font-weight:600; margin:0 0 16px 0;">Payment received, {username} ✅</p>
    <p style="margin:0 0 20px 0;">
      Thanks for trusting Dokotela with your care. Your payment has gone through
      and your consultation is now confirmed. Here's a quick receipt for your
      records.
    </p>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
           style="background:#f8f9fd; border-radius:12px; padding:4px 20px; margin:0 0 20px 0;">
      <tr>
        <td style="padding:10px 0; color:#5b5d75; border-bottom:1px solid #eef0f7;">Amount paid</td>
        <td style="padding:10px 0; text-align:right; font-weight:700; font-size:18px;
                   border-bottom:1px solid #eef0f7;">{currency} {amount}</td>
      </tr>
      {reference_row}
      <tr>
        <td style="padding:10px 0; color:#5b5d75;">Status</td>
        <td style="padding:10px 0; text-align:right; font-weight:600; color:#1e7a3f;">Completed</td>
      </tr>
    </table>
    <p style="margin:0 0 16px 0;">
      Next up: we'll match you with an available doctor and confirm your
      appointment time by email shortly — keep an eye on your inbox.
    </p>
    <p style="margin:0;">Thanks again,<br/>The Dokotela Team</p>
    """

    return _base_template(
        preheader=f"Payment of {currency} {amount} received. Your consultation is confirmed.",
        body_html=body_html,
        cta_text="View my consultation",
        cta_url=settings.FRONTEND_BASE_URL,
    )


def booking_confirmation_patient_template(
    patient_name: str,
    doctor_name: str,
    scheduled_at_display: str,
) -> str:
    body_html = f"""
    <p style="font-size:18px; font-weight:600; margin:0 0 16px 0;">You're booked in, {patient_name} 📅</p>
    <p style="margin:0 0 20px 0;">
      Your video consultation has been confirmed with <strong>Dr. {doctor_name}</strong>.
      Here are the details:
    </p>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
           style="background:#f8f9fd; border-radius:12px; padding:4px 20px; margin:0 0 20px 0;">
      <tr>
        <td style="padding:10px 0; color:#5b5d75; border-bottom:1px solid #eef0f7;">Doctor</td>
        <td style="padding:10px 0; text-align:right; font-weight:600; border-bottom:1px solid #eef0f7;">
          Dr. {doctor_name}
        </td>
      </tr>
      <tr>
        <td style="padding:10px 0; color:#5b5d75;">Appointment time</td>
        <td style="padding:10px 0; text-align:right; font-weight:600;">{scheduled_at_display}</td>
      </tr>
    </table>
    <p style="margin:0 0 16px 0;">
      ⏰ Please log in to Dokotela <strong>5&ndash;10 minutes before</strong> your
      appointment time so your video consultation can start on time.
    </p>
    <p style="margin:0;">See you soon,<br/>The Dokotela Team</p>
    """

    return _base_template(
        preheader=f"Your consultation with Dr. {doctor_name} is confirmed for {scheduled_at_display}.",
        body_html=body_html,
        cta_text="Go to my appointments",
        cta_url=settings.FRONTEND_BASE_URL,
    )


def booking_confirmation_doctor_template(
    doctor_name: str,
    patient_name: str,
    scheduled_at_display: str,
) -> str:
    body_html = f"""
    <p style="font-size:18px; font-weight:600; margin:0 0 16px 0;">New appointment booked, Dr. {doctor_name} 📅</p>
    <p style="margin:0 0 20px 0;">
      A patient has booked a video consultation with you. Here are the details:
    </p>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
           style="background:#f8f9fd; border-radius:12px; padding:4px 20px; margin:0 0 20px 0;">
      <tr>
        <td style="padding:10px 0; color:#5b5d75; border-bottom:1px solid #eef0f7;">Patient</td>
        <td style="padding:10px 0; text-align:right; font-weight:600; border-bottom:1px solid #eef0f7;">
          {patient_name}
        </td>
      </tr>
      <tr>
        <td style="padding:10px 0; color:#5b5d75;">Appointment time</td>
        <td style="padding:10px 0; text-align:right; font-weight:600;">{scheduled_at_display}</td>
      </tr>
    </table>
    <p style="margin:0 0 16px 0;">
      ⏰ Please log in to Dokotela <strong>5&ndash;10 minutes before</strong> the
      appointment time to be ready for the video consultation.
    </p>
    <p style="margin:0;">Thanks for caring for our patients,<br/>The Dokotela Team</p>
    """

    return _base_template(
        preheader=f"New consultation booked with {patient_name} for {scheduled_at_display}.",
        body_html=body_html,
        cta_text="View my schedule",
        cta_url=settings.FRONTEND_BASE_URL,
    )
