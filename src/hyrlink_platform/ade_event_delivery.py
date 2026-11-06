"""Bounded tenant event delivery to an operator-approved HTTPS endpoint.

An event ID is an idempotency key, not proof of exactly-once delivery. Remote
consumers must authenticate the sender, validate tenant authorization and dedupe
events. A failed acknowledgment leaves the outbox lease to expire for replay.
"""

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request

from .contracts import PlatformError
from .runtime import Principal


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HTTPSDelivery:
    """Destination and credentials must come from trusted server configuration."""

    def __init__(self, endpoint, allowed_hosts, bearer_token, *, ssl_context=None, timeout=5):
        if (not isinstance(endpoint, str) or not isinstance(bearer_token, str)
                or not isinstance(allowed_hosts, frozenset) or not allowed_hosts
                or any(not isinstance(host, str) or host != host.lower() for host in allowed_hosts)):
            raise ValueError("invalid_delivery_configuration")
        try:
            parsed = urllib.parse.urlsplit(endpoint)
            host = parsed.hostname
            port = parsed.port
        except ValueError:
            raise ValueError("invalid_delivery_configuration") from None
        if (parsed.scheme != "https" or not host or not host.isascii() or host not in allowed_hosts
                or parsed.username is not None or parsed.password is not None or parsed.fragment or parsed.query
                or not parsed.path.startswith("/") or (port is not None and not 1 <= port <= 65535)
                or not bearer_token or len(bearer_token) > 4096
                or any(ord(c) < 33 or ord(c) > 126 for c in bearer_token)
                or not 0 < timeout <= 10):
            raise ValueError("invalid_delivery_configuration")
        context = ssl_context or ssl.create_default_context()
        if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
            raise ValueError("tls_verification_required")
        self._endpoint, self._token, self._timeout = endpoint, bearer_token, timeout
        self._opener = urllib.request.build_opener(_NoRedirect(), urllib.request.HTTPSHandler(context=context))

    def deliver(self, tenant, event):
        body = json.dumps({"tenant_id": tenant, "event_id": str(event["event_id"]),
                           "record_id": str(event["record_id"]), "event_type": event["event_type"]},
                          separators=(",", ":")).encode("utf-8")
        if len(body) > 8192:
            raise PlatformError("delivery_failed")
        request = urllib.request.Request(
            self._endpoint, data=body, method="POST",
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + self._token,
                     "Idempotency-Key": str(event["event_id"])},
        )
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                if not 200 <= response.status < 300:
                    raise ValueError("delivery_not_accepted")
        except (OSError, ValueError, urllib.error.URLError):
            raise PlatformError("delivery_failed") from None


def deliver_batch(outbox, principal, sink, *, limit=10, lease_seconds=120):
    """Claim once, deliver to one fixed sink, and leave uncertain acknowledgments leased."""
    if not isinstance(principal, Principal) or "platform:outbox-dispatch" not in principal.permissions:
        raise PlatformError("permission_denied")
    # Ensure the lease can outlive the maximum serial network budget.
    if not isinstance(sink, HTTPSDelivery) or type(limit) is not int or type(lease_seconds) is not int:
        raise PlatformError("invalid_delivery_configuration")
    if not 1 <= limit <= 50 or not 1 <= lease_seconds <= 300 or lease_seconds <= limit * sink._timeout:
        raise PlatformError("invalid_delivery_configuration")
    events = outbox.claim(principal, limit=limit, lease_seconds=lease_seconds)
    result = {"claimed": len(events), "delivered": 0, "retry_scheduled": 0, "uncertain": 0}
    for event in events:
        try:
            sink.deliver(principal.tenant, event)
        except PlatformError:
            delay = min(300, 2 ** min(event["attempt"], 8))
            try:
                outbox.retry(principal, event["event_id"], event["lease_id"], delay)
                result["retry_scheduled"] += 1
            except Exception:
                result["uncertain"] += 1
            continue
        try:
            outbox.complete(principal, event["event_id"], event["lease_id"])
            result["delivered"] += 1
        except Exception:
            # The remote side may have committed. Do not issue a second send here.
            result["uncertain"] += 1
    return result
