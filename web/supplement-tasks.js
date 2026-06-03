const els = {
  backBtn: document.getElementById("backBtn"),
  refreshBtn: document.getElementById("refreshBtn"),
  taskCount: document.getElementById("taskCount"),
  taskRows: document.getElementById("taskRows"),
};

async function loadTasks() {
  els.refreshBtn.disabled = true;
  try {
    const tasks = await api("/supplement-tasks");
    renderTasks(tasks);
  } catch (error) {
    showToast(`加载补充任务失败：${error.message}`);
  } finally {
    els.refreshBtn.disabled = false;
  }
}

function renderTasks(tasks) {
  els.taskCount.textContent = `${tasks.length} 条`;
  if (!tasks.length) {
    els.taskRows.innerHTML = `<tr><td colspan="9" class="empty">暂无补充信息任务。</td></tr>`;
    return;
  }
  els.taskRows.innerHTML = tasks
    .map((task) => `
      <tr data-ticket-no="${escapeHtml(task.ticket_no)}">
        <td class="red-text">${escapeHtml(task.ticket_no)}</td>
        <td class="title-cell">${escapeHtml(task.title)}</td>
        <td>${escapeHtml(task.complainant_name || "-")}</td>
        <td>${escapeHtml(task.contact_phone || "需回查")}</td>
        <td>${badge(task.priority, task.priority === "优先" ? "orange" : "blue")}</td>
        <td>${list(task.missing_fields)}</td>
        <td>${list(task.recommended_supplement_fields)}</td>
        <td>${escapeHtml(task.call_script)}</td>
        <td><button class="btn secondary detail-btn" data-ticket-no="${escapeHtml(task.ticket_no)}">查看工单</button></td>
      </tr>
    `)
    .join("");
}

document.addEventListener("click", (event) => {
  const detailBtn = event.target.closest(".detail-btn");
  if (detailBtn) {
    window.location.href = `/demo/detail.html?ticket_no=${encodeURIComponent(detailBtn.dataset.ticketNo)}`;
  }
});

els.backBtn.addEventListener("click", () => {
  window.location.href = "/demo/";
});
els.refreshBtn.addEventListener("click", loadTasks);

loadTasks();
