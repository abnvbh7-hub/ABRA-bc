import smtplib
import os
import dotenv
from typing import Union, List
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

dotenv.load_dotenv()

def send_email(to_email: Union[str, List[str]], subject: str, body: str):
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
        return

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = to_header
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "html"))

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, app_password)
        server.sendmail(sender_email, recipients, msg.as_string())
        server.quit()
        print(f"Email sent successfully to {recipients}!")
    except Exception as e:
        print(f"Failed to send email: {e}")
