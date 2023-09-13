from django.conf import settings
from twilio.rest import Client


def send_sms(to, body):
    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    client.messages.create(body=body, to=to, messaging_service_sid=settings.TWILIO_MESSAGING_SERVICE)
