import smtplib
import os
import dotenv
from typing import Union, List, Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

dotenv.load_dotenv()

def send_email(to_email: Union[str, List[str]], subject: str, body: str, attachment_bytes: Optional[bytes] = None, attachment_filename: Optional[str] = None):
    sender_email = "dev.rabahpapyrus@gmail.com"
    app_password = os.getenv("GMAIL_KEY")

    if isinstance(to_email, list):
        recipients = [e.strip() for e in to_email if e and isinstance(e, str) and e.strip()]
        to_header = ", ".join(recipients)
    else:
        recipients = [to_email.strip()] if (to_email and isinstance(to_email, str) and to_email.strip()) else []
        to_header = to_email

    if not recipients:
        print("No valid recipients to send email.")
        return False

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = to_header
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "html"))

    if attachment_bytes and attachment_filename:
        part = MIMEApplication(attachment_bytes, Name=attachment_filename)
        part['Content-Disposition'] = f'attachment; filename="{attachment_filename}"'
        msg.attach(part)

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, app_password)
        server.sendmail(sender_email, recipients, msg.as_string())
        server.quit()
        print(f"Email sent successfully to {recipients}!")
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False
