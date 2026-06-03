const state = {
  tickets: [],
  results: new Map(),
  loading: new Set(),
};

const els = {
  rows: document.getElementById("ticketRows"),
  ticketCount: document.getElementById("ticketCount"),
  supplementTasksBtn: document.getElementById("supplementTasksBtn"),
  refreshBtn: document.getElementById("refreshBtn"),
  processAllBtn: document.getElementById("processAllBtn"),
};

function loadCachedResults() {
  try {
    const cached = JSON.parse(sessionStorage.getItem("aiResults") || "{}");
    state.results = new Map(Object.entries(cached));
  } catch (_) {
    state.results = new Map();
  }
}

function saveCachedResults() {
  sessionStorage.setItem("aiResults", JSON.stringify(Object.fromEntries(state.results)));
}

async function loadTickets() {
  els.refreshBtn.disabled = true;
  try {
    state.tickets = await api("/tickets");
    renderTickets();
  } catch (error) {
    showToast(`加载工单失败：${error.message}`);
  } finally {
    els.refreshBtn.disabled = false;
  }
}

function renderTickets() {
  els.ticketCount.textContent = `${state.tickets.length} 条`;
  els.rows.innerHTML = state.tickets
    .map((ticket, index) => {
      const result = state.results.get(ticket.ticket_no);
      const loading = state.loading.has(ticket.ticket_no);
      const status = typeof resultStatusLabel === "function" ? resultStatusLabel(result) : (result?.status || "未检测");
      const caseNature = result?.structured?.case_nature || "未检测";
      const risk = result?.professional_claimant_risk || "未检测";
      const actionDone = result?.automation_mode === "auto_executed";
      const fallbackActionText = result?.status === "建议退单" ? "已退单" : result?.status === "待补充" ? "已加入补充任务" : "已流转";
      const actionText = actionDone && typeof executedActionLabel === "function" ? executedActionLabel(result) : actionDone ? fallbackActionText : (loading ? "流转中" : "智能流转");
      const actionClass = actionDone && typeof executedButtonClass === "function" ? executedButtonClass(result) : actionDone ? "secondary" : "primary";
      const rerunButton = actionDone
        ? `<button class="btn secondary rerun-btn" data-ticket-no="${escapeHtml(ticket.ticket_no)}" ${loading ? "disabled" : ""}>重新流转</button>`
        : "";
      return `
        <tr data-ticket-no="${escapeHtml(ticket.ticket_no)}">
          <td class="red-text">${index + 1}</td>
          <td class="red-text">${escapeHtml(ticket.ticket_no)}</td>
          <td class="red-text">${escapeHtml(ticket.third_party_ticket_no || "-")}</td>
          <td class="title-cell">${escapeHtml(truncate(ticket.title, 42))}</td>
          <td><div class="content-cell">${escapeHtml(truncate(ticket.content, 210))}</div></td>
          <td class="red-text">${escapeHtml(ticket.customer_name || "-")}</td>
          <td class="red-text">${escapeHtml(ticket.contact_phone || ticket.caller_phone || "-")}</td>
          <td class="red-text">${escapeHtml(ticket.incident_at || "-")}</td>
          <td class="red-text">${escapeHtml(ticket.due_at || "-")}</td>
          <td class="red-text">${escapeHtml(ticket.ticket_type || "-")}</td>
          <td>${badge(status, statusColor(status))}</td>
          <td>${badge(caseNature, typeof caseNatureColor === "function" ? caseNatureColor(caseNature) : "gray")}</td>
          <td>${badge(risk === "高" ? "疑似职业索赔高风险" : risk, riskColor(risk))}</td>
          <td>
            <button class="btn ${actionClass} detect-btn" data-ticket-no="${escapeHtml(ticket.ticket_no)}" ${loading || actionDone ? "disabled" : ""}>
              ${escapeHtml(actionText)}
            </button>
            ${rerunButton}
          </td>
        </tr>`;
    })
    .join("");
}

function goDetail(ticketNo) {
  window.location.href = `/demo/detail.html?ticket_no=${encodeURIComponent(ticketNo)}`;
}

async function detectTicket(ticketNo) {
  state.loading.add(ticketNo);
  renderTickets();
  try {
    const result = await api(`/tickets/${encodeURIComponent(ticketNo)}/smart-transfer`, { method: "POST" });
    state.results.set(ticketNo, result);
    saveCachedResults();
    const mode = result.automation_mode === "auto_executed" ? "已自动执行" : "需人工确认";
    showToast(`工单 ${ticketNo} 智能流转完成：${result.status}，${mode}`);
    if (typeof notifyAutoExecution === "function") {
      notifyAutoExecution(result);
    }
  } catch (error) {
    showToast(`智能流转失败：${error.message}`);
  } finally {
    state.loading.delete(ticketNo);
    renderTickets();
  }
}

function clearCachedResult(ticketNo) {
  state.results.delete(ticketNo);
  saveCachedResults();
}

async function rerunTicket(ticketNo) {
  clearCachedResult(ticketNo);
  showToast(`工单 ${ticketNo} 正在重新智能流转。`);
  await detectTicket(ticketNo);
}

async function processAll() {
  els.processAllBtn.disabled = true;
  try {
    for (const ticket of state.tickets) {
      await detectTicket(ticket.ticket_no);
    }
    showToast("批量智能流转完成。");
  } finally {
    els.processAllBtn.disabled = false;
  }
}

document.addEventListener("click", (event) => {
  const detectBtn = event.target.closest(".detect-btn");
  const rerunBtn = event.target.closest(".rerun-btn");
  const row = event.target.closest("tr[data-ticket-no]");

  if (rerunBtn) {
    event.stopPropagation();
    rerunTicket(rerunBtn.dataset.ticketNo);
    return;
  }
  if (detectBtn) {
    event.stopPropagation();
    detectTicket(detectBtn.dataset.ticketNo);
    return;
  }
  if (row) {
    goDetail(row.dataset.ticketNo);
  }
});

els.refreshBtn.addEventListener("click", loadTickets);
els.processAllBtn.addEventListener("click", processAll);
els.supplementTasksBtn.addEventListener("click", () => {
  window.location.href = "/demo/supplement-tasks.html";
});

loadCachedResults();
loadTickets();
