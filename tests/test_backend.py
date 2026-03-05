import json
from datetime import datetime, timezone
from email.message import MIMEPart
from io import BytesIO
from unittest.mock import patch

import django
import requests
from django.conf import settings
from django.core import mail
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.test import SimpleTestCase, override_settings

from anymail.exceptions import AnymailRequestsAPIError, AnymailUnsupportedFeature


if not settings.configured:
    settings.configure(
        SECRET_KEY="test-secret",
        USE_TZ=True,
        EMAIL_BACKEND="anymail_dashamail.backend.EmailBackend",
        ANYMAIL={
            "DASHAMAIL_API_KEY": "test-api-key",
            "DASHAMAIL_API_URL": "https://api.dashamail.ru/",
        },
        INSTALLED_APPS=[],
    )
django.setup()


class RequestsBackendMockAPITestCase(SimpleTestCase):
    DEFAULT_RAW_RESPONSE = b'{"response":{"msg":{"err_code":0,"text":"ok"},"data":{"transaction_id":"tx-1"}}}'
    DEFAULT_CONTENT_TYPE = "application/json"
    DEFAULT_STATUS_CODE = 200

    class MockResponse(requests.Response):
        def __init__(
            self,
            status_code=200,
            raw=b"{}",
            content_type=None,
            encoding="utf-8",
            reason=None,
            test_case=None,
        ):
            super().__init__()
            self.status_code = status_code
            self.encoding = encoding
            self.reason = reason or ("OK" if 200 <= status_code < 300 else "ERROR")
            self.raw = BytesIO(raw)
            if content_type is not None:
                self.headers["Content-Type"] = content_type
            self.test_case = test_case

        @property
        def url(self):
            return self.test_case.get_api_call_arg("url", required=False)

        @url.setter
        def url(self, value):
            if value is not None:
                raise ValueError("MockResponse can't handle url assignment")

    def setUp(self):
        super().setUp()
        self.patch_request = patch("requests.Session.request", autospec=True)
        self.mock_request = self.patch_request.start()
        self.addCleanup(self.patch_request.stop)
        self.set_mock_response()

    def set_mock_response(
        self,
        *,
        status_code=None,
        raw=None,
        json_data=None,
        encoding="utf-8",
        content_type=None,
        reason=None,
    ):
        if status_code is None:
            status_code = self.DEFAULT_STATUS_CODE
        if json_data is not None:
            raw = json.dumps(json_data).encode(encoding)
            if content_type is None:
                content_type = "application/json"
        if raw is None:
            raw = self.DEFAULT_RAW_RESPONSE
        if content_type is None:
            content_type = self.DEFAULT_CONTENT_TYPE

        mock_response = self.MockResponse(
            status_code=status_code,
            raw=raw,
            content_type=content_type,
            encoding=encoding,
            reason=reason,
            test_case=self,
        )
        self.mock_request.return_value = mock_response
        return mock_response

    def get_api_call_arg(self, kwarg, required=True):
        if self.mock_request.call_args is None:
            raise AssertionError("API was not called")

        args, kwargs = self.mock_request.call_args
        if kwarg in kwargs:
            return kwargs[kwarg]

        order = (
            "method",
            "url",
            "params",
            "data",
            "headers",
            "cookies",
            "files",
            "auth",
            "timeout",
            "allow_redirects",
            "proxies",
            "hooks",
            "stream",
            "verify",
            "cert",
            "json",
        )
        try:
            return args[order.index(kwarg)]
        except (ValueError, IndexError):
            if required:
                self.fail(f"API was called without required arg '{kwarg}'")
            return None

    def get_api_call_json(self):
        return json.loads(self.get_api_call_arg("data"))


@override_settings(
    EMAIL_BACKEND="anymail_dashamail.backend.EmailBackend",
    ANYMAIL={
        "DASHAMAIL_API_KEY": "test-api-key",
        "DASHAMAIL_API_URL": "https://api.dashamail.ru/",
    },
)
class DashaMailBackendPayloadTests(RequestsBackendMockAPITestCase):
    def test_basic_send_payload(self):
        mail.send_mail(
            "Subject here",
            "Here is the message.",
            "From Name <from@example.com>",
            ["to@example.com"],
            fail_silently=False,
        )

        self.assertEqual(self.get_api_call_arg("method"), "POST")
        self.assertEqual(self.get_api_call_arg("url"), "https://api.dashamail.ru/")
        self.assertEqual(self.get_api_call_arg("params"), {"method": "transactional.send"})

        headers = self.get_api_call_arg("headers")
        self.assertEqual(headers["Accept"], "application/json")
        self.assertEqual(headers["Content-Type"], "application/json")

        data = self.get_api_call_json()
        self.assertEqual(data["api_key"], "test-api-key")
        self.assertEqual(data["from_email"], "from@example.com")
        self.assertEqual(data["from_name"], "From Name")
        self.assertEqual(data["to"], "to@example.com")
        self.assertEqual(data["subject"], "Subject here")
        self.assertEqual(data["plain_text"], "Here is the message.")

    def test_html_and_text_body(self):
        msg = EmailMultiAlternatives(
            "Subject", "Text body", "from@example.com", ["to@example.com"]
        )
        msg.attach_alternative("<p>HTML body</p>", "text/html")
        msg.send()

        data = self.get_api_call_json()
        self.assertEqual(data["plain_text"], "Text body")
        self.assertEqual(data["message"], "<p>HTML body</p>")

    def test_reply_to_and_custom_headers(self):
        msg = EmailMessage(
            "Subject",
            "Body",
            "from@example.com",
            ["to@example.com"],
            headers={"X-Test": "123"},
            reply_to=["reply@example.com"],
        )
        msg.send()

        data = self.get_api_call_json()
        self.assertEqual(data["headers"]["Reply-To"], "reply@example.com")
        self.assertEqual(data["headers"]["X-Test"], "123")

    def test_merge_data_template_data_and_tracking(self):
        msg = EmailMessage("Subject", "Hi %NAME%", "from@example.com", ["to@example.com"])
        msg.merge_data = {"to@example.com": {"%NAME%": "Test User"}}
        msg.merge_global_data = {"support_email": "support@example.com"}
        msg.track_clicks = False
        msg.track_opens = False
        msg.send()

        data = self.get_api_call_json()
        self.assertEqual(
            data["replace"], {"to@example.com": {"%NAME%": "Test User"}}
        )
        self.assertEqual(data["template_data"], {"support_email": "support@example.com"})
        self.assertEqual(data["no_track_clicks"], 1)
        self.assertEqual(data["no_track_opens"], 1)

    def test_send_at_and_esp_extra(self):
        msg = EmailMessage("Subject", "Body", "from@example.com", ["to@example.com"])
        msg.send_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        msg.esp_extra = {"detailed_answer": 1, "dkim": 1}
        msg.send()

        data = self.get_api_call_json()
        self.assertEqual(data["delivery_time"], 1767323045)
        self.assertEqual(data["detailed_answer"], 1)
        self.assertEqual(data["dkim"], 1)

    def test_multi_to_enabled_for_multi_recipient_non_batch(self):
        msg = EmailMessage(
            "Subject",
            "Body",
            "from@example.com",
            ["to1@example.com", "to2@example.com"],
        )
        msg.send()
        data = self.get_api_call_json()
        self.assertEqual(data["multi_to"], 1)

    def test_multi_to_not_for_batch_send(self):
        msg = EmailMessage(
            "Subject",
            "Hello",
            "from@example.com",
            ["to1@example.com", "to2@example.com"],
        )
        msg.merge_data = {
            "to1@example.com": {"%NAME%": "One"},
            "to2@example.com": {"%NAME%": "Two"},
        }
        msg.send()
        data = self.get_api_call_json()
        self.assertNotIn("multi_to", data)

    def test_attachments_and_inline(self):
        msg = EmailMultiAlternatives(
            "Subject", "Body", "from@example.com", ["to@example.com"]
        )
        msg.attach("test.txt", b"hello", "text/plain")
        inline = MIMEPart()
        inline.set_content(
            b"img",
            maintype="image",
            subtype="png",
            disposition="inline",
            cid="<cid-1>",
            filename="img.png",
        )
        msg.attach(inline)
        msg.send()

        data = self.get_api_call_json()
        self.assertEqual(len(data["attachments"]), 1)
        self.assertEqual(data["attachments"][0]["name"], "test.txt")
        self.assertEqual(len(data["inline"]), 1)
        self.assertEqual(data["inline"][0]["filename"], "img.png")
        self.assertEqual(data["inline"][0]["cid"], "cid-1")

    def test_multiple_html_parts_unsupported(self):
        msg = EmailMultiAlternatives(
            "Subject", "Body", "from@example.com", ["to@example.com"]
        )
        msg.attach_alternative("<p>one</p>", "text/html")
        msg.attach_alternative("<p>two</p>", "text/html")
        with self.assertRaises(AnymailUnsupportedFeature):
            msg.send()


@override_settings(
    EMAIL_BACKEND="anymail_dashamail.backend.EmailBackend",
    ANYMAIL={
        "DASHAMAIL_API_KEY": "test-api-key",
        "DASHAMAIL_API_URL": "https://api.dashamail.ru/",
    },
)
class DashaMailBackendResponseTests(RequestsBackendMockAPITestCase):
    def test_status_uses_transaction_id_as_message_id(self):
        msg = EmailMessage("Subject", "Body", "from@example.com", ["to@example.com"])
        msg.send()
        self.assertEqual(msg.anymail_status.status, {"queued"})
        self.assertEqual(
            msg.anymail_status.recipients["to@example.com"].message_id, "tx-1"
        )

    def test_api_error_on_invalid_response_shape(self):
        self.set_mock_response(json_data={"unexpected": {}})
        with self.assertRaises(AnymailRequestsAPIError):
            mail.send_mail("Subject", "Body", "from@example.com", ["to@example.com"])

    def test_api_error_on_err_code(self):
        self.set_mock_response(
            json_data={"response": {"msg": {"err_code": 100, "text": "bad request"}}}
        )
        with self.assertRaises(AnymailRequestsAPIError) as cm:
            mail.send_mail("Subject", "Body", "from@example.com", ["to@example.com"])
        self.assertIn("bad request", str(cm.exception))

    def test_detailed_answer_recipient_ids(self):
        self.set_mock_response(
            json_data={
                "response": {
                    "msg": {"err_code": 0, "text": "ok"},
                    "data": {
                        "transaction_id": "tx-common",
                        "to1@example.com": "tx-1",
                        "to2@example.com": "tx-2",
                    },
                }
            }
        )
        msg = EmailMessage(
            "Subject",
            "Body",
            "from@example.com",
            ["to1@example.com", "to2@example.com"],
        )
        msg.send()
        self.assertEqual(msg.anymail_status.status, {"queued"})
        self.assertEqual(msg.anymail_status.recipients["to1@example.com"].message_id, "tx-1")
        self.assertEqual(msg.anymail_status.recipients["to2@example.com"].message_id, "tx-2")
