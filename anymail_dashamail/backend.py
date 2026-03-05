from anymail.backends.base_requests import AnymailRequestsBackend, RequestsPayload
from anymail.exceptions import AnymailRequestsAPIError
from anymail.message import AnymailRecipientStatus
from anymail.utils import CaseInsensitiveCasePreservingDict, get_anymail_setting


class EmailBackend(AnymailRequestsBackend):
    """DashaMail (dashamail.ru) transactional API Email Backend."""

    esp_name = "DashaMail"

    def __init__(self, **kwargs):
        esp_name = self.esp_name

        self.api_key = get_anymail_setting(
            "api_key", esp_name=esp_name, kwargs=kwargs, allow_bare=True
        )
        api_url = get_anymail_setting(
            "api_url",
            esp_name=esp_name,
            kwargs=kwargs,
            default="https://api.dashamail.ru/",
        )
        if not api_url.endswith("/"):
            api_url += "/"

        super().__init__(api_url, **kwargs)

    def build_message_payload(self, message, defaults):
        return DashaMailPayload(message, defaults, self)

    def parse_recipient_status(self, response, payload, message):
        parsed_response = self.deserialize_json_response(response, payload, message)

        try:
            api_response = parsed_response["response"]
            msg = api_response["msg"]
            err_code = int(msg.get("err_code", -1))
        except (KeyError, TypeError, ValueError) as err:
            raise AnymailRequestsAPIError(
                "Invalid DashaMail API response format",
                email_message=message,
                payload=payload,
                response=response,
                backend=self,
            ) from err

        if err_code != 0:
            raise AnymailRequestsAPIError(
                msg.get("text", "DashaMail API error"),
                email_message=message,
                payload=payload,
                response=response,
                backend=self,
            )

        data = api_response.get("data", {})

        transaction_id = None
        if isinstance(data, dict):
            transaction_id = data.get("transaction_id")

        recipient_status = CaseInsensitiveCasePreservingDict(
            {
                recip.addr_spec: AnymailRecipientStatus(
                    message_id=transaction_id, status="queued"
                )
                for recip in payload.recipients
            }
        )

        # detailed_answer format can include recipient-specific identifiers
        if isinstance(data, dict):
            for recip in payload.recipients:
                recipient_message_id = data.get(recip.addr_spec)
                if isinstance(recipient_message_id, str):
                    recipient_status[recip.addr_spec] = AnymailRecipientStatus(
                        message_id=recipient_message_id, status="queued"
                    )

        return dict(recipient_status)


class DashaMailPayload(RequestsPayload):
    def __init__(self, message, defaults, backend, *args, **kwargs):
        self.recipients = []
        self.to_recipients = []

        headers = kwargs.pop("headers", {})
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"
        super().__init__(
            message,
            defaults,
            backend,
            params={"method": "transactional.send"},
            headers=headers,
            *args,
            **kwargs,
        )

    def init_payload(self):
        self.data = {"api_key": self.backend.api_key}

    def serialize_data(self):
        # Show all To recipients in one message when merge features are not used.
        if len(self.to_recipients) > 1 and not self.is_batch():
            self.data.setdefault("multi_to", 1)
        return self.serialize_json(self.data)

    def _idna_encode_domain(self, domain):
        encoder = getattr(self.backend, "idna_encode", None)
        if callable(encoder):
            return encoder(domain)

        try:
            import idna

            return idna.encode(domain).decode("ascii")
        except Exception:
            return domain

    def _format_address(self, email):
        try:
            return email.format(idna_encode=self._idna_encode_domain)
        except (AttributeError, TypeError):
            # Compatibility with older anymail EmailAddress.format signatures.
            return str(email)

    def _format_addresses(self, emails):
        return ", ".join(self._format_address(email) for email in emails)

    def _format_addr_spec(self, email):
        if hasattr(email, "format_addr_spec"):
            return email.format_addr_spec(idna_encode=self._idna_encode_domain)

        addr_spec = getattr(email, "addr_spec", None) or str(email)
        if "@" in addr_spec:
            local_part, domain = addr_spec.rsplit("@", 1)
            return f"{local_part}@{self._idna_encode_domain(domain)}"
        return addr_spec

    def set_from_email(self, email):
        self.data["from_email"] = self._format_addr_spec(email)
        if email.display_name:
            self.data["from_name"] = email.display_name

    def set_recipients(self, recipient_type, emails):
        if not emails:
            return
        assert recipient_type in ["to", "cc", "bcc"]
        self.data[recipient_type] = self._format_addresses(emails)
        self.recipients += emails
        if recipient_type == "to":
            self.to_recipients = emails

    def set_subject(self, subject):
        self.data["subject"] = subject

    def set_reply_to(self, emails):
        if emails:
            self.data.setdefault("headers", {})["Reply-To"] = self._format_addresses(
                emails
            )

    def set_extra_headers(self, headers):
        self.data.setdefault("headers", {}).update(headers)

    def set_text_body(self, body):
        self.data["plain_text"] = body

    def set_html_body(self, body):
        if "message" in self.data:
            self.unsupported_feature("multiple html parts")
        self.data["message"] = body

    def make_attachment(self, attachment):
        if attachment.inline:
            if not attachment.cid:
                self.unsupported_feature("inline attachments without Content-ID")
            return {
                "mime_type": attachment.mimetype,
                "filename": attachment.name or "inline",
                "body": attachment.b64content,
                "cid": attachment.cid,
            }

        return {
            "name": attachment.name or "attachment",
            "filebody": attachment.b64content,
        }

    def set_attachments(self, attachments):
        if not attachments:
            return

        regular = []
        inline = []
        for attachment in attachments:
            if attachment.inline:
                inline.append(self.make_attachment(attachment))
            else:
                regular.append(self.make_attachment(attachment))

        if regular:
            self.data["attachments"] = regular
        if inline:
            self.data["inline"] = inline

    def set_send_at(self, send_at):
        try:
            send_at = int(send_at.timestamp())
        except AttributeError:
            # Caller can pass custom pre-formatted value
            pass
        self.data["delivery_time"] = send_at

    def set_template_id(self, template_id):
        self.data["message"] = template_id

    def set_merge_global_data(self, merge_global_data):
        self.data["template_data"] = merge_global_data

    def set_merge_data(self, merge_data):
        replace = {addr_spec: values for addr_spec, values in merge_data.items() if values}
        if replace:
            self.data["replace"] = replace

    def set_track_clicks(self, track_clicks):
        if track_clicks is False:
            self.data["no_track_clicks"] = 1

    def set_track_opens(self, track_opens):
        if track_opens is False:
            self.data["no_track_opens"] = 1

    def set_esp_extra(self, extra):
        self.data.update(extra)
