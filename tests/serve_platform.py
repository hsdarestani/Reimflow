"""HTTP server serving current frontend and isolated real platform API to browser tests."""
import os
import tempfile
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import platform_api
import api

temp=tempfile.TemporaryDirectory()
platform_api.DATABASE=str(Path(temp.name)/"browser.sqlite")
platform_api.MEDIA_DIR=Path(temp.name)/"media"
platform_api.initialize()
os.environ["REIMFLOW_DEV_ORIGIN"]="http://127.0.0.1:8186"

class BrowserTestHandler(api.Handler,SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/"):
            return api.Handler.do_GET(self)
        return SimpleHTTPRequestHandler.do_GET(self)

if __name__=="__main__":
    server=ThreadingHTTPServer(("127.0.0.1",8186),BrowserTestHandler)
    try:server.serve_forever()
    finally:
        server.server_close()
        temp.cleanup()
