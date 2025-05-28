let ws;
function connect() {
  const jwt = document.getElementById("jwt").value;
  if (!jwt) {
    alert("Enter JWT token");
    return;
  }
  ws = new WebSocket("ws://localhost:8000/ws/chat");
  ws.onopen = () => {
    ws.send(JSON.stringify({ jwt_token: jwt }));
    appendMessage("System", "Connected to chat");
  };
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.reply) {
      appendMessage("Bot", data.reply);
    }
  };
  ws.onclose = () => appendMessage("System", "Connection closed");
  ws.onerror = () => appendMessage("System", "Connection error");
}

function sendMessage() {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    connect();
    setTimeout(() => sendMessage(), 500); // wait and retry
    return;
  }
  const msgInput = document.getElementById("msg");
  const msg = msgInput.value;
  if (!msg) return;
  ws.send(JSON.stringify({ message: msg }));
  appendMessage("You", msg);
  msgInput.value = "";
}

function appendMessage(sender, text) {
  const chat = document.getElementById("chat");
  const el = document.createElement("p");
  el.textContent = `${sender}: ${text}`;
  chat.appendChild(el);
}
