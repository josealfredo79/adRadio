"""
Webhooks router — combines all webhook endpoints.
"""
from fastapi import APIRouter

from app.api.v1.webhooks_pkg.meta_incoming import meta_incoming, meta_webhook_verify
from app.api.v1.webhooks_pkg.stripe import stripe_webhook_route

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

router.add_api_route("/meta", meta_webhook_verify, methods=["GET"])
router.add_api_route("/meta", meta_incoming, methods=["POST"])
router.add_api_route("/stripe", stripe_webhook_route, methods=["POST"])
