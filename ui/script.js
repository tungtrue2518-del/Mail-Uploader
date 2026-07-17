function setActiveNav(target) {
  document.querySelectorAll(".nav-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.target === target);
  });
}

function showPage(pageId, scrollTarget) {
  document.querySelectorAll(".page-panel").forEach((el) => {
    el.classList.toggle("active", el.id === pageId);
  });
  document.querySelector(".main").scrollTop = 0;
  if (scrollTarget) {
    const el = document.getElementById(scrollTarget);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

document.querySelector(".sidebar").addEventListener("click", (event) => {
  const item = event.target.closest(".nav-item");
  if (!item) return;
  const target = item.dataset.target;
  const page = item.dataset.page;
  setActiveNav(target);
  if (page) showPage(page, target);
});

let statusTimer = null;

function showStatus(ok, message) {
  const banner = document.getElementById("status-banner");
  const text = document.getElementById("status-text");
  const iconOk = document.getElementById("status-icon-ok");
  const iconError = document.getElementById("status-icon-error");

  text.textContent = message;
  banner.classList.remove("ok", "error");
  banner.classList.add(ok ? "ok" : "error");
  iconOk.style.display = ok ? "block" : "none";
  iconError.style.display = ok ? "none" : "block";

  banner.classList.add("show");
  banner.classList.remove("pulse");
  void banner.offsetWidth; // force reflow so the animation re-triggers on repeat calls
  banner.classList.add("pulse");

  if (statusTimer) clearTimeout(statusTimer);
  statusTimer = setTimeout(() => {
    banner.classList.remove("show");
  }, 6000);
}

function stampRefreshTime() {
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, "0");
  const mm = String(now.getMinutes()).padStart(2, "0");
  document.getElementById("stat-refresh-time").textContent = `${hh}:${mm} น.`;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

/* ---------- Sidebar search ---------- */

document.getElementById("nav-search").addEventListener("input", (event) => {
  const q = event.target.value.trim().toLowerCase();
  document.querySelectorAll(".sidebar .nav-group").forEach((group) => {
    const title = group.querySelector(".nav-group-title span:last-child");
    const groupName = title ? title.textContent.toLowerCase() : "";
    const subItems = group.querySelectorAll(".nav-item.nav-sub");
    let anyVisible = false;
    subItems.forEach((sub) => {
      const label = sub.querySelector("span:last-child").textContent.toLowerCase();
      const match = !q || groupName.includes(q) || label.includes(q);
      sub.classList.toggle("nav-hidden", !match);
      if (match) anyVisible = true;
    });
    group.classList.toggle("nav-hidden", !anyVisible);
  });
});

/* ---------- Dark mode ---------- */

function applyDarkMode(enabled) {
  document.body.classList.toggle("dark", enabled);
  document.getElementById("dark-mode-toggle").checked = enabled;
}

function toggleDarkMode() {
  const enabled = document.getElementById("dark-mode-toggle").checked;
  localStorage.setItem("darkMode", enabled ? "1" : "0");
  applyDarkMode(enabled);
}

function initDarkMode() {
  applyDarkMode(localStorage.getItem("darkMode") === "1");
}

/* ---------- Settings page: environment, autostart, about ---------- */

async function loadEnvironmentStatus() {
  const container = document.getElementById("env-status");
  const result = await window.pywebview.api.check_environment();
  if (!result.warnings || result.warnings.length === 0) {
    container.innerHTML = '<div class="env-ok"><span class="icon icon-check"></span>ทุกระบบพร้อมใช้งาน (Thunderbird / Outlook / โฟลเดอร์ Advice)</div>';
    return;
  }
  container.innerHTML = `<ul class="warning-list">${result.warnings
    .map((w) => `<li><span class="icon icon-warning"></span><span>${escapeHtml(w)}</span></li>`)
    .join("")}</ul>`;
}

async function loadAutostartStatus() {
  const result = await window.pywebview.api.get_autostart();
  document.getElementById("autostart-toggle").checked = !!result.enabled;
}

function toggleAutostart() {
  const checked = document.getElementById("autostart-toggle").checked;
  window.pywebview.api.set_autostart(checked).then((result) => {
    showStatus(result.ok, result.message);
    if (!result.ok) document.getElementById("autostart-toggle").checked = !checked;
  });
}

async function loadBackgroundTaskStatus() {
  const result = await window.pywebview.api.get_background_task();
  document.getElementById("background-task-toggle").checked = !!result.enabled;
}

function toggleBackgroundTask() {
  const checked = document.getElementById("background-task-toggle").checked;
  window.pywebview.api.set_background_task(checked).then((result) => {
    showStatus(result.ok, result.message);
    if (!result.ok) document.getElementById("background-task-toggle").checked = !checked;
  });
}

async function loadReplyBridgeStatus() {
  const result = await window.pywebview.api.get_reply_bridge();
  document.getElementById("reply-bridge-toggle").checked = !!result.enabled;
}

function toggleReplyBridge() {
  const checked = document.getElementById("reply-bridge-toggle").checked;
  window.pywebview.api.set_reply_bridge(checked).then((result) => {
    showStatus(result.ok, result.message);
    if (!result.ok) document.getElementById("reply-bridge-toggle").checked = !checked;
  });
}

async function loadAdviceConfig() {
  const config = await window.pywebview.api.get_advice_config();
  document.getElementById("advice-cfg-to").value = config.advice_to || "";
  document.getElementById("advice-cfg-cc").value = config.advice_cc || "";
  document.getElementById("advice-cfg-root").value = config.advice_root || "";
}

async function pickAdviceRootFolder() {
  const result = await window.pywebview.api.pick_advice_root_folder();
  if (!result) return;
  document.getElementById("advice-cfg-root").value = result.path;
}

function saveAdviceConfig() {
  withButton("advice-cfg-save-btn", async () => {
    const to = document.getElementById("advice-cfg-to").value.trim();
    const cc = document.getElementById("advice-cfg-cc").value.trim();
    const root = document.getElementById("advice-cfg-root").value.trim();
    const result = await window.pywebview.api.save_advice_config(to, cc, root);
    if (result.error) {
      showStatus(false, result.error);
      return;
    }
    showStatus(true, "บันทึกการตั้งค่า Advice แล้ว");
    refreshDefaults();
    loadEnvironmentStatus();
  });
}

async function loadSignatureConfig() {
  const config = await window.pywebview.api.get_signature_config();
  document.getElementById("sig-cfg-name").value = config.sig_name || "";
  document.getElementById("sig-cfg-position").value = config.sig_position || "";
  document.getElementById("sig-cfg-email").value = config.sig_email || "";
  document.getElementById("sig-cfg-it-call").value = config.sig_it_call || "";
  refreshSignaturePreview();
}

async function refreshSignaturePreview() {
  const result = await window.pywebview.api.preview_signature_html();
  const preview = document.getElementById("sig-preview");
  preview.innerHTML = result.html || '<span style="color:var(--text-muted);font-size:12.5px">ยังไม่ได้ตั้งชื่อ — จะไม่มีลายเซ็นแนบท้ายอีเมล</span>';
}

function saveSignatureConfig() {
  withButton("sig-cfg-save-btn", async () => {
    const name = document.getElementById("sig-cfg-name").value.trim();
    const position = document.getElementById("sig-cfg-position").value.trim();
    const email = document.getElementById("sig-cfg-email").value.trim();
    const itCall = document.getElementById("sig-cfg-it-call").value.trim();
    await window.pywebview.api.save_signature_config(name, position, email, itCall);
    showStatus(true, "บันทึกลายเซ็นแล้ว");
    refreshSignaturePreview();
  });
}

function fgStockLogLineClass(line) {
  if (line.includes(" OK - ")) return "log-line-ok";
  if (line.includes(" FAILED - ")) return "log-line-fail";
  if (line.includes(" SKIP - ")) return "log-line-skip";
  return "";
}

async function loadFgStockStatus() {
  const status = await window.pywebview.api.get_fg_stock_status();
  const installedBox = document.getElementById("fgstock-not-installed");
  const contentBox = document.getElementById("fgstock-content");
  if (!status.installed) {
    installedBox.style.display = "block";
    contentBox.style.display = "none";
    return;
  }
  installedBox.style.display = "none";
  contentBox.style.display = "block";

  document.getElementById("fgstock-today-status").textContent = status.today_ok ? "สำเร็จแล้ว" : "ยังไม่ export";
  document.getElementById("fgstock-last-success").textContent = status.last_success || "-";

  const task = status.task || {};
  if (task.registered) {
    document.getElementById("fgstock-next-run").textContent = task.next_run || "-";
    document.getElementById("fgstock-task-desc").textContent = `ลงทะเบียนแล้ว — รันครั้งถัดไป ${task.next_run || "-"} (รันล่าสุด ${task.last_run || "-"})`;
  } else {
    document.getElementById("fgstock-next-run").textContent = "ไม่ได้ตั้งค่า";
    document.getElementById("fgstock-task-desc").textContent = "ยังไม่ได้ลงทะเบียน Scheduled Task";
  }
  document.getElementById("fgstock-startup-desc").textContent = status.startup_shortcut
    ? "เปิดใช้งานอยู่ — จะรันทันทีทุกครั้งที่ล็อกอินเข้าเครื่อง"
    : "ยังไม่ได้ตั้งค่า";

  const logBox = document.getElementById("fgstock-log");
  if (!status.log_tail || !status.log_tail.length) {
    logBox.innerHTML = '<span style="opacity:.6">ยังไม่มีประวัติการทำงาน</span>';
  } else {
    logBox.innerHTML = status.log_tail
      .map((line) => `<div class="${fgStockLogLineClass(line)}">${escapeHtml(line)}</div>`)
      .join("");
  }
}

async function openFgStockFolder() {
  const result = await window.pywebview.api.open_fg_stock_folder();
  showStatus(result.ok, result.message);
}

async function runFgStockNow() {
  const btn = document.getElementById("fgstock-run-btn");
  btn.disabled = true;
  showStatus(true, "กำลังรันดึงข้อมูล FG Stock...");
  try {
    const result = await window.pywebview.api.run_fg_stock_now();
    showStatus(result.ok, result.message);
  } finally {
    btn.disabled = false;
    loadFgStockStatus();
  }
}

async function loadAboutInfo() {
  const info = await window.pywebview.api.get_app_info();
  document.getElementById("about-grid").innerHTML = `
    <div><b>เวอร์ชัน</b><span>${escapeHtml(info.version)}</span></div>
    <div><b>อัปเดตล่าสุด</b><span>${escapeHtml(info.build_date)}</span></div>
    <div><b>ผู้พัฒนา</b><span>${escapeHtml(info.author)}</span></div>
    <div><b>บริษัท</b><span>${escapeHtml(info.company)}</span></div>
  `;
}

function formatDateTimeThai(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString("th-TH", { dateStyle: "short", timeStyle: "short" });
  } catch (e) {
    return iso;
  }
}

function renderScheduledQueue(items) {
  const container = document.getElementById("queue-list");
  if (!items.length) {
    container.innerHTML = '<div class="queue-empty"><span class="icon icon-clock empty-state-icon"></span>ยังไม่มีรายการที่ตั้งเวลาส่งไว้</div>';
    return;
  }
  container.innerHTML = items
    .map(
      (it) => `
    <div class="queue-item ${it.status === "due" ? "due" : ""}">
      <div class="queue-item-icon"><span class="icon icon-clock"></span></div>
      <div class="queue-item-main">
        <div class="queue-item-subject">${escapeHtml(it.subject || "(ไม่มีหัวข้อ)")}</div>
        <div class="queue-item-meta">${escapeHtml(it.category || "")} · ถึง ${escapeHtml(it.to || "-")} · กำหนดส่ง ${formatDateTimeThai(it.send_time)} ${it.status === "due" ? "· ถึงเวลาแล้ว" : ""}</div>
      </div>
      <button type="button" class="resend-btn" onclick="dismissScheduled('${it.id}')"><span class="icon icon-trash"></span>เอาออกจากรายการ</button>
    </div>
  `
    )
    .join("");
}

async function dismissScheduled(id) {
  await window.pywebview.api.dismiss_scheduled(id);
  refreshScheduledQueue();
}

const warnedScheduledIds = new Set();

function checkDueSoonWarning(items) {
  const now = Date.now();
  const soon = items.find((it) => {
    if (it.status !== "pending" || warnedScheduledIds.has(it.id)) return false;
    const t = new Date(it.send_time).getTime();
    return t - now > 0 && t - now <= 5 * 60000;
  });
  if (soon) {
    warnedScheduledIds.add(soon.id);
    showStatus(true, `ใกล้ถึงเวลาส่งอัตโนมัติ: "${soon.subject || "(ไม่มีหัวข้อ)"}" ในอีกไม่กี่นาที — ยังแก้ไข/ยกเลิกได้ที่ Outbox ของ Outlook`);
  }
}

async function refreshScheduledQueue() {
  const items = await window.pywebview.api.get_scheduled_sends();
  renderScheduledQueue(items);
  checkDueSoonWarning(items);
}

/* ---------- History ---------- */

let historyCache = [];

function renderHistoryTable(logs) {
  const body = document.getElementById("history-table-body");
  if (!logs.length) {
    body.innerHTML = '<tr><td colspan="7"><div class="history-empty"><span class="icon icon-list empty-state-icon"></span>ไม่พบประวัติที่ตรงกับเงื่อนไข</div></td></tr>';
    return;
  }
  body.innerHTML = logs
    .map(
      (l) => `
    <tr>
      <td>${formatDateTimeThai(l.timestamp)}</td>
      <td><span class="history-badge">${escapeHtml(l.category || "-")}</span></td>
      <td>${l.client === "outlook" ? "Outlook" : "Thunderbird"}</td>
      <td>${escapeHtml(l.to || "-")}</td>
      <td>${escapeHtml(l.subject || "-")}</td>
      <td>${escapeHtml(l.status || "-")}</td>
      <td><button type="button" class="resend-btn" onclick="resendLog('${l.id}')"><span class="icon icon-refresh"></span>ส่งซ้ำ</button></td>
    </tr>
  `
    )
    .join("");
}

function populateHistoryCategoryFilter() {
  const select = document.getElementById("history-filter-category");
  const current = select.value;
  const categories = [...new Set(historyCache.map((l) => l.category).filter(Boolean))].sort();
  select.innerHTML =
    '<option value="">ทุกหมวดหมู่</option>' +
    categories.map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");
  select.value = current;
}

function applyHistoryFilters() {
  const q = document.getElementById("history-search").value.trim().toLowerCase();
  const category = document.getElementById("history-filter-category").value;
  const client = document.getElementById("history-filter-client").value;
  const from = document.getElementById("history-filter-from").value;
  const to = document.getElementById("history-filter-to").value;

  const filtered = historyCache.filter((l) => {
    if (category && l.category !== category) return false;
    if (client && l.client !== client) return false;
    if (q && !((l.to || "").toLowerCase().includes(q) || (l.subject || "").toLowerCase().includes(q))) return false;
    if (from && l.timestamp < from) return false;
    if (to && l.timestamp.slice(0, 10) > to) return false;
    return true;
  });
  renderHistoryTable(filtered);
}

["history-search", "history-filter-category", "history-filter-client", "history-filter-from", "history-filter-to"].forEach(
  (id) => {
    document.getElementById(id).addEventListener("input", applyHistoryFilters);
  }
);

async function loadHistory() {
  historyCache = await window.pywebview.api.get_send_log(100);
  populateHistoryCategoryFilter();
  applyHistoryFilters();
}

async function resendLog(id) {
  const result = await window.pywebview.api.resend_log(id);
  showStatus(result.ok, result.message);
  if (result.ok) loadHistory();
}

async function exportHistoryCsv() {
  const result = await window.pywebview.api.export_history_csv();
  showStatus(result.ok, result.message);
}

async function clearHistory() {
  if (!confirm("ยืนยันล้างประวัติการส่งทั้งหมด? การลบนี้ย้อนกลับไม่ได้")) return;
  await window.pywebview.api.clear_history();
  loadHistory();
  showStatus(true, "ล้างประวัติการส่งแล้ว");
}

/* ---------- Ctrl+Enter to send from a body/textarea ---------- */

document.addEventListener("keydown", (event) => {
  if (!(event.ctrlKey && event.key === "Enter")) return;
  const active = document.activeElement;
  if (!active) return;
  const card = active.closest(".card");
  if (!card) return;
  const sendBtn = card.querySelector(".btn-primary");
  if (sendBtn && !sendBtn.disabled) sendBtn.click();
});

async function refreshDefaults() {
  const data = await window.pywebview.api.get_defaults();
  document.getElementById("general-subject").value = data.general_subject;
  document.getElementById("general-body").value = data.general_body;
  document.getElementById("outlook-leave-subject").value = data.outlook_leave_subject;
  document.getElementById("outlook-leave-body").value = data.outlook_leave_body;
  applyAdviceFileInfo(data);
  stampRefreshTime();
}

function applyAdviceFileInfo(data) {
  if (!overrides.step1) {
    document.getElementById("stat-step1-file").textContent = data.step1_file;
    document.getElementById("step1-file-name").textContent = data.step1_file;
  }
  if (!overrides.step2) {
    document.getElementById("stat-step3-file").textContent = data.step3_file;
    document.getElementById("step2-file-name").textContent = data.step3_file;
  }
}

async function refreshAdviceFileInfo() {
  const data = await window.pywebview.api.get_defaults();
  applyAdviceFileInfo(data);
  stampRefreshTime();
}

function startLiveClock() {
  const el = document.getElementById("live-clock");
  if (!el) return;
  const tick = () => {
    el.textContent = new Date().toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  };
  tick();
  setInterval(tick, 1000);
}

async function withButton(btnId, fn) {
  const btn = document.getElementById(btnId);
  btn.disabled = true;
  try {
    await fn();
  } finally {
    btn.disabled = false;
  }
}

const overrides = { step1: null, step2: null };

/* ---------- Optional extra image attachment (any form) ---------- */

const imageOverrides = {};

async function pickImage(formKey) {
  const result = await window.pywebview.api.pick_image_file();
  if (!result) return;
  imageOverrides[formKey] = result.path;
  const nameEl = document.getElementById(`image-${formKey}-name`);
  const clearEl = document.getElementById(`image-${formKey}-clear`);
  if (nameEl) nameEl.textContent = result.file_name;
  if (clearEl) clearEl.style.display = "inline";
}

function clearImage(formKey) {
  delete imageOverrides[formKey];
  const nameEl = document.getElementById(`image-${formKey}-name`);
  const clearEl = document.getElementById(`image-${formKey}-clear`);
  if (nameEl) nameEl.textContent = "ไม่มี";
  if (clearEl) clearEl.style.display = "none";
}

function sendGeneral() {
  withButton("general-btn", async () => {
    const to = document.getElementById("general-to").value.trim();
    const cc = document.getElementById("general-cc").value.trim();
    const subject = document.getElementById("general-subject").value.trim();
    const body = document.getElementById("general-body").value;
    const result = await window.pywebview.api.open_general(to, cc, subject, body, imageOverrides["general"] || null);
    showStatus(result.ok, result.message);
    if (result.ok) {
      loadHistory();
      clearImage("general");
    }
  });
}

function toLocalDatetimeInputValue(date) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function toggleOutlookLeaveSchedule() {
  const checked = document.getElementById("outlook-leave-schedule-toggle").checked;
  document.getElementById("outlook-leave-schedule-wrap").style.display = checked ? "flex" : "none";
  document.getElementById("outlook-leave-btn-label").textContent = checked ? "ตั้งเวลาส่งอัตโนมัติ" : "เปิดใน Outlook";
  document.getElementById("outlook-leave-btn-icon").className = checked ? "icon icon-clock" : "icon icon-send";
  if (checked) {
    const input = document.getElementById("outlook-leave-schedule-time");
    if (!input.value) {
      input.value = toLocalDatetimeInputValue(new Date(Date.now() + 5 * 60000));
    }
  }
}

function sendOutlookLeave() {
  withButton("outlook-leave-btn", async () => {
    const to = document.getElementById("outlook-leave-to").value.trim();
    const cc = document.getElementById("outlook-leave-cc").value.trim();
    const subject = document.getElementById("outlook-leave-subject").value.trim();
    const body = document.getElementById("outlook-leave-body").value;
    const scheduled = document.getElementById("outlook-leave-schedule-toggle").checked;
    const deferredTime = scheduled ? document.getElementById("outlook-leave-schedule-time").value : null;
    if (scheduled && !deferredTime) {
      showStatus(false, "กรุณาเลือกวันเวลาที่ต้องการส่ง");
      return;
    }
    const result = await window.pywebview.api.open_outlook_leave(to, cc, subject, body, deferredTime, imageOverrides["outlook-leave"] || null);
    showStatus(result.ok, result.message);
    if (result.ok) {
      loadHistory();
      refreshScheduledQueue();
      clearImage("outlook-leave");
    }
  });
}

async function pickStep1File() {
  const result = await window.pywebview.api.pick_file();
  if (!result) return;
  if (result.error) {
    showStatus(false, result.error);
    return;
  }
  overrides.step1 = result.path;
  document.getElementById("step1-file-name").textContent = `${result.file_name} (เลือกเอง)`;
  document.getElementById("step1-reset-btn").style.display = "inline";
}

function resetStep1File() {
  overrides.step1 = null;
  document.getElementById("step1-reset-btn").style.display = "none";
  document.getElementById("step1-file-name").textContent = document.getElementById("stat-step1-file").textContent;
}

async function pickStep2File() {
  const result = await window.pywebview.api.pick_file();
  if (!result) return;
  if (result.error) {
    showStatus(false, result.error);
    return;
  }
  overrides.step2 = result.path;
  document.getElementById("step2-file-name").textContent = `${result.file_name} (เลือกเอง)`;
  document.getElementById("step2-reset-btn").style.display = "inline";
}

function resetStep2File() {
  overrides.step2 = null;
  document.getElementById("step2-reset-btn").style.display = "none";
  document.getElementById("step2-file-name").textContent = document.getElementById("stat-step3-file").textContent;
}

function sendStep1() {
  withButton("step1-btn", async () => {
    const quoteNo = document.getElementById("step1-quote").value.trim();
    const result = await window.pywebview.api.open_step1(quoteNo, overrides.step1, imageOverrides["step1"] || null);
    showStatus(result.ok, result.message);
    if (result.ok) {
      if (result.quote_no) document.getElementById("step1-quote").value = result.quote_no;
      if (!overrides.step1) {
        document.getElementById("step1-file-name").textContent = result.file_name;
        document.getElementById("stat-step1-file").textContent = result.file_name;
      }
      stampRefreshTime();
      loadHistory();
      clearImage("step1");
    }
  });
}

function sendStep2() {
  withButton("step2-btn", async () => {
    const poNo = document.getElementById("step2-po").value.trim();
    const result = await window.pywebview.api.open_step2(poNo, overrides.step2, imageOverrides["step2"] || null);
    showStatus(result.ok, result.message);
    if (result.ok) {
      if (result.po_no) document.getElementById("step2-po").value = result.po_no;
      if (!overrides.step2) {
        document.getElementById("step2-file-name").textContent = result.file_name;
        document.getElementById("stat-step3-file").textContent = result.file_name;
      }
      stampRefreshTime();
      loadHistory();
      clearImage("step2");
    }
  });
}

/* ---------- Custom categories ---------- */

function categoryIcon() {
  return '<span class="icon icon-mail"></span>';
}

const categoryCache = {};

function renderCategory(cat) {
  categoryCache[cat.id] = cat;
  const navTarget = `section-custom-${cat.id}`;
  const navContainer = document.getElementById("custom-nav-container");
  const navGroup = document.createElement("div");
  navGroup.className = "nav-group";
  navGroup.innerHTML = `
    <div class="nav-group-title">
      <span class="nav-group-dot"></span>
      <span>${escapeHtml(cat.name)}</span>
    </div>
    <div class="nav-item nav-sub" data-target="${navTarget}" data-page="page-custom-${cat.id}">
      ${categoryIcon()}
      <span>เขียนอีเมล</span>
    </div>
  `;
  navContainer.appendChild(navGroup);

  const clientLabel = cat.client === "outlook" ? "Outlook" : "Thunderbird";
  const contentContainer = document.getElementById("custom-content-container");
  const block = document.createElement("div");
  block.className = "page-panel vendor-block";
  block.id = `page-custom-${cat.id}`;
  block.innerHTML = `
    <div class="vendor-header">
      <div class="vendor-badge">${escapeHtml(cat.badge)}</div>
      <div>
        <h2>${escapeHtml(cat.name)}</h2>
        <p>${escapeHtml(cat.description)}</p>
      </div>
      <div class="vendor-header-actions">
        <button type="button" class="icon-btn" title="แก้ไขหมวดหมู่" onclick="openEditCategoryModal('${cat.id}')"><span class="icon icon-edit"></span></button>
        <button type="button" class="icon-btn danger" title="ลบหมวดหมู่" onclick="deleteCategory('${cat.id}')"><span class="icon icon-trash"></span></button>
      </div>
    </div>
    <div class="card-grid">
      <section class="card" id="${navTarget}" style="grid-column: 1 / -1;">
        <h2>เขียนอีเมล</h2>
        <p class="card-desc">เปิดร่างผ่าน ${clientLabel}</p>
        <div class="field">
          <label>ถึง (To)${cat.client === "outlook" ? `<button type="button" class="field-action" onclick="openContactPicker('custom-to-${cat.id}')">+ เลือกจาก Outlook</button>` : ""}</label>
          <input type="text" id="custom-to-${cat.id}" value="${escapeHtml(cat.to)}" />
        </div>
        <div class="field">
          <label>สำเนา (CC)${cat.client === "outlook" ? `<button type="button" class="field-action" onclick="openContactPicker('custom-cc-${cat.id}')">+ เลือกจาก Outlook</button>` : ""}</label>
          <input type="text" id="custom-cc-${cat.id}" value="${escapeHtml(cat.cc)}" />
        </div>
        <div class="field">
          <label>หัวข้อ (Subject)</label>
          <input type="text" id="custom-subject-${cat.id}" />
        </div>
        <div class="field">
          <label>เนื้อหา (Body)</label>
          <textarea id="custom-body-${cat.id}"></textarea>
        </div>
        <div class="attach-hint">
          <span class="icon icon-paperclip"></span>
          <span>รูปภาพเพิ่มเติม: <b id="image-custom-${cat.id}-name">ไม่มี</b></span>
          <button type="button" class="link-btn" id="image-custom-${cat.id}-clear" onclick="clearImage('custom-${cat.id}')" style="display:none"><span class="icon icon-refresh"></span>เอาออก</button>
        </div>
        <button type="button" class="btn-secondary" onclick="pickImage('custom-${cat.id}')">
          <span class="icon icon-folder"></span>
          แนบรูปภาพเพิ่มเติม (ถ้าจำเป็น)
        </button>
        <button class="btn-primary" id="custom-btn-${cat.id}" onclick="sendCustom('${cat.id}')" title="กด Ctrl+Enter จากช่องไหนในการ์ดนี้ก็ส่งได้">
          <span class="icon icon-send"></span>
          เปิดใน ${clientLabel}
        </button>
      </section>
    </div>
  `;
  contentContainer.appendChild(block);
}

async function loadCategories() {
  document.getElementById("custom-nav-container").innerHTML = "";
  document.getElementById("custom-content-container").innerHTML = "";
  const categories = await window.pywebview.api.get_categories();
  categories.forEach(renderCategory);
}

async function deleteCategory(catId) {
  const cat = categoryCache[catId];
  const name = cat ? cat.name : "";
  if (!confirm(`ยืนยันลบหมวดหมู่ "${name}" ใช่หรือไม่? การลบนี้ย้อนกลับไม่ได้`)) return;
  await window.pywebview.api.delete_category(catId);
  await loadCategories();
  showStatus(true, `ลบหมวดหมู่ "${name}" แล้ว`);
}

function sendCustom(catId) {
  withButton(`custom-btn-${catId}`, async () => {
    const to = document.getElementById(`custom-to-${catId}`).value.trim();
    const cc = document.getElementById(`custom-cc-${catId}`).value.trim();
    const subject = document.getElementById(`custom-subject-${catId}`).value.trim();
    const body = document.getElementById(`custom-body-${catId}`).value;
    const result = await window.pywebview.api.open_custom(catId, subject, body, to, cc, imageOverrides[`custom-${catId}`] || null);
    showStatus(result.ok, result.message);
    if (result.ok) {
      loadHistory();
      clearImage(`custom-${catId}`);
    }
  });
}

/* ---------- Add-category modal ---------- */

function openAddCategoryModal() {
  document.getElementById("edit-cat-id").value = "";
  document.getElementById("add-cat-modal-title").textContent = "เพิ่มหมวดหมู่ใหม่";
  document.getElementById("add-cat-modal-desc").textContent = "สร้างหมวดหมู่สำหรับงานส่งเมลรูปแบบใหม่ พร้อมช่องกรอกอิสระ";
  document.getElementById("add-cat-submit-btn").innerHTML = '<span class="icon icon-plus"></span>เพิ่มหมวดหมู่';
  document.getElementById("add-category-overlay").classList.add("show");
  document.getElementById("new-cat-name").focus();
}

function openEditCategoryModal(catId) {
  const cat = categoryCache[catId];
  if (!cat) return;
  document.getElementById("edit-cat-id").value = cat.id;
  document.getElementById("add-cat-modal-title").textContent = `แก้ไขหมวดหมู่ "${cat.name}"`;
  document.getElementById("add-cat-modal-desc").textContent = "ปรับปรุงข้อมูลหมวดหมู่นี้";
  document.getElementById("add-cat-submit-btn").innerHTML = '<span class="icon icon-check"></span>บันทึกการแก้ไข';
  document.getElementById("new-cat-name").value = cat.name;
  document.getElementById("new-cat-badge").value = cat.badge;
  document.getElementById("new-cat-desc").value = cat.description;
  document.getElementById("new-cat-client").value = cat.client;
  document.getElementById("new-cat-to").value = cat.to;
  document.getElementById("new-cat-cc").value = cat.cc;
  document.getElementById("add-category-overlay").classList.add("show");
  document.getElementById("new-cat-name").focus();
}

function closeAddCategoryModal() {
  document.getElementById("add-category-overlay").classList.remove("show");
  ["new-cat-name", "new-cat-badge", "new-cat-desc", "new-cat-to", "new-cat-cc", "edit-cat-id"].forEach((id) => {
    document.getElementById(id).value = "";
  });
}

async function submitAddCategory() {
  const name = document.getElementById("new-cat-name").value.trim();
  if (!name) {
    showStatus(false, "กรุณาตั้งชื่อหมวดหมู่");
    return;
  }
  const badge = document.getElementById("new-cat-badge").value.trim();
  const description = document.getElementById("new-cat-desc").value.trim();
  const client = document.getElementById("new-cat-client").value;
  const to = document.getElementById("new-cat-to").value.trim();
  const cc = document.getElementById("new-cat-cc").value.trim();
  const editId = document.getElementById("edit-cat-id").value;

  if (editId) {
    const result = await window.pywebview.api.update_category(editId, name, badge, description, client, to, cc);
    if (result.error) {
      showStatus(false, result.error);
      return;
    }
    closeAddCategoryModal();
    await loadCategories();
    showStatus(true, `บันทึกการแก้ไข "${result.category.name}" แล้ว`);
    return;
  }

  const result = await window.pywebview.api.add_category(name, badge, description, client, to, cc);
  if (result.error) {
    showStatus(false, result.error);
    return;
  }
  renderCategory(result.category);
  closeAddCategoryModal();
  showStatus(true, `เพิ่มหมวดหมู่ "${result.category.name}" แล้ว`);
}

document.getElementById("add-category-btn").addEventListener("click", openAddCategoryModal);
document.getElementById("add-category-overlay").addEventListener("click", (event) => {
  if (event.target.id === "add-category-overlay") closeAddCategoryModal();
});

/* ---------- Outlook contact picker ---------- */

let outlookContacts = null;
let contactPickerTarget = null;
let selectedContactEmails = new Set();
let currentContactList = [];

function updateContactSelectionMeta() {
  const countEl = document.getElementById("contact-selected-count");
  countEl.textContent = selectedContactEmails.size ? `เลือกแล้ว ${selectedContactEmails.size} คน` : "";

  const selectAll = document.getElementById("contact-select-all");
  const visibleEmails = currentContactList.map((c) => c.email);
  const allVisibleSelected = visibleEmails.length > 0 && visibleEmails.every((e) => selectedContactEmails.has(e));
  selectAll.checked = allVisibleSelected;
  selectAll.indeterminate = !allVisibleSelected && visibleEmails.some((e) => selectedContactEmails.has(e));
}

function renderContactList(list) {
  currentContactList = list;
  const container = document.getElementById("contact-list");
  if (!list.length) {
    container.innerHTML = '<div class="contact-empty"><span class="icon icon-user empty-state-icon"></span>ไม่พบรายชื่อ</div>';
  } else {
    container.innerHTML = list
      .map(
        (c) => `
    <label class="contact-item">
      <input type="checkbox" data-email="${escapeHtml(c.email)}" ${selectedContactEmails.has(c.email) ? "checked" : ""} />
      <span class="icon icon-user contact-item-icon"></span>
      <div>
        <div class="contact-name">${escapeHtml(c.name)}</div>
        <div class="contact-email">${escapeHtml(c.email)}</div>
      </div>
    </label>
  `
      )
      .join("");
  }
  updateContactSelectionMeta();
}

function toggleSelectAllContacts() {
  const checked = document.getElementById("contact-select-all").checked;
  currentContactList.forEach((c) => {
    if (checked) selectedContactEmails.add(c.email);
    else selectedContactEmails.delete(c.email);
  });
  renderContactList(currentContactList);
}

document.getElementById("contact-list").addEventListener("change", (event) => {
  const checkbox = event.target.closest('input[type="checkbox"]');
  if (!checkbox) return;
  const email = checkbox.dataset.email;
  if (checkbox.checked) selectedContactEmails.add(email);
  else selectedContactEmails.delete(email);
  updateContactSelectionMeta();
});

document.getElementById("contact-search").addEventListener("input", (event) => {
  if (!outlookContacts) return;
  const q = event.target.value.trim().toLowerCase();
  const filtered = q
    ? outlookContacts.filter((c) => c.name.toLowerCase().includes(q) || c.email.toLowerCase().includes(q))
    : outlookContacts;
  renderContactList(filtered);
});

async function openContactPicker(targetInputId) {
  contactPickerTarget = targetInputId;
  selectedContactEmails = new Set();
  document.getElementById("contact-search").value = "";
  document.getElementById("contact-picker-overlay").classList.add("show");

  if (outlookContacts) {
    document.getElementById("contact-picker-status").textContent = `พบ ${outlookContacts.length} รายชื่อในสมุดที่อยู่ Outlook (กำลังอัปเดต...)`;
    renderContactList(outlookContacts);
  } else {
    document.getElementById("contact-picker-status").textContent = "กำลังโหลดรายชื่อจาก Outlook...";
    document.getElementById("contact-list").innerHTML = "";
  }

  // always refetch, so the list reflects the current Outlook address book, not a stale cache
  const result = await window.pywebview.api.get_outlook_contacts();
  if (result.error) {
    document.getElementById("contact-picker-status").textContent = result.error;
    return;
  }
  outlookContacts = result.contacts;
  document.getElementById("contact-picker-status").textContent = `พบ ${outlookContacts.length} รายชื่อในสมุดที่อยู่ Outlook`;
  renderContactList(outlookContacts);
}

function closeContactPicker() {
  document.getElementById("contact-picker-overlay").classList.remove("show");
}

function applyContactSelection() {
  if (selectedContactEmails.size === 0) {
    closeContactPicker();
    return;
  }
  const input = document.getElementById(contactPickerTarget);
  const existing = input.value.split(",").map((s) => s.trim()).filter(Boolean);
  const seen = new Set(existing.map((e) => e.toLowerCase()));
  const finalList = [...existing];
  selectedContactEmails.forEach((email) => {
    if (!seen.has(email.toLowerCase())) {
      finalList.push(email);
      seen.add(email.toLowerCase());
    }
  });
  input.value = finalList.join(", ");
  closeContactPicker();
}

document.getElementById("contact-picker-overlay").addEventListener("click", (event) => {
  if (event.target.id === "contact-picker-overlay") closeContactPicker();
});

window.addEventListener("pywebviewready", () => {
  initDarkMode();
  startLiveClock();
  refreshDefaults();
  loadCategories();
  loadHistory();
  loadEnvironmentStatus();
  loadAdviceConfig();
  loadSignatureConfig();
  loadAutostartStatus();
  loadBackgroundTaskStatus();
  loadReplyBridgeStatus();
  loadAboutInfo();
  loadFgStockStatus();
  refreshScheduledQueue();
  setInterval(refreshScheduledQueue, 60000);
  setInterval(refreshAdviceFileInfo, 30000);
  setInterval(loadHistory, 30000);
  setInterval(loadFgStockStatus, 60000);
});
