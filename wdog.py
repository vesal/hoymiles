import time
import subprocess
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from wdogsecret import *

# Asetukset
# Tee tiedosto wgogsecret.py jossa on rivit
"""
target_host = "192.168.59.157"
email_user = "POSTIOHJELMASI KÄYTTÄJÄTUNNUS"
email_sender = "OMA SÄHKÖPOSTI1"  # Syötä oma sähköpostisi
email_receiver = "OMA SÄHKÖPOSTI2"
email_password = "SALASANA"  # Syötä sähköpostisi salasana
"""


def ftime():
    current_time = time.strftime("%y%m%d-%H:%M:%S")
    return current_time


def send_email(msg_txt):
    subject = "HomeAssistant Ping test failed!" + ftime()
    body = "Ping to {} failed at {}\n{}".format(target_host, ftime(), msg_txt)

    msg = MIMEMultipart()
    msg['From'] = email_sender
    msg['To'] = email_receiver
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))

    server = smtplib.SMTP('smtpauth2.jyu.fi', 587)
    server.starttls()
    server.login(email_user, email_password)
    text = msg.as_string()
    server.sendmail(email_sender, email_receiver, text)
    server.quit()


def check_ping(host):
    process = subprocess.Popen(['ping', '-w', '1', host], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    if process.returncode != 0:
        return stdout.decode('utf-8')
    else:
        return None


if __name__ == "__main__":
    # Pääohjelma
    time.sleep(60)  # Odota että kaikki ehtii asettua
    while True:
        ping_output = check_ping(target_host)
        if ping_output:
            print(ftime(), "Ping failed!", ping_output)
            send_email(ping_output)
            time.sleep(600)  # Tarkistaa uudestaan myöhemmin
        else:
            print(ftime(), "Ping successful.")
            time.sleep(60)  # Tarkistaa pingin joka minuutti
