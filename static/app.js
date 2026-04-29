/* ============================================================
   app.js — Nexus Chat Frontend
   Corrigido e expandido:
   - Autenticação via /api/login e /api/register
   - message.id em vez de message.message_id
   - delete_message emitido corretamente
   - logout usa socket.emit('logout')
   - vote_update (em vez de vote_started)
   - Typing indicator
   - Sala com descrição
   - /clear, /ban, /roomdesc nos atalhos de admin
   ============================================================ */

lucide.createIcons();
const socket = io();

// ── Estado global ──────────────────────────────────────────────────────────
let myUser    = "";
let myRole    = "guest";
let myIsAdmin = false;
let myAvatar  = "👤";
let currentRoom   = "";
let allRooms      = [];
let pendingAction = "";
let isRoomOwner   = false;
let privateMessagesEnabled = true;
let voteTimer    = null;
let voteTimeLeft = 60;
let guestWarningTimeout = null;
let replyingTo   = null;
let votedInCurrentPoll = false;
let typingTimeout = null;

// ── Emoji data ──────────────────────────────────────────────────────────────
const emojis = {
    "😊":":)", "😢":":(", "😄":":D", "😛":":P", "😉":";)",
    "😮":":O", "😐":":|", "😘":":*", "❤":"<3",  "💔":"</3",
    "👍":":+1", "👎":":-1", "🔥":":fire:", "💯":":100:",
    "👌":":ok:", "👏":":clap:", "🙏":":pray:", "🤔":":think:",
    "😆":":D", "🤣":":rofl:", "😎":"B)", "😍":":heart:",
    "🚀":":rocket:", "💎":":gem:", "👑":":crown:", "⭐":":star:",
    "⚡":":zap:", "💥":":boom:", "🎉":":tada:", "🎊":":confetti:"
};

// ── View helpers ────────────────────────────────────────────────────────────
function switchView(id) {
    ["view-landing","view-auth","view-lobby","view-chat"].forEach(v =>
        document.getElementById(v).classList.add("hidden")
    );
    document.getElementById(id).classList.remove("hidden");
}

function goToAuth(action) {
    pendingAction = action;
    switchView("view-auth");
}

function toggleSidebar() {
    const sb = document.getElementById("chat-sidebar");
    const ov = document.getElementById("sidebar-overlay");
    sb.classList.toggle("open");
    ov.classList.toggle("hidden");
}

function openModal() {
    document.getElementById("modal").classList.remove("hidden");
}

function showCommands() {
    document.getElementById("commands-modal").classList.remove("hidden");
}

function showToast(msg, type = "info") {
    const t  = document.createElement("div");
    const color = type === "error"   ? "border-red-500 text-red-400" :
                  type === "warning" ? "border-yellow-500 text-yellow-400" :
                  type === "success" ? "border-green-500 text-green-400" :
                                       "border-primary text-primary";
    const icon  = type === "error"   ? "alert-circle" :
                  type === "warning" ? "alert-triangle" : "info";
    t.className = `glass border ${color} px-4 py-3 rounded-lg shadow-2xl font-mono text-xs flex items-center gap-2 transition-all duration-300`;
    t.innerHTML = `<i data-lucide="${icon}" class="w-4 h-4"></i> ${msg}`;
    document.getElementById("toast-container").appendChild(t);
    lucide.createIcons();
    setTimeout(() => t.remove(), 3500);
}

function showGuestWarning(msg, duration = 10000) {
    const existing = document.getElementById("guest-warning-banner");
    if (existing) existing.remove();
    if (guestWarningTimeout) clearTimeout(guestWarningTimeout);
    const banner = document.createElement("div");
    banner.id = "guest-warning-banner";
    banner.className = "warning-banner";
    banner.innerHTML = `<div class="flex items-center gap-3">
        <i data-lucide="alert-triangle" class="w-5 h-5"></i>
        <span class="font-bold">${msg}</span></div>`;
    document.body.appendChild(banner);
    lucide.createIcons();
    guestWarningTimeout = setTimeout(() => banner.remove(), duration);
}

// ── Emoji picker ─────────────────────────────────────────────────────────────
function toggleEmojiPicker() {
    const picker = document.getElementById("emoji-picker");
    if (picker.classList.contains("hidden")) {
        if (!document.getElementById("emoji-container").children.length) loadEmojis();
        picker.classList.remove("hidden");
    } else {
        picker.classList.add("hidden");
    }
}

function loadEmojis() {
    const c = document.getElementById("emoji-container");
    c.innerHTML = "";
    for (const [emoji, code] of Object.entries(emojis)) {
        const btn = document.createElement("button");
        btn.className = "emoji-btn";
        btn.textContent = emoji;
        btn.title = code;
        btn.onclick = () => {
            const inp = document.getElementById("msg-in");
            inp.value += emoji;
            inp.focus();
        };
        c.appendChild(btn);
    }
}

// ── Reply ────────────────────────────────────────────────────────────────────
function showReply(msgId, username, text) {
    replyingTo = { id: msgId, user: username, text: text };
    const preview = document.getElementById("reply-preview");
    preview.innerHTML = `
        <div class="flex justify-between items-center">
            <div class="flex-1">
                <div class="text-xs text-primary font-bold">↪️ Respondendo a ${username}</div>
                <div class="text-xs text-slate-300 truncate">${text.substring(0, 50)}${text.length > 50 ? "…" : ""}</div>
            </div>
            <button onclick="cancelReply()" class="text-slate-400 hover:text-white ml-2">
                <i data-lucide="x" class="w-4 h-4"></i>
            </button>
        </div>`;
    preview.classList.remove("hidden");
    lucide.createIcons();
    document.getElementById("msg-in").focus();
}

function cancelReply() {
    replyingTo = null;
    document.getElementById("reply-preview").classList.add("hidden");
}

// ── Auth ─────────────────────────────────────────────────────────────────────
function enterGuest() {
    socket.emit("join_guest", {});
}

async function apiAuth(type) {
    const u = document.getElementById("auth-user").value.trim();
    const p = document.getElementById("auth-pass").value;
    if (!u || !p) return showToast("Preencha todos os campos", "error");

    try {
        const res  = await fetch(`/api/${type}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username: u, password: p }),
        });
        const data = await res.json();
        if (data.success) {
            myUser    = data.username || u;
            myIsAdmin = data.is_admin || false;
            myRole    = myIsAdmin ? "admin" : "user";
            myAvatar  = data.avatar || "👤";
            socket.emit("join_auth", { username: myUser });
        } else {
            showToast(data.msg, "error");
        }
    } catch (e) {
        showToast("Erro de conexão", "error");
        console.error(e);
    }
}

// ── Room helpers ─────────────────────────────────────────────────────────────
function createRoom() {
    const n    = document.getElementById("new-room").value.trim();
    const p    = document.getElementById("new-pass").value;
    const desc = document.getElementById("new-desc") ? document.getElementById("new-desc").value.trim() : "";
    if (!n) return showToast("Nome da sala é obrigatório", "error");

    socket.emit("create_room", { name: n, password: p, description: desc });
}

function join(name, isPriv) {
    let p = "";
    if (isPriv) {
        p = prompt("🔒 Senha da sala:");
        if (p === null) return;
    }
    socket.emit("join_room", { name, password: p });
}

function leaveRoom() {
    if (!confirm("Sair da sala?")) return;
    cancelReply();
    socket.emit("logout");
    switchView("view-lobby");
}

function filterRooms() {
    const term = document.getElementById("room-search").value.toLowerCase();
    const filtered = allRooms.filter(r => r.name.toLowerCase().includes(term));
    renderRoomList(filtered);
}

function renderRoomList(rooms) {
    const list = document.getElementById("room-list-container");
    list.innerHTML = "";

    if (!rooms.length) {
        list.innerHTML = `<div class="col-span-3 text-center text-slate-500 py-10">
            <i data-lucide="server-off" class="w-12 h-12 mx-auto mb-4 opacity-50"></i>
            <p class="text-sm">Nenhum servidor encontrado.</p>
            <p class="text-xs mt-2">Crie um servidor clicando em CRIAR</p></div>`;
        lucide.createIcons();
        return;
    }

    rooms.forEach(r => {
        const icon  = r.private ? "lock" : "globe";
        const color = r.private ? "text-secondary" : "text-primary";
        const pct   = Math.min((r.users / r.max) * 100, 100);
        const uc    = pct > 80 ? "text-red-400" : pct > 50 ? "text-yellow-400" : "text-primary";

        const el = document.createElement("div");
        el.className = "glass p-5 rounded-xl border border-white/5 hover:border-primary/30 transition cursor-pointer group";
        el.onclick = () => join(r.name, r.private);
        el.innerHTML = `
            <div class="flex justify-between items-start mb-4">
                <div class="w-10 h-10 rounded-lg bg-[#0a0b10] flex items-center justify-center ${color}">
                    <i data-lucide="${icon}" class="w-5 h-5"></i>
                </div>
                <div class="flex flex-col items-end">
                    <div class="bg-[#0a0b10] px-2 py-1 rounded text-[10px] font-mono ${uc} border border-white/5">${r.users}/${r.max}</div>
                    <div class="text-[9px] text-slate-500 mt-1">${r.last_activity}</div>
                </div>
            </div>
            <h3 class="font-bold text-white text-lg mb-1 truncate">${r.name}</h3>
            ${r.description ? `<p class="text-[11px] text-slate-400 mb-1 truncate">${r.description}</p>` : ""}
            <div class="w-full bg-slate-800 rounded-full h-1.5 mb-2">
                <div class="bg-primary h-1.5 rounded-full" style="width:${pct}%"></div>
            </div>
            <p class="text-xs text-slate-500 mb-3">${r.private ? "🔒 Sala privada" : "🌐 Sala pública"}</p>
            <button class="mt-2 w-full py-2 bg-[#0a0b10] border border-slate-700 text-slate-300 hover:text-white rounded-lg text-xs font-bold font-mono transition group-hover:border-primary/50">
                CONECTAR
            </button>`;
        list.appendChild(el);
    });

    lucide.createIcons();
}

// ── Messages ─────────────────────────────────────────────────────────────────
function sendMsg() {
    const inp = document.getElementById("msg-in");
    const msg = inp.value.trim();
    if (!msg) return;

    const payload = { message: msg };
    if (replyingTo) {
        payload.reply_to = replyingTo;
        cancelReply();
    }

    socket.emit("send_message", payload);
    inp.value = "";
    inp.focus();

    // Para o typing indicator
    socket.emit("typing_stop", {});
    clearTimeout(typingTimeout);
}

// Tecla Enter envia; Shift+Enter nova linha
document.getElementById("msg-in").addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMsg();
    }
});

// Typing indicator
document.getElementById("msg-in").addEventListener("input", () => {
    socket.emit("typing_start", {});
    clearTimeout(typingTimeout);
    typingTimeout = setTimeout(() => socket.emit("typing_stop", {}), 2500);
});

// ── Deletar mensagem ─────────────────────────────────────────────────────────
function deleteMessage(messageId) {
    if (!messageId) return;
    if (!confirm("Deletar esta mensagem?")) return;
    // Emissão correta — não usa send_message
    socket.emit("delete_message", { message_id: messageId });
}

// ── File upload ───────────────────────────────────────────────────────────────
function sendFile() {
    const fi = document.getElementById("file-in");
    const f  = fi.files[0];
    if (!f) return;

    if (f.size > 500 * 1024 * 1024) {
        showToast("Arquivo muito grande (máx. 500 MB)", "error");
        fi.value = "";
        return;
    }
    if (f.size > 100 * 1024 * 1024) showToast("Arquivo grande, enviando…", "info");

    const reader = new FileReader();
    reader.onload  = e => {
        socket.emit("upload_file", { name: f.name, data: e.target.result, size: f.size, type: f.type });
        showToast("Arquivo enviado!", "success");
    };
    reader.onerror = () => showToast("Erro ao ler arquivo", "error");
    reader.readAsDataURL(f);
    fi.value = "";
}

// ── Gravação de voz ───────────────────────────────────────────────────────────
let mediaRec, chunks = [];

function startRec() {
    document.getElementById("mic-btn").classList.add("recording");
    if (!navigator.mediaDevices?.getUserMedia) return showToast("Gravação não suportada", "error");

    navigator.mediaDevices.getUserMedia({ audio: true }).then(s => {
        mediaRec = new MediaRecorder(s, { mimeType: "audio/webm" });
        mediaRec.start();
        chunks = [];
        mediaRec.ondataavailable = e => chunks.push(e.data);
        mediaRec.onstop = () => {
            const blob   = new Blob(chunks, { type: "audio/webm" });
            const reader = new FileReader();
            reader.readAsDataURL(blob);
            reader.onloadend = () => {
                socket.emit("upload_file", { name: "audio.webm", data: reader.result, size: blob.size, type: "audio/webm" });
            };
        };
    }).catch(() => showToast("Acesso ao microfone negado", "error"));
}

function stopRec() {
    document.getElementById("mic-btn").classList.remove("recording");
    if (mediaRec?.state === "recording") mediaRec.stop();
}

// ── Votação ───────────────────────────────────────────────────────────────────
function vote(choice) {
    if (votedInCurrentPoll) return showToast("Você já votou!", "warning");
    socket.emit("vote_action", { action: choice });
    votedInCurrentPoll = true;
    document.getElementById(`vote-${choice}-btn`).classList.add("opacity-50", "cursor-not-allowed");
    showToast(`Você votou ${choice === "yes" ? "SIM" : "NÃO"}!`, "success");
}

function startVoteUI(target, action, minutes) {
    const voteDisplay = document.getElementById("vote-active");
    voteDisplay.classList.remove("hidden");
    voteTimeLeft = 60;
    votedInCurrentPoll = false;

    document.getElementById("vote-yes-btn").classList.remove("opacity-50", "cursor-not-allowed");
    document.getElementById("vote-no-btn").classList.remove("opacity-50", "cursor-not-allowed");
    document.getElementById("vote-description").textContent =
        action === "kick"
            ? `Expulsar ${target}`
            : `Mutar ${target} por ${minutes || 10} minutos`;

    clearInterval(voteTimer);
    voteTimer = setInterval(() => {
        voteTimeLeft--;
        document.getElementById("vote-timer").textContent = `${voteTimeLeft}s`;
        if (voteTimeLeft <= 0) {
            clearInterval(voteTimer);
            voteDisplay.classList.add("hidden");
            votedInCurrentPoll = false;
        }
    }, 1000);
}

// ── Render de mensagem ────────────────────────────────────────────────────────
function renderMessage(data) {
    const area   = document.getElementById("messages");
    const isMe   = data.user === myUser;
    const isAdm  = data.role === "admin" || data.user === "SISTEMA";

    // Badge de papel
    const badge =
        data.role === "admin" ? '<span class="badge-admin ml-2">ADMIN</span>' :
        data.role === "owner" ? '<span class="badge-owner ml-2">DONO</span>'  :
        data.role === "user"  ? '<span class="badge-user ml-2">USUÁRIO</span>' :
        data.role === "guest" ? '<span class="badge-guest ml-2">CONVIDADO</span>' : "";

    // Conteúdo extra (mídia)
    let extraContent = "";
    if (data.type === "image")
        extraContent = `<img src="${data.url}" class="rounded-lg max-w-[200px] mt-2 border border-white/10 cursor-pointer" onclick="window.open(this.src,'_blank')">`;
    else if (data.type === "audio")
        extraContent = `<audio controls src="${data.url}" class="mt-2 w-48"></audio>`;
    else if (data.type === "video")
        extraContent = `<video controls src="${data.url}" class="mt-2 w-48 rounded-lg"></video>`;
    else if (data.type === "file")
        extraContent = `<a href="${data.url}" target="_blank" class="flex items-center gap-2 text-primary hover:underline mt-1 text-xs"><i data-lucide="download" class="w-3 h-3"></i> ${data.text}</a>`;

    // Reply preview
    let replyHTML = "";
    if (data.reply_to && typeof data.reply_to === "object") {
        replyHTML = `<div class="msg-reply text-xs text-slate-400 mb-1">
            <div class="font-bold">↪️ ${data.reply_to.user}</div>
            <div class="truncate">${(data.reply_to.text || "").substring(0, 50)}</div></div>`;
    }

    // Botões de ação
    const msgId = data.id || "";
    const canDel = data.can_delete || myIsAdmin || isRoomOwner;
    const replyBtn = `<button onclick="showReply('${msgId}','${(data.user||"").replace(/'/g,"\\'")}','${(data.text||"").replace(/'/g,"\\'").substring(0,30)}')" class="p-1 text-slate-400 hover:text-primary" title="Responder"><i data-lucide="reply" class="w-3 h-3"></i></button>`;
    const delBtn   = canDel ? `<button onclick="deleteMessage(${msgId})" class="p-1 text-slate-400 hover:text-red-500" title="Deletar"><i data-lucide="trash-2" class="w-3 h-3"></i></button>` : "";
    const actionButtons = `<div class="flex gap-1 mt-1">${replyBtn}${delBtn}</div>`;

    const wrapper = document.createElement("div");
    wrapper.className = `flex flex-col ${isMe ? "items-end" : "items-start"} mb-2 animate-fade-in`;
    wrapper.dataset.messageId = msgId;
    wrapper.innerHTML = `
        <div class="flex items-center gap-2 mb-1">
            <span class="text-[10px] text-slate-500 font-mono">${data.user} ${badge}</span>
            <span class="text-[10px] text-slate-700">•</span>
            <span class="text-[10px] text-slate-500">${data.time}</span>
        </div>
        <div class="max-w-[85%] px-3 py-2 text-sm text-white shadow-sm ${isMe ? "msg-me" : isAdm ? "msg-admin" : "msg-other"}">
            ${replyHTML}
            <div class="break-words">${data.text || ""}</div>
            ${extraContent}
            ${actionButtons}
        </div>`;

    area.appendChild(wrapper);
    area.scrollTop = area.scrollHeight;
    lucide.createIcons();
}

// ── PM helpers ────────────────────────────────────────────────────────────────
function startPM(username) {
    const msg = prompt(`Mensagem privada para ${username}:`);
    if (msg?.trim()) socket.emit("send_message", { message: `/pm ${username} ${msg}` });
}

// ── Admin actions ─────────────────────────────────────────────────────────────
function adminAction(action, username) {
    if (!myIsAdmin && !isRoomOwner) return showToast("Sem permissão", "error");

    if (action === "kick") {
        const reason = prompt(`Razão para expulsar ${username}:`, "Violação das regras");
        if (reason !== null) socket.emit("send_message", { message: `/kick ${username} ${reason}` });
    } else if (action === "mute") {
        const min = prompt(`Mutar ${username} por quantos minutos?`, "5");
        if (min !== null && !isNaN(min)) {
            const reason = prompt("Razão:", "Spam");
            if (reason !== null)
                socket.emit("send_message", { message: `/mute ${username} ${min} ${reason}` });
        }
    } else if (action === "ban") {
        const days   = prompt(`Banir ${username} por quantos dias? (0 = permanente)`, "0");
        if (days !== null && !isNaN(days)) {
            const reason = prompt("Razão do banimento:", "Violação grave das regras");
            if (reason !== null)
                socket.emit("send_message", { message: `/ban ${username} ${days} ${reason}` });
        }
    }
}

function togglePrivateMessages() {
    socket.emit("toggle_private_messages", {});
}

// ── Socket Events ─────────────────────────────────────────────────────────────

socket.on("connect", () => {
    console.log("[Nexus] Socket conectado");
    if (myUser) setTimeout(() => socket.emit("join_auth", { username: myUser }), 100);
});

socket.on("login_success", data => {
    myUser    = data.username;
    myRole    = data.role;
    myIsAdmin = data.is_admin || false;
    myAvatar  = data.avatar || "👤";

    document.getElementById("user-display").innerText =
        `${myAvatar} ${data.username}${myIsAdmin ? " [ADMIN]" : ""}`;

    switchView("view-lobby");
    if (pendingAction === "host") setTimeout(openModal, 400);
    showToast(`Bem-vindo, ${data.username}!`, "success");
});

socket.on("room_list", rooms => {
    allRooms = rooms;
    renderRoomList(rooms);
});

socket.on("create_room_result", data => {
    if (data.success) {
        document.getElementById("modal").classList.add("hidden");
        document.getElementById("new-room").value = "";
        document.getElementById("new-pass").value = "";
        showToast(data.msg, "success");
    } else {
        showToast(data.msg, "error");
    }
});

socket.on("joined_room", data => {
    currentRoom = data.name;
    isRoomOwner = data.is_owner || false;

    document.getElementById("room-title").innerText = data.name;
    document.getElementById("room-owner").innerText =
        isRoomOwner ? "👑 Você é o dono" : data.is_admin ? "🛡️ Admin" : "";
    document.getElementById("messages").innerHTML = "";
    cancelReply();
    switchView("view-chat");

    // Descrição da sala
    if (data.description) {
        showToast(`📝 ${data.description}`, "info");
    }

    if (window.innerWidth < 768) {
        document.getElementById("chat-sidebar").classList.remove("open");
        document.getElementById("sidebar-overlay").classList.add("hidden");
    }
    document.getElementById("emoji-picker").classList.add("hidden");
    showToast(`Entrou em ${data.name}`, "success");
});

// Histórico via room_history (array)
socket.on("room_history", history => {
    // Mensagens já foram renderizadas via eventos 'message' individuais
    // Este evento existe para compatibilidade — não re-renderiza
    console.log(`[Nexus] Histórico: ${history.length} mensagens`);
});

socket.on("message", data => {
    if (data.type === "system") {
        const area = document.getElementById("messages");
        const div = document.createElement("div");
        div.className = "msg-system animate-fade-in";
        div.innerHTML = `<div class="flex items-center justify-between">
            <span class="font-mono text-xs">${data.text || data.msg || ""}</span>
            <span class="text-[10px] opacity-70">${data.time || ""}</span></div>`;
        area.appendChild(div);
        area.scrollTop = area.scrollHeight;
    } else {
        renderMessage(data);
    }
});

socket.on("private_message", data => {
    const area      = document.getElementById("messages");
    const isOutgoing = data.from.startsWith("Para ");
    const div = document.createElement("div");
    div.className = "flex justify-center mb-2 animate-fade-in";
    div.innerHTML = `<div class="msg-private px-3 py-2 text-sm shadow-sm">
        <div class="flex items-center gap-2">
            <i data-lucide="${isOutgoing ? "send" : "inbox"}" class="w-3 h-3"></i>
            <span><strong>${data.from}:</strong> ${data.message}</span>
            <span class="text-[9px] opacity-70 ml-2">${data.time}</span>
        </div></div>`;
    area.appendChild(div);
    area.scrollTop = area.scrollHeight;
    lucide.createIcons();
});

socket.on("system_message", data => {
    if (data.type === "system") {
        // Renderizar na área de chat
        const area = document.getElementById("messages");
        if (area) {
            const div = document.createElement("div");
            div.className = "msg-system animate-fade-in";
            div.innerHTML = `<span class="font-mono text-xs">${data.msg}</span>`;
            area.appendChild(div);
            area.scrollTop = area.scrollHeight;
        }
    } else {
        showToast(data.msg, data.type || "info");
    }
});

socket.on("user_list", data => {
    const userList  = document.getElementById("user-list");
    const userCount = document.getElementById("user-count");
    userList.innerHTML = "";
    userCount.textContent = data.count || data.users.length;

    (data.users || []).forEach(username => {
        const isMe    = username === myUser;
        const isGuest = username.startsWith("Guest_");

        const li = document.createElement("li");
        li.className = "flex items-center justify-between p-2 rounded-lg hover:bg-white/5 transition";
        li.innerHTML = `
            <div class="flex items-center gap-2">
                <i data-lucide="${isMe ? "star" : isGuest ? "ghost" : "user"}" class="w-3 h-3 ${isMe ? "text-accent" : isGuest ? "text-slate-500" : "text-primary"}"></i>
                <span class="text-sm ${isMe ? "text-accent font-bold" : "text-white"}">${username}</span>
            </div>
            <div class="flex gap-1">
                ${!isMe ? `
                <button onclick="startPM('${username}')" class="p-1 text-slate-400 hover:text-primary" title="PM">
                    <i data-lucide="message-square" class="w-3 h-3"></i>
                </button>
                ${myIsAdmin || isRoomOwner ? `
                <button onclick="adminAction('kick','${username}')" class="p-1 text-slate-400 hover:text-red-500" title="Expulsar">
                    <i data-lucide="user-x" class="w-3 h-3"></i>
                </button>
                <button onclick="adminAction('mute','${username}')" class="p-1 text-slate-400 hover:text-yellow-500" title="Mutar">
                    <i data-lucide="volume-x" class="w-3 h-3"></i>
                </button>
                <button onclick="adminAction('ban','${username}')" class="p-1 text-slate-400 hover:text-red-700" title="Banir">
                    <i data-lucide="ban" class="w-3 h-3"></i>
                </button>` : ""}` : ""}
            </div>`;
        userList.appendChild(li);
    });
    lucide.createIcons();
});

socket.on("message_deleted", data => {
    // Usa message_id (campo enviado pelo servidor) para localizar o elemento
    const id = data.message_id;
    const el = document.querySelector(`[data-message-id="${id}"]`);
    if (el) {
        el.innerHTML = `<div class="text-center text-slate-500 italic text-sm py-2">
            <i data-lucide="trash-2" class="w-4 h-4 inline mr-1"></i>
            Mensagem deletada por ${data.deleted_by}</div>`;
        lucide.createIcons();
    }
});

// Limpar chat inteiro (comando /clear)
socket.on("clear_chat", () => {
    const area = document.getElementById("messages");
    if (area) area.innerHTML = "";
    showToast("🗑️ Chat limpo pelo administrador", "warning");
});

// Descrição de sala atualizada (comando /roomdesc)
socket.on("room_desc_updated", data => {
    showToast(`📝 Descrição: ${data.description}`, "info");
});

// vote_update — unifica vote_started e result
socket.on("vote_update", data => {
    if (data.type === "start") {
        startVoteUI(data.target, data.action, data.minutes);
    } else if (data.type === "result") {
        clearInterval(voteTimer);
        document.getElementById("vote-active").classList.add("hidden");
        votedInCurrentPoll = false;
        showToast(data.result, data.success ? "success" : "warning");
    }
});

// Typing indicator
socket.on("typing_update", data => {
    const others = (data.users || []).filter(u => u !== myUser);
    const el = document.getElementById("typing-indicator");
    if (!el) return;
    if (others.length === 0) {
        el.classList.add("hidden");
    } else {
        el.classList.remove("hidden");
        el.textContent = others.length === 1
            ? `${others[0]} está digitando…`
            : `${others.slice(0, 3).join(", ")} estão digitando…`;
    }
});

socket.on("error",       d => showToast(d.msg, "error"));
socket.on("guest_warning", d => showGuestWarning(d.msg, d.time * 1000));
socket.on("room_warning",  d => showToast(d.msg, "warning"));
socket.on("left_room",     ()  => switchView("view-lobby"));

socket.on("force_kick", data => {
    showToast(`Você foi expulso: ${data.reason}`, "error");
    setTimeout(() => switchView("view-landing"), 2000);
});

// ── Init ──────────────────────────────────────────────────────────────────────
loadEmojis();

document.addEventListener("DOMContentLoaded", () => {
    const inp = document.getElementById("msg-in");
    if (inp) {
        inp.addEventListener("focus", () =>
            document.getElementById("emoji-picker").classList.add("hidden")
        );
    }
});