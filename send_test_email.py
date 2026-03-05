#!/usr/bin/env python3
import argparse
import base64
import sys
from datetime import timedelta

import django
from django.conf import settings
from django.core.mail import EmailMessage, EmailMultiAlternatives, get_connection
from django.utils import timezone


PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAQAAAAEACAIAAADTED8xAAADMElEQVR4nOzVwQnAIBQFQYXff81RUkQCOyDj1YOPnbXWPmeTRef+/3O/OyBjzh3CD9"
    "5BfqICMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0C"
    "MK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK"
    "0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0C"
    "MK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK"
    "0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0C"
    "MK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK"
    "0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0C"
    "MK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK"
    "0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMO0TAAD"
    "//2Anhf4QtqobAAAAAElFTkSuQmCC"
)


def configure_django(api_key, api_url):
    if settings.configured:
        return

    settings.configure(
        SECRET_KEY="dashamail-test-script",
        INSTALLED_APPS=[],
        EMAIL_BACKEND="anymail_dashamail.backend.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@example.com",
        ANYMAIL={
            "DASHAMAIL_API_KEY": api_key,
            "DASHAMAIL_API_URL": api_url,
            "REQUESTS_TIMEOUT": 30,
            "IGNORE_UNSUPPORTED_FEATURES": False,
        },
    )
    django.setup()


def print_status(label, msg):
    recipients = msg.anymail_status.recipients
    print(f"\n[{label}] sent")
    for email, status in recipients.items():
        print(
            f"  - {email}: status={status.status}, "
            f"message_id={status.message_id}"
        )


def send_basic(connection, to_email, from_email):
    msg = EmailMessage(
        subject="[DashaMail Test] Basic text",
        body="Basic text body",
        from_email=from_email,
        to=[to_email],
        connection=connection,
    )
    msg.send(fail_silently=False)
    print_status("basic", msg)


def send_html_headers(connection, to_email, from_email, reply_to):
    msg = EmailMultiAlternatives(
        subject="[DashaMail Test] HTML + headers",
        body="Plain text fallback",
        from_email=from_email,
        to=[to_email],
        reply_to=[reply_to] if reply_to else [],
        headers={"X-Test-Header": "dashamail-anymail"},
        connection=connection,
    )
    msg.attach_alternative("<h1>HTML body</h1><p>Hello</p>", "text/html")
    msg.send(fail_silently=False)
    print_status("html_headers", msg)


def send_attachments_inline(connection, to_email, from_email):
    msg = EmailMultiAlternatives(
        subject="[DashaMail Test] Attachments + inline",
        body="See html and attachment",
        from_email=from_email,
        to=[to_email],
        connection=connection,
    )
    msg.attach_alternative(
        '<p>Inline image below:</p><img src="cid:test-inline-image">', "text/html"
    )

    msg.attach("test.txt", b"attachment payload", "text/plain")
    msg.attach(
        "pixel.png",
        base64.b64decode(PNG_BASE64),
        "image/png",
    )

    # Build inline attachment compatible with Django email API
    from email.mime.image import MIMEImage

    inline = MIMEImage(base64.b64decode(PNG_BASE64), _subtype="png")
    inline.add_header("Content-ID", "<test-inline-image>")
    inline.add_header("Content-Disposition", "inline", filename="inline.png")
    msg.attach(inline)

    msg.send(fail_silently=False)
    print_status("attachments_inline", msg)


def send_merge_and_template_data(connection, to_email, from_email):
    msg = EmailMultiAlternatives(
        subject="[DashaMail Test] merge_data + template_data",
        body="Hi %NAME%",
        from_email=from_email,
        to=[to_email],
        connection=connection,
    )
    msg.attach_alternative("<p>Hi %NAME%</p>", "text/html")

    msg.merge_data = {to_email: {"%NAME%": "Test User", "%ORDER_ID%": "A-100"}}
    msg.merge_global_data = {"support_email": from_email}

    msg.send(fail_silently=False)
    print_status("merge_template_data", msg)


def send_tracking_and_esp_extra(connection, to_email, from_email):
    msg = EmailMessage(
        subject="[DashaMail Test] tracking + esp_extra",
        body="Tracking should be disabled for this message",
        from_email=from_email,
        to=[to_email],
        connection=connection,
    )
    msg.track_opens = False
    msg.track_clicks = False
    msg.esp_extra = {"detailed_answer": 1}
    msg.send(fail_silently=False)
    print_status("tracking_esp_extra", msg)


def send_scheduled(connection, to_email, from_email):
    msg = EmailMessage(
        subject="[DashaMail Test] scheduled send",
        body="This message is scheduled for +2 minutes",
        from_email=from_email,
        to=[to_email],
        connection=connection,
    )
    msg.send_at = timezone.now() + timedelta(minutes=2)
    msg.send(fail_silently=False)
    print_status("scheduled", msg)


def main():
    parser = argparse.ArgumentParser(
        description="Send real test emails through anymail-dashamail backend"
    )
    parser.add_argument("--to", required=True, help="Recipient email")
    parser.add_argument("--api-key", required=True, help="DashaMail API key")
    parser.add_argument(
        "--from-email",
        required=True,
        help='From address, example: "QA Team <qa@example.com>"',
    )
    parser.add_argument(
        "--api-url",
        default="https://api.dashamail.ru/",
        help="DashaMail API URL",
    )
    parser.add_argument("--reply-to", default=None, help="Optional Reply-To")
    parser.add_argument(
        "--skip-scheduled",
        action="store_true",
        help="Skip scheduled send test",
    )
    args = parser.parse_args()

    configure_django(args.api_key, args.api_url)

    connection = get_connection(
        "anymail_dashamail.backend.EmailBackend",
        api_key=args.api_key,
        api_url=args.api_url,
        fail_silently=False,
    )

    tests = [
        ("basic", lambda: send_basic(connection, args.to, args.from_email)),
        (
            "html_headers",
            lambda: send_html_headers(
                connection, args.to, args.from_email, args.reply_to
            ),
        ),
        (
            "attachments_inline",
            lambda: send_attachments_inline(connection, args.to, args.from_email),
        ),
        (
            "merge_template_data",
            lambda: send_merge_and_template_data(connection, args.to, args.from_email),
        ),
        (
            "tracking_esp_extra",
            lambda: send_tracking_and_esp_extra(connection, args.to, args.from_email),
        ),
    ]

    if not args.skip_scheduled:
        tests.append(
            ("scheduled", lambda: send_scheduled(connection, args.to, args.from_email))
        )

    failures = 0
    for name, fn in tests:
        try:
            print(f"Running: {name}")
            fn()
        except Exception as exc:
            failures += 1
            print(f"\n[{name}] FAILED: {exc}", file=sys.stderr)

    print("\nDone")
    print(f"Passed: {len(tests) - failures}, Failed: {failures}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
