#!/usr/bin/env python3
"""
Demo server: serves poc9.html with chapter1 pre-loaded.
Usage: python3 demo.py [port]   (default port: 8080)
Requires cloudflared for the public URL: yay -S cloudflared
"""
import http.server
import pathlib
import re
import socket
import subprocess
import sys
import threading

ROOT = pathlib.Path(__file__).parent

# Explicit allowlist — nothing else is ever served
STATIC = {
    '/chapter1.js': (ROOT / 'example-data' / 'chapter1_ver4.js', 'application/javascript; charset=utf-8'),
    '/charstats.js': (ROOT / 'charstats.js', 'application/javascript; charset=utf-8'),
}

POC9 = ROOT / 'poc9.html'


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ('/', '/poc9.html'):
            html = POC9.read_bytes()
            html = html.replace(b'</head>', b'<script src="/chapter1.js"></script>\n</head>', 1)
            html = html.replace(
                b'</body>',
                b'<script>if(window.CHAPTER1)initReader(window.CHAPTER1);</script>\n</body>',
                1,
            )
            self._send(200, 'text/html; charset=utf-8', html)
        elif self.path in STATIC:
            path, ctype = STATIC[self.path]
            self._send(200, ctype, path.read_bytes())
        else:
            self._send(404, 'text/plain; charset=utf-8', b'Not found\n')

    def _send(self, code, content_type, body):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f'  {self.address_string()}  {fmt % args}')


def local_ip():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]

def start_tunnel(port):
    try:
        proc = subprocess.Popen(
            ['cloudflared', 'tunnel', '--url', f'http://localhost:{port}'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        for line in proc.stdout:
            m = re.search(r'https://\S+\.trycloudflare\.com', line)
            if m:
                print(f'Public:   {m.group()}')
                return
    except FileNotFoundError:
        print('Public:   (install cloudflared for a public URL: yay -S cloudflared)')


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    server = http.server.HTTPServer(('0.0.0.0', port), Handler)
    print(f'Local:    http://{local_ip()}:{port}')
    threading.Thread(target=start_tunnel, args=(port,), daemon=True).start()
    print(f'Allowed:  /, /poc9.html, /chapter1.js, /charstats.js')
    server.serve_forever()
