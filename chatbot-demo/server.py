from http.server import HTTPServer, SimpleHTTPRequestHandler
import json
import urllib.request

class Handler(SimpleHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers['Content-Length'])
        data = json.loads(self.rfile.read(length))
        msg = data['message']
        key = data['key']

        url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}'
        req = urllib.request.Request(url, method='POST')
        req.add_header('Content-Type', 'application/json')
        body = json.dumps({
            'contents': [{'parts': [{'text': msg}]}],
            'systemInstruction': {'parts': [{'text': 'You are a friendly business assistant. Keep answers to 2-3 sentences.'}]}
        })

        res = urllib.request.urlopen(req, body.encode())
        result = json.loads(res.read())
        reply = result['candidates'][0]['content']['parts'][0]['text']

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'reply': reply}).encode())

HTTPServer(('', 8080), Handler).serve_forever()
