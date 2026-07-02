"""Tiny HTTP app whose memory footprint can be grown at runtime.

Endpoints:
    GET /            -> "ok" (readiness / W3SVC-equivalent)
    GET /leak?mb=N   -> allocate N MB and hold it (raises real RSS / cgroup usage)
    GET /free        -> release everything

Used by the approval demo as a target with a *real* memory metric: a restart
drops the held memory back to baseline, so remediation is genuinely observable.
"""

import http.server
import urllib.parse

# Held allocations — kept alive so the process RSS (and cgroup usage) stays high.
_balloon: list[bytearray] = []


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, code: int, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/leak":
            query = urllib.parse.parse_qs(parsed.query)
            megabytes = int(query.get("mb", ["50"])[0])
            _balloon.append(bytearray(megabytes * 1024 * 1024))
            self._send(200, f"allocated {megabytes}MB (chunks={len(_balloon)})")
        elif parsed.path == "/free":
            _balloon.clear()
            self._send(200, "freed")
        else:
            self._send(200, "ok")

    def log_message(self, *args) -> None:  # silence request logging
        return


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
