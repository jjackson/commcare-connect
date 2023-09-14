from django.conf import settings
from twilio.rest import Client


class SMSException(Exception):
    pass


def send_sms(to, body):
    if not (settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_MESSAGING_SERVICE):
        raise SMSException("Twilio credentials not provided")
    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    client.messages.create(body=body, to=to, messaging_service_sid=settings.TWILIO_MESSAGING_SERVICE)
