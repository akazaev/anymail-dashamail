# anymail-dashamail

[`DashaMail`](https://dashamail.ru/) transactional email backend for [`django-anymail`](https://github.com/anymail/django-anymail).

This package lets you keep the standard Django/Anymail sending API while routing messages through the DashaMail Transactional API.

## Features

- Drop-in `EMAIL_BACKEND` for Django
- Works with `ANYMAIL` settings style
- Supports plain text and HTML emails
- Supports `to`, `cc`, `bcc`, `reply_to`, custom headers
- Supports regular and inline attachments
- Supports Anymail options: `merge_data`, `merge_global_data`, `send_at`, `track_opens`, `track_clicks`, `esp_extra`
- Includes a real-send CLI script for end-to-end verification

## Compatibility

Verified with:

- `django-anymail==13.1`
- `django-anymail==14.0`

## Installation

From local path:

```bash
pip install -e /path/to/anymail-dashamail
```

## Django configuration

Use the backend in `settings.py`:

```python
EMAIL_BACKEND = "anymail_dashamail.backend.EmailBackend"

ANYMAIL = {
    # Required
    "DASHAMAIL_API_KEY": "<your-dashamail-api-key>",

    # Optional (default shown)
    "DASHAMAIL_API_URL": "https://api.dashamail.ru/",

    # Optional global anymail settings
    # "REQUESTS_TIMEOUT": 30,
    # "IGNORE_UNSUPPORTED_FEATURES": False,
    # "DEBUG_API_REQUESTS": False,
}
```

## Field mapping

- `from_email` -> `from_email` (+ `from_name` when display name exists)
- `to`, `cc`, `bcc` -> comma-separated strings
- `subject` -> `subject`
- text body -> `plain_text`
- HTML body -> `message`
- `reply_to` -> `headers["Reply-To"]`
- custom headers -> `headers`
- attachments -> `attachments`
- inline attachments -> `inline`
- `send_at` -> `delivery_time` (Unix timestamp)
- `merge_data` -> `replace`
- `merge_global_data` -> `template_data`
- `track_opens=False` -> `no_track_opens=1`
- `track_clicks=False` -> `no_track_clicks=1`
- `esp_extra` -> merged into API payload

## Usage example

```python
from django.core.mail import EmailMultiAlternatives

msg = EmailMultiAlternatives(
    subject="Order #123",
    body="Plain text fallback",
    from_email="Shop <sales@example.com>",
    to=["user@example.com"],
)
msg.attach_alternative("<h1>Order #123</h1><p>Thanks!</p>", "text/html")
msg.track_opens = False
msg.track_clicks = False
msg.send()
```

## Real-send test script

A ready-to-use script is provided in:

- `send_test_email.py`

It sends several real messages to verify key functionality:

- basic text
- html + headers + reply-to
- regular attachment + inline image
- `merge_data` + `merge_global_data`
- tracking flags + `esp_extra`
- scheduled send (+2 minutes, optional)

Run:

```bash
python scripts/send_test_email.py \
  --to you@example.com \
  --api-key <DASHAMAIL_API_KEY> \
  --from-email "QA Team <qa@example.com>" \
  --reply-to support@example.com
```

Skip scheduled test:

```bash
python scripts/send_test_email.py \
  --to you@example.com \
  --api-key <DASHAMAIL_API_KEY> \
  --from-email "QA Team <qa@example.com>" \
  --skip-scheduled
```

The script exits with non-zero status if at least one scenario fails.

## Limitations

- Current scope is send API integration (`transactional.send`)
- Webhooks and inbound processing are not included
- `transactional.check` is not exposed as Django backend API

## Development

Quick local check:

```bash
python -m py_compile anymail_dashamail/backend.py scripts/send_test_email.py
```

Run tests with pytest:

```bash
python -m pip install -e ".[test]"
pytest -q
```

## Contributing

Issues and pull requests are welcome.

When reporting bugs, include:

- `django-anymail` version
- Django version
- Python version
- minimal failing example
- sanitized API response if possible

## License

MIT, see `LICENSE`.
