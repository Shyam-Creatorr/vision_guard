import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.schemas.analysis import Agent1VisualAudit
from app.services.gemini_client import GeminiDiagramClient


def test_gemini_client_repairs_invalid_json_on_retry(tmp_path):
    img = tmp_path / "diag.png"
    img.write_bytes(b"pngdata")

    bad_resp = SimpleNamespace(text='{"diagram_summary": "Missing required fields"}')
    good_payload = {
        "diagram_summary": "Plant Cell",
        "overall_legibility": "clear",
        "regions": [
            {
                "box_id": "B1",
                "label_text": "Nucleus",
                "component_type": "label",
                "bbox_1000": [100, 100, 200, 250],
                "status": "VERIFIED",
                "confidence": 0.96,
                "ambiguity_reason": None,
            }
        ],
        "connections": [],
    }
    good_resp = SimpleNamespace(text=json.dumps(good_payload))

    mock_models = MagicMock()
    mock_models.generate_content.side_effect = [bad_resp, good_resp]
    mock_client = MagicMock(models=mock_models)

    with patch("app.services.gemini_client.genai.Client", return_value=mock_client):
        client = GeminiDiagramClient()
        client.settings = MagicMock(GEMINI_API_KEY="fake-key", GEMINI_MODEL="gemini-2.5-flash", AI_TIMEOUT_SECONDS=15)
        result = client.run_visual_audit(img)

    assert isinstance(result, Agent1VisualAudit)
    assert result.regions[0].label_text == "Nucleus"
    assert mock_models.generate_content.call_count == 2
