// OverAll Uploader Reply Bridge — background script
// Keeps a persistent native-messaging connection to the Python app's
// "reply bridge host" (mail_app.py --reply-bridge-host, launched by
// Thunderbird itself the first time this connects). Jobs arrive over that
// port; each job asks us to find an existing message (by searching its body
// for a PR&QC/quote number) and open a REAL Thunderbird reply or forward to
// it — not a fresh compose — so the resulting draft threads onto the
// original conversation. Supports zero or more attachments (sent as base64
// so we never need file:// host permissions).

const HOST_NAME = "com.velsuede.mail_uploader_reply_bridge";
let port = null;

function log(...args) {
  console.log("[reply-bridge]", ...args);
}

function connect() {
  try {
    port = browser.runtime.connectNative(HOST_NAME);
    port.onMessage.addListener(onHostMessage);
    port.onDisconnect.addListener(() => {
      log("native host disconnected", browser.runtime.lastError);
      port = null;
      setTimeout(connect, 5000);
    });
    log("connected to native host");
  } catch (e) {
    log("connect failed", e);
    setTimeout(connect, 5000);
  }
}

async function onHostMessage(job) {
  if (!job || !job.jobId) return;
  log("job received", job.jobId, job.searchText);
  try {
    const result = await processJob(job);
    port.postMessage({ jobId: job.jobId, ok: true, ...result });
  } catch (e) {
    log("job failed", job.jobId, e);
    port.postMessage({ jobId: job.jobId, ok: false, error: String(e && e.message ? e.message : e) });
  }
}

function base64ToFile(base64, filename, mimeType) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return new File([bytes], filename, { type: mimeType || "application/pdf" });
}

async function processJob(job) {
  // job: { jobId, action: "reply"|"forward", searchText, cc, body, attachments: [{name, base64}] }
  const found = await messenger.messages.query({ body: job.searchText });
  const messages = found && found.messages ? found.messages : [];
  if (!messages.length) {
    throw new Error(`ไม่พบอีเมลต้นฉบับที่มีข้อความ "${job.searchText}" ในเนื้อหา`);
  }
  messages.sort((a, b) => new Date(b.date) - new Date(a.date));
  const original = messages[0];

  const composeDetails = { body: job.body, isPlainText: true };
  if (job.cc) composeDetails.cc = job.cc;

  const action = job.action || "reply";
  const composeTab =
    action === "forward"
      ? await messenger.compose.beginForward(original.id, "forwardInline", composeDetails)
      : await messenger.compose.beginReply(original.id, "replyToSender", composeDetails);

  // beginReply/beginForward's composeDetails override isn't guaranteed on
  // every TB version — re-apply explicitly to be safe.
  await messenger.compose.setComposeDetails(composeTab.id, composeDetails);

  // New multi-attachment form, with a fallback to the old single-attachment
  // fields in case anything still sends those.
  const attachments = job.attachments || (job.attachmentBase64 ? [{ name: job.attachmentName, base64: job.attachmentBase64 }] : []);
  for (const att of attachments) {
    const file = base64ToFile(att.base64, att.name || "attachment.pdf");
    await messenger.compose.addAttachment(composeTab.id, { file });
  }

  return { originalMessageId: original.id, originalSubject: original.subject, composeTabId: composeTab.id };
}

connect();
