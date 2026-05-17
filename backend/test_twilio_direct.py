import os
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

account_sid = os.getenv('TWILIO_ACCOUNT_SID')
auth_token = os.getenv('TWILIO_AUTH_TOKEN')
client = Client(account_sid, auth_token)

# Try with the +521 number first (what Twilio registered)
try:
    print("Testing with +5215599631448...")
    message = client.messages.create(
        body="🎙️ Prueba de fuego desde IaRadio (Script directo). Si lees esto, la conexión está perfecta.",
        from_='whatsapp:+5215599631448',
        to='whatsapp:+529531953182'
    )
    print(f"✅ Success! Message SID: {message.sid}")
except Exception as e:
    print(f"❌ Failed with +521: {e}")

    # Try with the +5255 number (what we had originally)
    try:
        print("\nTesting with +525599631448...")
        message = client.messages.create(
            body="🎙️ Prueba de fuego desde IaRadio (Script directo). Si lees esto, la conexión está perfecta.",
            from_='whatsapp:+525599631448',
            to='whatsapp:+529531953182'
        )
        print(f"✅ Success! Message SID: {message.sid}")
    except Exception as e:
        print(f"❌ Failed with +5255: {e}")
