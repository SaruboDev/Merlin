import { marked } from "https://cdn.jsdelivr.net/npm/marked/lib/marked.esm.js";
import hljs from "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.11.1/es/highlight.min.js";
import go from "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.11.1/es/languages/go.min.js";
hljs.registerLanguage('go', go);

const renderer = new marked.Renderer();
renderer.code = function({ text, lang }) {
    const language = hljs.getLanguage(lang) ? lang : 'plaintext';
    const highlighted = hljs.highlight(text, { language }).value;
    return `<pre><code class="hljs language-${language}">${highlighted}</code></pre>`;
};

marked.setOptions({ renderer });

const chat_box = document.getElementById("user-input");
const chat = document.getElementById("chat-space");

let model_name;
let reasoning;
let streaming;

chat_box.addEventListener("keydown", send);
function send(event) {
    if (event.key == "Enter" && !event.shiftKey) {
        event.preventDefault();

        sendText();
        chat_box.style.height = "0px";
        chat_box.style.overflowY = "hidden";
    }
}
chat_box.addEventListener("input", expand);
function expand(input) {
    chat_box.style.height = "0px";
    chat_box.style.overflowY = "hidden";

    if (chat_box.scrollHeight >= 200) {
        const newHeight = Math.min(chat_box.scrollHeight, 200);
        chat_box.style.height = newHeight + "px";
        chat_box.style.overflowY = "auto";
    } else {
        chat_box.style.height = chat_box.scrollHeight + "px";
    }
}
let userScrolled = false;
chat.addEventListener("scroll", () => {
    userScrolled = chat.scrollTop + chat.clientHeight < chat.scrollHeight - 10;
});

async function sendText() {
    const message = chat_box.value.trim();
    if (!message) return;

    let container = document.getElementById("chat-space");

    create_user_bubble(message, false);

    if (!userScrolled) chat.scrollTop = chat.scrollHeight;

    chat_box.value = "";
    const response = await fetch("/api/send-text", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({user_text: message})
    });

    let content_type = response.headers.get("content-type");
    console.log(content_type);

    if (content_type == "text/event-stream; charset=utf-8") {
        // Maybe this can also be placed in a single function to create the bubble??

        let message_assistant = document.createElement("div");
        message_assistant.className = "message assistant";
        let bubble_assistant = document.createElement("div");
        bubble_assistant.className = "bubble";
        message_assistant.appendChild(bubble_assistant);

        container.appendChild(message_assistant);

        console.log(response);
        const reader = response.body.getReader();
        var string = new TextDecoder();

        let rawText = "";
        reader.read().then(function processText({done, value}){
            if (done) {
                console.log("Stream complete");
                save_assistant_text(rawText);
                return;
            }
            rawText += string.decode(value);
            bubble_assistant.innerHTML = marked.parse(rawText);
            if (!userScrolled) chat.scrollTop = chat.scrollHeight;
            return reader.read().then(processText);
        })
    } else {
        const result = await response.json();
        console.log(response);

        create_assistant_bubble(result.response, false);

        if (!userScrolled) chat.scrollTop = chat.scrollHeight;
        console.log("Result: ", result);
    }
    if (!userScrolled) chat.scrollTop = chat.scrollHeight;
};

function create_user_bubble(message, prepend) {
    let message_user = document.createElement("div");
    message_user.className = "message user";
    let bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.innerHTML = marked.parse(message);
    message_user.appendChild(bubble);

    let container = document.getElementById("chat-space");

    if (prepend == true) {
        container.prepend(message_user);
    } else {
        container.appendChild(message_user);
    }
}

function create_assistant_bubble(message, prepend) {
    let container = document.getElementById("chat-space");
    let message_assistant = document.createElement("div");
    message_assistant.className = "message assistant";
    let bubble_assistant = document.createElement("div");
    bubble_assistant.className = "bubble";
    bubble_assistant.innerHTML = marked.parse(message);
    message_assistant.appendChild(bubble_assistant);

    if (prepend == true) {
        container.prepend(message_assistant);
    } else {
        container.appendChild(message_assistant);
    }
}

async function save_assistant_text(text) {
    const response = await fetch("/api/save-assistant-text", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({user_text: text})
    });
    const result = await response.json();
    console.log("Result: ", result);
}

async function changeOption(id) {
    const options = document.getElementById(id);

    const response = await fetch("/api/change-settings", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({option_name: id, option: options.value})
    })
    const result = await response.json();
    console.log("Result: ", result);
}

function changeBG() {
    if (this.checked) {
        document.getElementById('streaming-img').style.backgroundImage = 'url("/svg/toggle_on.svg")';
        document.getElementById('streaming').value = "on";
    } else {
        document.getElementById('streaming-img').style.backgroundImage = 'url("/svg/toggle_off.svg"';
        document.getElementById('streaming').value = "off";
    }
    changeOption('streaming');
}

document.getElementById('streaming').addEventListener('change', changeBG);

async function getOptions() {
    const response = await fetch("/api/load-settings", {
        method: "GET",
        headers: {
            "Content-Type": "application/json",
        }
    })
    const result = await response.json();
    
    console.log("Result: ", result);

    model_name = result["Model"]["model_name"];
    reasoning = result["Model"]["reasoning"];
    streaming = result["Model"]["streaming"];

    console.log(streaming);
    if (streaming == "off") {
        document.getElementById('streaming-img').style.backgroundImage = 'url("/svg/toggle_off.svg"';
        document.getElementById('streaming').value = "off";
    };
    if (streaming == "on") {
        document.getElementById('streaming-img').style.backgroundImage = 'url("/svg/toggle_on.svg")';
        document.getElementById('streaming').value = "on";
    };
    
    let think = document.getElementById("reasoning");
    switch (reasoning) {
        case "false":
            think.selectedIndex = 0;
            break;
        case "low":
            think.selectedIndex = 3;
            break;
        case "medium":
            think.selectedIndex = 2;
            break;
        case "high":
            think.selectedIndex = 1;
            break;
    }
}

getOptions();

async function retrieve_old_texts() {
    // This one gets called WHEN you load the page!
    const response_sent = await fetch("/api/get-old-texts", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({"reload": -1})
    })
    const result_sent = await response_sent.json();
    console.log("Result SENT: ", result_sent);

    load_other_texts();
}

async function load_other_texts() {
    const response = await fetch("/api/get-old-texts", {
        method: "GET",
        headers: {
            "Content-Type": "application/json",
        }
    })
    const result = await response.json();
    console.log(result);
    for (var i = result.response.length - 1; i >= 0 ; i--) {
        console.log(result.response[i][0]);
        if (result.response[i][0] == "user") {
            create_user_bubble(result.response[i][1], true)
        } else {
            create_assistant_bubble(result.response[i][1], true)
        };
    }
    if (!userScrolled) chat.scrollTop = chat.scrollHeight;
}
document.getElementById("clickMe").addEventListener("click", load_other_texts);
retrieve_old_texts()