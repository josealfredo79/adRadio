"""
Webhooks router — combines all webhook endpoints.
"""
from fastapi import APIRouter

from app.api.v1.webhooks_pkg.twilio_incoming import twilio_incoming
from app.api.v1.webhooks_pkg.twilio_status import twilio_status
from app.api.v1.webhooks_pkg.stripe import stripe_webhook_route

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

router.add_api_route("/twilio/incoming", twilio_incoming, methods=["POST"])
router.add_api_route("/twilio/status", twilio_status, methods=["POST"])
router.add_api_route("/stripe", stripe_webhook_route, methods=["POST"])
