import re

with open('chrome_extension/background.js', 'r') as f:
    content = f.read()

# Unified fetcher
unified_fetcher = """
async function sendToN8n(event, payload) {
  try {
    const res = await fetch(N8N_MASTER_WEBHOOK, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event, ...payload })
    });
    return await res.json();
  } catch (err) {
    return { success: false, status: "error", message: err.message, error: err.message };
  }
}
"""

if "async function sendToN8n" not in content:
    content = content.replace('const N8N_MASTER_WEBHOOK = "https://n8n.themenuagency.com/webhook/fios-master";',
                              'const N8N_MASTER_WEBHOOK = "https://n8n.themenuagency.com/webhook/fios-master";\n' + unified_fetcher)


def replacer(match):
    action = match.group('action')
    return f"""  if (request.action === "{action}") {{
    sendToN8n("{action.lower()}", request).then(sendResponse);
    return true;
  }}"""

# Regex to match the standard fetch handlers we want to replace
pattern = r'  if \(request\.action === "(?P<action>[A-Z_]+)"\) \{\s*fetch\(.*?\)\s*\.then.*?return true;\s*\}'
content = re.sub(pattern, replacer, content, flags=re.DOTALL)

with open('chrome_extension/background.js', 'w') as f:
    f.write(content)
print("Rewrote background.js to use n8n native webhook.")
