__author__ = 'wpanderson'

"""
Test script for sending an email from a server. Can be easily modified to work in any program that needs email
functionality.
"""

import os

import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import COMMASPACE, formatdate

FROM_ADDR = 'ENTER_FROM'
TO_ADDR = ['ENTER_TO', 'ENTER_TO']
EMAIL_PASS = 'PW'
USER_NAME = FROM_ADDR


def send_mail(send_from, send_to, subject, text, files=None, server="smtp.gmail.com:587"):
    """

    :param send_from:
    :param send_to:
    :param subject:
    :param text:
    :param files:
    :param server:
    :return:
    """

    print('Sending email...')
    msg = MIMEMultipart()
    msg['From'] = send_from
    msg['To'] = COMMASPACE.join(send_to)
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = subject

    msg.attach(MIMEText(text))
    # print('prefile')
    for f in files or []:
        print('File: ', f)
        with open(f, 'rb') as fil:
            part = MIMEApplication(fil.read(), Name=os.path.basename(f))
            part['Content-Disposition'] = 'attachment; filename="%s"' % os.path.basename(f)
            msg.attach(part)
    # print('complete')
    smtp = smtplib.SMTP(server)
    smtp.ehlo()
    smtp.starttls()
    smtp.login(USER_NAME, EMAIL_PASS)
    smtp.sendmail(send_from, send_to, msg.as_string())
    smtp.close()
    print('Email sent to {0}!'.format(send_to))


if __name__ == '__main__':
    send_mail(FROM_ADDR, TO_ADDR, 'Greetings from Wesvis', "Hello Gary,\nIt's nice to meet you. I'm sorry about "
                                                                "what happened to Solaris.\n\n - Wesvis")

