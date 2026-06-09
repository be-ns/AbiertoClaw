"""Driver interface (SPEC §4.2).

Driver.chat(messages, model, opts) -> {"text": str, "usage": dict}
Driver.list_models() -> [{"id": ..., ...}]

Raises RateLimited on 429 so the engine can rotate to the next candidate,
and ProviderError for everything else that went wrong upstream.
"""

import json
import urllib.error
import urllib.parse
import urllib.request


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Never carry the API key across hosts.

    The stdlib handler copies every header — including Authorization — onto
    the redirected request, so a compromised provider (or an open redirect on
    one) could bounce the call to a host it controls and capture the key.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and (urllib.parse.urlsplit(new.full_url).netloc
                                != urllib.parse.urlsplit(req.full_url).netloc):
            new.remove_header("Authorization")
        return new


_opener = urllib.request.build_opener(_SafeRedirectHandler())


class RateLimited(Exception):
    def __init__(self, message, retry_after=None):
        super().__init__(message)
        self.retry_after = retry_after


class ProviderError(Exception):
    pass


class Driver:
    def chat(self, messages, model, opts=None):
        raise NotImplementedError

    def list_models(self):
        raise NotImplementedError

    # -- shared HTTP plumbing (stdlib only; no dependencies) -----------------

    @staticmethod
    def _request(url, payload=None, headers=None, timeout=120):
        """POST json (or GET when payload is None). Returns the parsed body."""
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, headers=headers or {})
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with _opener.open(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode()[:500]
            except Exception:
                pass
            if e.code == 429:
                retry_after = e.headers.get("Retry-After")
                raise RateLimited(
                    "rate limited by %s" % url,
                    retry_after=float(retry_after) if retry_after else None,
                )
            raise ProviderError("HTTP %s from %s: %s" % (e.code, url, body))
        except urllib.error.URLError as e:
            raise ProviderError("cannot reach %s: %s" % (url, e.reason))
        except json.JSONDecodeError:
            raise ProviderError("non-JSON response from %s" % url)
