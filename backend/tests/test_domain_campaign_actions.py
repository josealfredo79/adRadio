"""check_content_complete — pure function, no DB needed. Guards against the
2026-09-18 bug where the Copiloto could launch a campaign by chat without
the content its mode requires (REST's resume_campaign already validated
this; the Copiloto reimplemented the rest of the launch flow but skipped
this check)."""
import uuid

import pytest

from app.domain.campaign_actions import (
    CampaignContentIncompleteError,
    check_content_complete,
)
from app.models.campaign import Campaign


def _campaign(**overrides) -> Campaign:
    defaults = {
        "id": uuid.uuid4(),
        "advertiser_id": uuid.uuid4(),
        "name": "Test",
        "type": "promo",
        "message_text": "Hola!",
        "status": "draft",
        "ab_test": {"enabled": False},
    }
    defaults.update(overrides)
    return Campaign(**defaults)


class TestCheckContentComplete:
    def test_regular_mode_requires_message_text(self):
        campaign = _campaign(message_text="", ab_test={"campaign_mode": "regular"})
        with pytest.raises(CampaignContentIncompleteError):
            check_content_complete(campaign)

    def test_regular_mode_passes_with_message(self):
        campaign = _campaign(message_text="Hola!", ab_test={"campaign_mode": "regular"})
        check_content_complete(campaign)  # no debe lanzar

    def test_radio_mode_requires_audio_url(self):
        campaign = _campaign(ab_test={"campaign_mode": "radio"})
        with pytest.raises(CampaignContentIncompleteError):
            check_content_complete(campaign)

    def test_radio_mode_passes_with_audio_url(self):
        campaign = _campaign(ab_test={"campaign_mode": "radio", "audio_url": "https://x/a.mp3"})
        check_content_complete(campaign)

    def test_comunitaria_mode_requires_audio_url(self):
        campaign = _campaign(ab_test={"campaign_mode": "comunitaria"})
        with pytest.raises(CampaignContentIncompleteError):
            check_content_complete(campaign)

    def test_banner_mode_requires_image_url(self):
        campaign = _campaign(ab_test={"campaign_mode": "banner"}, image_url=None)
        with pytest.raises(CampaignContentIncompleteError):
            check_content_complete(campaign)

    def test_banner_mode_passes_with_image_url(self):
        campaign = _campaign(ab_test={"campaign_mode": "banner"}, image_url="https://x/b.png")
        check_content_complete(campaign)

    def test_non_draft_campaign_is_never_blocked(self):
        """Ya salió de draft (running/paused/etc) — se asume que ya pasó
        esta validación cuando se lanzó la primera vez."""
        campaign = _campaign(status="paused", ab_test={"campaign_mode": "radio"})
        check_content_complete(campaign)
