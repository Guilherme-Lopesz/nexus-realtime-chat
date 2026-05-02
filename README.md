# Nexus Chat — Real-time Chat com Governança Distribuída


https://github.com/user-attachments/assets/1b275feb-8bf4-450c-8f52-fe8c82268bb0


Plataforma de comunicação em tempo real projetada para escalabilidade, com moderação comunitária, sistema anti-spam multicamada e gerenciamento inteligente de recursos.

---

## 🎯 O Problema

Sistemas de chat tradicionais apresentam limitações recorrentes que impactam diretamente a experiência e a escalabilidade:

- **Spam e abuso**: bots e usuários maliciosos comprometem a qualidade da interação
- **Moderação centralizada**: dependência de administradores para ações críticas
- **Salas inativas**: consumo desnecessário de recursos por ambientes ociosos
- **Baixa participação do usuário**: ausência de mecanismos de governança coletiva

## ✨ A Solução

O Nexus aborda esses desafios com uma arquitetura orientada a controle distribuído e automação:

- **Sistema de anti-spam multicamada** (usuário + IP + contexto global)
- **Moderação democrática em tempo real** via votação (votekick / votemute)
- **Gerenciamento automático de salas** com limpeza de recursos ociosos
- **Persistência inteligente** de estado e histórico

---

## 🏗️ Funcionamento (Alto Nível)

```
┌─────────────────────────────────────────────────────┐
│                   Cliente (SPA)                     │
│   HTML5 + Vanilla JS + WebSocket (Socket.IO)        │
└────────────────────┬────────────────────────────────┘
                     │ comunicação em tempo real
                     ↓
┌─────────────────────────────────────────────────────┐
│              Servidor Flask + SocketIO              │
├─────────────────────────────────────────────────────┤
│ • Autenticação segura (bcrypt)                      │
│ • Anti-spam multicamada                            │
│ • Processamento de comandos                        │
│ • Sistema de votação distribuída                   │
│ • Persistência via ORM                             │
└────────────────────┬────────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         ↓                       ↓
    ┌────────────┐        ┌────────────────────┐
    │ Banco SQL  │        │ Estado em Memória  │
    │ (Users,    │        │ (sessions, votos,  │
    │ Messages,  │        │ usuários ativos)   │
    │ Rooms)     │        └────────────────────┘
    └────────────┘
```

---

## 🛠️ Tecnologias Utilizadas

| Camada          | Tecnologia                              |
|-----------------|----------------------------------------|
| **Backend**     | Flask, Flask-SocketIO, SQLAlchemy      |
| **Autenticação**| bcrypt, Flask-Login                    |
| **Banco**       | SQLite (compatível com PostgreSQL/MySQL)|
| **Frontend**    | Vanilla JS, WebSocket, HTML5           |
| **Deploy**      | Compatível com Gunicorn + Nginx        |

---

## 🚀 Como Executar

### Pré-requisitos

- Python 3.10+

### Setup

```bash
git clone <repo-url>
cd NexusV2
pip install -r requirements.txt

# Variáveis opcionais
export SECRET_KEY="sua-chave"
export DATABASE_URL="sqlite:///nexus.db"
export PORT=8080

python app.py
```

**Acesse:** `http://localhost:8080`

---

## 💎 Diferenciais Técnicos

### 1️⃣ Anti-Spam Multicamadas

```
# Rate limit por usuário e IP
# Detecção de padrões de spam
# Mute automático
```

- Mitigação de spam coordenado
- Controle distribuído de requisições
- Proteção contra flood e bots

### 2️⃣ Moderação Democrática com Quórum

```
# votekick / votemute com tempo limite
# maioria simples + quórum mínimo
```

- Redução da dependência de admins
- Decisões auditáveis e transparentes
- Proteção contra abuso em salas pequenas

### 3️⃣ Gerenciamento de Estado em Memória

```
# sincronização em tempo real
# limpeza automática de salas
```

- Redução de carga no banco de dados
- Atualizações com baixa latência
- Estrutura eficiente para múltiplos usuários

### 4️⃣ Persistência e Relacionamentos

```
# ORM com histórico completo
# banimentos com expiração
```

- Rastreabilidade de ações
- Recuperação de histórico
- Estrutura preparada para expansão

### 5️⃣ Arquitetura Modular

```
events.py      → handlers de eventos
commands.py    → parser de comandos
voting.py      → lógica de votação
antispam.py    → controle de spam
state.py       → estado global em memória
```

- Separação clara de responsabilidades
- Facilidade de manutenção e testes
- Extensível para novas funcionalidades

---

## 📚 Aprendizados Relevantes

### Engenharia Aplicada

- Sincronização em tempo real com WebSocket
- Controle de concorrência com locks por sala
- Design híbrido: memória + persistência
- Estrutura modular orientada a eventos

### Problemas Resolvidos

- **Race conditions em votações** → uso de locks para atomicidade
- **Salas ociosas** → limpeza automática baseada em atividade
- **Spam distribuído** → rate limiting por IP + usuário
- **Reconexão de clientes** → recuperação de estado no frontend
- **Sincronização de histórico** → eventos unificados

---

## 🎮 Comandos Disponíveis

### Usuários

- `/pm <user> <msg>` — mensagem privada
- `/votekick <user>` — votação para expulsão
- `/votemute <user>` — votação para silenciamento
- `/togglepm` — ativar/desativar PM
- `/help` — ajuda

### Admin / Dono

- `/kick`, `/mute`, `/ban`, `/clear`

---

## 📁 Estrutura do Projeto

```
NexusV2/
├── app.py
├── models.py
├── state.py
├── events.py
├── commands.py
├── voting.py
├── antispam.py
├── routes.py
├── tasks.py
├── static/
├── templates/
└── uploads/
```

---

## 🔐 Segurança

- ✅ Hash de senhas com bcrypt
- ✅ Proteção contra SQL Injection (ORM)
- ✅ Sanitização de inputs
- ✅ Rate limiting por IP
- ✅ Logs de auditoria

---

## 📊 Performance

- **Latência média:** ~50ms
- **Arquitetura** orientada a baixa latência
- **Uso eficiente** de memória por sessão

---

## 🎓 Para Recrutadores

Este projeto demonstra:

- ✅ Arquitetura backend escalável
- ✅ Sistemas distribuídos em tempo real
- ✅ Resolução de problemas reais (spam, concorrência, moderação)
- ✅ Boas práticas de engenharia (modularidade, organização, segurança)

---

## 📝 Licença

MIT
| `/roomdesc <texto>`             | Admin / Dono         |
| `/broadcast <msg>`              | Apenas Admin global  |
