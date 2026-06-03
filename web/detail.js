const params = new URLSearchParams(window.location.search);
const ticketNo = params.get("ticket_no");

const els = {
  backBtn: document.getElementById("backBtn"),
  detectBtn: document.getElementById("detailDetectBtn"),
  selectedTicketNo: document.getElementById("selectedTicketNo"),
  detailEmpty: document.getElementById("detailEmpty"),
  ticketDetail: document.getElementById("ticketDetail"),
  aiStatus: document.getElementById("aiStatus"),
  aiEmpty: document.getElementById("aiEmpty"),
  aiResult: document.getElementById("aiResult"),
};

let ticket = null;
let result = null;

function loadCachedResult() {
  try {
    const cached = JSON.parse(sessionStorage.getItem("aiResults") || "{}");
    return ticketNo ? cached[ticketNo] : null;
  } catch (_) {
    return null;
  }
}

function saveCachedResult(value) {
  const cached = JSON.parse(sessionStorage.getItem("aiResults") || "{}");
  cached[value.ticket_no] = value;
  sessionStorage.setItem("aiResults", JSON.stringify(cached));
}

async function loadTicket() {
  if (!ticketNo) {
    els.detailEmpty.textContent = "缺少 ticket_no 参数。";
    return;
  }
  try {
    ticket = await api(`/tickets/${encodeURIComponent(ticketNo)}`);
    els.selectedTicketNo.textContent = ticket.ticket_no;
    els.detailEmpty.classList.add("hidden");
    els.ticketDetail.classList.remove("hidden");
    els.ticketDetail.innerHTML = renderDetail(ticket);

    result = loadCachedResult();
    renderAiResult(result);
  } catch (error) {
    els.detailEmpty.textContent = `加载工单失败：${error.message}`;
  }
}

function renderAiResult(current) {
  if (!current) {
    els.aiStatus.textContent = "未检测";
    els.detectBtn.disabled = false;
    els.detectBtn.textContent = "智能流转";
    els.aiEmpty.classList.remove("hidden");
    els.aiResult.classList.add("hidden");
    return;
  }
  els.aiStatus.textContent = typeof resultStatusLabel === "function" ? resultStatusLabel(current) : current.status;
  if (current.automation_mode === "auto_executed") {
    els.detectBtn.disabled = false;
    els.detectBtn.textContent = "重新智能流转";
  } else {
    els.detectBtn.disabled = false;
    els.detectBtn.textContent = "智能流转";
  }
  els.aiEmpty.classList.add("hidden");
  els.aiResult.classList.remove("hidden");
  els.aiResult.innerHTML = renderAiResultHtml(current);
}

async function detectTicket() {
  if (!ticketNo) return;
  els.detectBtn.disabled = true;
  els.detectBtn.textContent = "流转中";
  els.aiStatus.textContent = "流转中";
  if (result?.automation_mode === "auto_executed") {
    result = null;
    saveCachedResultPlaceholder(ticketNo);
  }
  try {
    result = await api(`/tickets/${encodeURIComponent(ticketNo)}/smart-transfer`, { method: "POST" });
    saveCachedResult(result);
    renderAiResult(result);
    const mode = result.automation_mode === "auto_executed" ? "已自动执行" : "需人工确认";
    showToast(`智能流转完成：${result.status}，${mode}`);
    if (typeof notifyAutoExecution === "function") {
      notifyAutoExecution(result);
    }
  } catch (error) {
    showToast(`智能流转失败：${error.message}`);
  } finally {
    els.detectBtn.disabled = false;
    els.detectBtn.textContent = result?.automation_mode === "auto_executed" ? "重新智能流转" : "智能流转";
  }
}

function saveCachedResultPlaceholder(ticketNoValue) {
  const cached = JSON.parse(sessionStorage.getItem("aiResults") || "{}");
  delete cached[ticketNoValue];
  sessionStorage.setItem("aiResults", JSON.stringify(cached));
}

async function createSupplementTask(ticketNoValue, button) {
  if (button) {
    button.disabled = true;
    button.textContent = "生成中";
  }
  els.aiStatus.textContent = "正在生成补充任务";
  showToast("正在生成补充核心信息任务，请稍候。");
  try {
    const task = await api(`/tickets/${encodeURIComponent(ticketNoValue)}/supplement-task`, { method: "POST" });
    els.aiStatus.textContent = "补充任务已生成";
    showToast("已生成补充核心信息任务，正在打开任务列表。");
    console.log("supplement task created", task);
    window.setTimeout(() => {
      window.location.href = "/demo/supplement-tasks.html";
    }, 600);
  } catch (error) {
    els.aiStatus.textContent = result?.status || "生成补充任务失败";
    showToast(`生成补充任务失败：${error.message}`);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "生成补充核心信息任务";
    }
  }
}

function mockOperation(message) {
  showToast(`${message}。demo 阶段不真实提交工单系统。`);
}

document.addEventListener("click", (event) => {
  const supplementBtn = event.target.closest(".op-supplement");
  const returnBtn = event.target.closest(".op-return");
  const transferBtn = event.target.closest(".op-transfer");

  if (supplementBtn) {
    createSupplementTask(supplementBtn.dataset.ticketNo, supplementBtn);
    return;
  }
  if (returnBtn) {
    mockOperation("已模拟确认退单");
    return;
  }
  if (transferBtn) {
    mockOperation(`已模拟流转至 ${result?.recommended_branch || "建议承办单位"}`);
  }
});

els.backBtn.addEventListener("click", () => {
  window.location.href = "/demo/";
});
els.detectBtn.addEventListener("click", detectTicket);

loadTicket();
