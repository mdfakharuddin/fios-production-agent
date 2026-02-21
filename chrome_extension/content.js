async function captureUpworkConversation() {
    const messageElements = document.querySelectorAll('[data-test="message-text"]');
    let messages = [];

    messageElements.forEach(el => {
        messages.push(el.innerText);
    });

    if (messages.length === 0) return;

    const latestMessage = messages[messages.length - 1];

    const fiosResponse = await queryFIOS(
        `Client said: ${latestMessage}`,
        "upwork_convo_" + window.location.pathname
    );

    if (fiosResponse) {
        injectReplySuggestion(fiosResponse.response);
    }
}

function injectReplySuggestion(replyText) {
    const replyBox = document.querySelector('[data-test="message-compose-input"]');
    if (!replyBox) return;

    let button = document.getElementById("fios-reply-btn");
    if (!button) {
        button = document.createElement("button");
        button.id = "fios-reply-btn";
        button.innerText = "Generate AI Reply";
        button.style.margin = "10px";
        button.style.padding = "8px";
        button.style.backgroundColor = "#108a00";
        button.style.color = "white";
        button.style.border = "none";
        button.style.borderRadius = "4px";
        button.style.cursor = "pointer";
        button.style.fontWeight = "bold";

        button.onclick = () => {
            replyBox.innerText = replyText;
        };

        replyBox.parentElement.appendChild(button);
    }
}

const observer = new MutationObserver(() => {
    captureUpworkConversation();
});

observer.observe(document.body, {
    childList: true,
    subtree: true
});
