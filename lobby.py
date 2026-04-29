import http.server
import socketserver
import subprocess
import urllib.parse
import socket
import time
import os

# --- CONFIGURAÇÕES ---
PORTA_WEB = 8080      # Porta do site (navegador)
PORTA_INICIAL = 50000 # Porta dos chats
MAX_GRUPOS = 40       # Limite máximo de salas
IP_VPS = "163.176.160.224" # <--- IMPORTANTE: TROQUE PELO SEU IP PÚBLICO

# Armazena salas ativas: {porta: {"pid": 1234, "nome": "Sala 1", "start": time}}
salas_ativas = {}

def verificar_processos():
    """Remove salas da lista se o processo morreu (timeout)"""
    portas_para_remover = []
    for porta, info in salas_ativas.items():
        # Verifica se o processo (PID) ainda existe
        if subprocess.call(f"kill -0 {info['pid']} 2>/dev/null", shell=True) != 0:
            portas_para_remover.append(porta)
    
    for porta in portas_para_remover:
        print(f"♻️ Sala na porta {porta} fechou (Inatividade). Liberando vaga...")
        del salas_ativas[porta]

def encontrar_porta_livre():
    """Busca uma porta livre entre 50000 e 50039"""
    for i in range(MAX_GRUPOS):
        porta = PORTA_INICIAL + i
        if porta not in salas_ativas:
            # Verifica se a porta está realmente livre no sistema
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('127.0.0.1', porta))
            sock.close()
            if result != 0: # 0 significa que está ocupada
                return porta
    return None

class LobbyHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        verificar_processos()
        
        # Se usuário clicou em "Criar Sala"
        if "criar=" in self.path:
            if len(salas_ativas) >= MAX_GRUPOS:
                self.responder_erro("⚠️ Limite de salas atingido (40/40)! Aguarde uma sala fechar.")
                return

            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            nome_sala = params.get("criar", ["Sala Nova"])[0]
            senha_sala = params.get("senha", [""])[0]
            
            porta_livre = encontrar_porta_livre()
            
            if porta_livre:
                # Lança o servidor_master.py em background
                cmd = f"nohup python3 servidor_master.py {porta_livre} '{nome_sala}' '{senha_sala}' > /dev/null 2>&1 & echo $!"
                pid = subprocess.check_output(cmd, shell=True).decode().strip()
                
                salas_ativas[porta_livre] = {"pid": pid, "nome": nome_sala, "privada": bool(senha_sala)}
                
                # Redireciona de volta para a home
                self.send_response(303)
                self.send_header('Location', '/')
                self.end_headers()
                return

        # Renderiza a página HTML
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Lobby de Chats</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{ background: #1a1a1a; color: #fff; font-family: sans-serif; text-align: center; padding: 20px; }}
                .container {{ max_width: 800px; margin: auto; }}
                .stats {{ background: #333; padding: 10px; border-radius: 8px; margin-bottom: 20px; }}
                .sala {{ background: #2d2d2d; border-left: 5px solid #00ff00; margin: 10px 0; padding: 15px; text-align: left; display: flex; justify-content: space-between; align-items: center; }}
                .sala.privada {{ border-color: #ffcc00; }}
                .btn {{ background: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; border: none; cursor: pointer; font-size: 16px; }}
                .btn:hover {{ background: #0056b3; }}
                input {{ padding: 10px; border-radius: 5px; border: none; }}
                .full {{ color: #ff4444; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>💬 Lobby de Servidores</h1>
                <div class="stats">
                    Salas Ativas: <b>{len(salas_ativas)} / {MAX_GRUPOS}</b>
                    <br><small>Salas inativas por 10min são fechadas automaticamente.</small>
                </div>

                <div style="background: #333; padding: 20px; border-radius: 10px; margin-bottom: 30px;">
                    <h3>Criar Nova Sala</h3>
                    <form action="/" method="GET">
                        <input type="text" name="criar" placeholder="Nome da Sala" required>
                        <input type="text" name="senha" placeholder="Senha (Opcional)">
                        <button type="submit" class="btn">Criar +</button>
                    </form>
                </div>

                <h2>Salas Disponíveis</h2>
                {self.gerar_lista_salas()}
            </div>
        </body>
        </html>
        """
        self.wfile.write(html.encode())

    def gerar_lista_salas(self):
        if not salas_ativas:
            return "<p>Nenhuma sala ativa. Crie a primeira!</p>"
        
        lista = ""
        for porta, info in sorted(salas_ativas.items()):
            lock_icon = "🔒" if info['privada'] else "🌍"
            lista += f"""
            <div class="sala {'privada' if info['privada'] else ''}">
                <div>
                    <strong>{lock_icon} {info['nome']}</strong>
                    <br><small>IP: {IP_VPS} | Porta: {porta}</small>
                </div>
                <div style="background: #000; padding: 5px 10px; border-radius: 4px;">
                    {porta}
                </div>
            </div>
            """
        return lista

    def responder_erro(self, msg):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(f"<h1>Erro</h1><p>{msg}</p><a href='/'>Voltar</a>".encode())

print(f"🔥 Lobby rodando na porta {PORTA_WEB}")
http.server.HTTPServer(('0.0.0.0', PORTA_WEB), LobbyHandler).serve_forever()