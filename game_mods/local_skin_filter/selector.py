# -*- coding: utf-8 -*-
"""Development preview server. Not included in the installed Gameface mod."""
from __future__ import unicode_literals
import binascii,json,os,threading
try:
    from BaseHTTPServer import HTTPServer,BaseHTTPRequestHandler
    from SocketServer import ThreadingMixIn
    from urlparse import urlsplit
except ImportError:
    from http.server import HTTPServer,BaseHTTPRequestHandler
    from socketserver import ThreadingMixIn
    from urllib.parse import urlsplit


class LocalServer(ThreadingMixIn,HTTPServer):
    daemon_threads=True
    allow_reuse_address=False


class PanelServer(object):
    def __init__(self,submit,html=None):
        if html is None:
            try:
                from .panel_assets import HTML
                html=HTML
            except ImportError:
                with open(os.path.join(os.path.dirname(__file__),'selector.html'),'rb')as f:html=f.read()
        self.html=html;self.submit=submit;self.lock=threading.Lock();self.ticket=0
        self.token=binascii.hexlify(os.urandom(32)).decode('ascii')
        self.state=json.dumps(dict(loading=True,cars=[],rules={},revision=0)).encode('utf-8')
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def reply(self,status,data,kind='application/json; charset=utf-8'):
                self.send_response(status);self.send_header('Content-Type',kind)
                self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store')
                self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
                self.end_headers();self.wfile.write(data)
            def valid_host(self):return self.headers.get('Host')=='127.0.0.1:'+str(owner.server.server_port)
            def authorized(self):
                origin=self.headers.get('Origin')
                return self.valid_host()and self.headers.get('X-LSF-Key')==owner.token and(origin is None or origin==owner.origin)
            def do_GET(self):
                if not self.valid_host():self.reply(403,b'{}');return
                route=urlsplit(self.path).path
                if route=='/':self.reply(200,owner.html,'text/html; charset=utf-8')
                elif route=='/api/state'and self.authorized():
                    with owner.lock:data=owner.state
                    self.reply(200,data)
                else:self.reply(403,b'{}')
            def do_POST(self):
                if not self.authorized()or urlsplit(self.path).path!='/api/command':self.reply(403,b'{}');return
                try:
                    count=int(self.headers.get('Content-Length','0'))
                    if not 0<count<=256*1024:raise ValueError('size')
                    value=json.loads(self.rfile.read(count).decode('utf-8'))
                    if not isinstance(value,dict):raise ValueError('command')
                    with owner.lock:owner.ticket+=1;ticket=owner.ticket
                    owner.submit(ticket,value)
                    self.reply(202,json.dumps(dict(ticket=ticket)).encode('utf-8'))
                except (ValueError,TypeError):self.reply(400,b'{}')
        self.server=LocalServer(('127.0.0.1',0),Handler)
        self.origin='http://127.0.0.1:'+str(self.server.server_port)
        # Native BrowserController may append its own params after the fragment.
        # The page takes the fixed-length local nonce; no game params are logged.
        self.url=self.origin+'/?view=selector#'+self.token
        self.thread=threading.Thread(target=lambda:self.server.serve_forever(poll_interval=0.1))
        self.thread.daemon=True;self.thread.start()

    def update(self,state):
        data=json.dumps(state,ensure_ascii=True).encode('utf-8')
        with self.lock:self.state=data

    def stop(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2)
