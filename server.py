"""Local HTTP application. Python 3.10+, no third-party packages."""
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from engine import check_documents
ROOT=Path(__file__).resolve().parent
class Handler(BaseHTTPRequestHandler):
    def respond(self,status,data,mime='application/json; charset=utf-8'):
        b=data.encode('utf-8') if isinstance(data,str) else data
        self.send_response(status)
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(b)))
        self.send_header('Cache-Control','no-store')
        self.end_headers()
        self.wfile.write(b)
    def do_GET(self):
        path=urlsplit(self.path).path
        if path in ('/','/index.html'):
            return self.respond(200,(ROOT/'static'/'index.html').read_bytes(),'text/html; charset=utf-8')
        if path.startswith('/sample/'):
            name=path.removeprefix('/sample/')
            f=ROOT/'samples'/name
            if name.endswith('.txt') and '/' not in name and f.is_file():
                return self.respond(200,f.read_bytes(),'text/plain; charset=utf-8')
        if path=='/health':return self.respond(200,'{"status":"ok"}')
        return self.respond(404,'{"error":"not found"}')
    def do_POST(self):
        if self.path!='/api/check':return self.respond(404,'{"error":"not found"}')
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size<=0 or size>5_000_000:return self.respond(413,'{"error":"Limit 5 MB"}')
            request=json.loads(self.rfile.read(size))
            docs=request.get('documents')
            if not isinstance(docs,list) or not 1<=len(docs)<=100:raise ValueError('Загрузите от 1 до 100 TXT файлов')
            if any(not isinstance(d,dict) or not isinstance(d.get('name'),str) or not d['name'].lower().endswith('.txt') or not isinstance(d.get('text'),str) for d in docs):
                raise ValueError('Принимаются только TXT файлы')
            result=check_documents(docs,request.get('as_of','2026-03-10'))
            return self.respond(200,json.dumps(result,ensure_ascii=False))
        except (ValueError,TypeError,KeyError) as e:
            return self.respond(400,json.dumps({'error':str(e)},ensure_ascii=False))
        except Exception:
            return self.respond(500,'{"error":"Ошибка обработки документов"}')
if __name__=='__main__':
    print('Open http://127.0.0.1:8000')
    ThreadingHTTPServer(('127.0.0.1',8000),Handler).serve_forever()
