"""A small OpenAI-compatible server on this machine, for tests. Standard library only.

It answers GET /v1/models and POST /v1/chat/completions, records the Authorization header
it was sent, and can be told to echo that header back, to refuse, or to repeat the canary
codes a private lane plants.
"""
import http.server
import json
import re
import threading

LONG = "A substantive objection: the proposal assumes demand that nothing in the packet shows. " * 4


class Fake:
    def __init__(self, model="other/model-1", key=None, echo_auth=False, canaries=False, status=200):
        self.model, self.key, self.echo_auth, self.canaries, self.status = model, key, echo_auth, canaries, status
        self.seen_auth = []
        fake = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def reply(self, code, data):
                b = json.dumps(data).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def gate(self):
                auth = self.headers.get("Authorization", "")
                fake.seen_auth.append(auth)
                if fake.status != 200:
                    self.reply(fake.status, {"error": {"message": "refused, you sent " + auth}})
                    return False
                if fake.key and auth != "Bearer " + fake.key:
                    self.reply(401, {"error": {"message": "bad key " + auth}})
                    return False
                return True

            def do_GET(self):
                if self.path.rstrip("/") != "/v1/models":
                    return self.reply(404, {"error": "no"})
                if self.gate():
                    self.reply(200, {"data": [{"id": fake.model}]})

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                if self.path.rstrip("/") != "/v1/chat/completions":
                    return self.reply(404, {"error": "no"})
                if not self.gate():
                    return
                text = LONG
                if fake.echo_auth:
                    text += "\nYou sent: " + self.headers.get("Authorization", "")
                if fake.canaries:
                    prompt = " ".join(m.get("content", "") for m in body.get("messages", []))
                    codes = re.findall(r"CANARY-[AB]: [0-9a-f]+", prompt)
                    text = (codes[0] + "\n" if codes else "") + text + ("\n" + codes[-1] if codes else "")
                self.reply(200, {"choices": [{"message": {"content": text}}]})

        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}/v1"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()
