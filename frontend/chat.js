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
    document.getElementById('chat-input').style.display = 'flex';
  };
  ws.onmessage = (event) => {
    const messagesDiv = document.getElementById('messages');
    const botMessageDiv = document.createElement('div');
    botMessageDiv.classList.add('message', 'bot-message');
    
    // Apply style to respect newlines and wrap text
    botMessageDiv.style.whiteSpace = "pre-wrap";
    botMessageDiv.style.wordWrap = "break-word";

    try {
      const data = JSON.parse(event.data);
      let displayText = ""; // Ensure displayText is always initialized as a string

      if (data && data.error) {
        displayText = `Bot: Error - ${data.error}`;
      } else if (Array.isArray(data)) {
        if (data.length > 0) {
          displayText = "Bot: Found these relevant snippets:"; // Initial part, newlines will be added after this
          data.forEach((hit, index) => {
            let memoryEntry = "No content preview available.";
            if (hit && typeof hit.memory === 'string') {
              memoryEntry = hit.memory;
            } else if (hit && typeof hit.text === 'string') { // Fallback if 'memory' field is not present
              memoryEntry = hit.text;
            }
            displayText += `\n\n[${index + 1}] ${memoryEntry.substring(0, 300)}${memoryEntry.length > 300 ? '...' : ''}`;
            if (hit && typeof hit.score === 'number') {
              displayText += `\n   (Score: ${hit.score.toFixed(4)})`;
            }
          });
        } else {
          displayText = "Bot: I found no specific snippets for your query in the email data.";
        }
      } else if (typeof data === 'string') { 
        displayText = "Bot: " + data;
      } else {
        displayText = "Bot: Received an unexpected data format.";
        console.warn("Unexpected data format from WebSocket:", data);
      }
      botMessageDiv.textContent = displayText; // Assign the fully constructed string
    } catch (e) {
      console.error("Error processing message from WebSocket:", e);
      console.log("Raw data from server:", event.data);
      botMessageDiv.textContent = "Bot (raw data): " + event.data; // Fallback for raw data
    }
    
    messagesDiv.appendChild(botMessageDiv);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
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
