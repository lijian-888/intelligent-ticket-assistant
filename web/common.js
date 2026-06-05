function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function truncate(value, size = 90) {
  const text = String(value ?? "");
  return text.length > size ? `${text.slice(0, size)}...` : text;
}

function showToast(message) {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.remove("hidden");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.add("hidden"), 2600);
}

function badge(text, color = "gray") {
  return `<span class="badge ${color}">${escapeHtml(text || "未检测")}</span>`;
}

function statusColor(status) {
  if (status === "待流转") return "green";
  if (status === "已流转") return "green";
  if (status === "待补充") return "orange";
  if (status === "已加入补充任务") return "orange";
  if (status === "建议退单") return "red";
  if (status === "已退单") return "red";
  return "gray";
}

function riskColor(risk) {
  if (risk === "高") return "red";
  if (risk === "中") return "orange";
  if (risk === "低") return "green";
  return "gray";
}

function caseNatureColor(caseNature) {
  if (caseNature === "投诉") return "blue";
  if (caseNature === "举报") return "green";
  if (caseNature === "无法判断") return "orange";
  return "gray";
}

async function api(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = response.statusText;
    const text = await response.text();
    try {
      const body = JSON.parse(text);
      detail = body.detail || JSON.stringify(body);
    } catch (_) {
      detail = text || detail;
    }
    throw new Error(detail);
  }
  return response.json();
}

function list(items) {
  if (!items || !items.length) return "<span class='muted'>无</span>";
  return `<ul class="compact">${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function getExecutedAction(result) {
  if (result?.automation_mode !== "auto_executed") return null;
  return (result.actions || []).find((action) => action.executed) || null;
}

function executedActionLabel(result) {
  const action = getExecutedAction(result);
  if (!action) return "";
  if (action.tool === "transfer_ticket") return "已流转";
  if (action.tool === "return_ticket") return "已退单";
  if (action.tool === "write_back_ticket") return "已加入补充任务";
  return "已执行";
}

function resultStatusLabel(result) {
  return executedActionLabel(result) || result?.status || "未检测";
}

function executedButtonClass(result) {
  const action = getExecutedAction(result);
  if (!action) return "primary";
  if (action.tool === "transfer_ticket") return "success";
  if (action.tool === "return_ticket") return "danger";
  if (action.tool === "write_back_ticket") return "warning";
  return "secondary";
}

function autoExecutionMessage(result) {
  const action = getExecutedAction(result);
  if (!action) return "";
  if (action.tool === "transfer_ticket") {
    return `工单 ${result.ticket_no} 已自动流转至：${action.target_branch || result.recommended_branch || "建议承办单位"}`;
  }
  if (action.tool === "return_ticket") {
    return `工单 ${result.ticket_no} 已自动退单。退单原因：${action.reason || result.return_reason || "-"}`;
  }
  if (action.tool === "write_back_ticket") {
    return `工单 ${result.ticket_no} 已自动加入补充核心字段任务表。缺失字段：${(result.missing_fields || []).join("、") || "-"}`;
  }
  return `工单 ${result.ticket_no} 已自动执行：${action.tool}`;
}

function notifyAutoExecution(result) {
  const message = autoExecutionMessage(result);
  if (!message) return;
  showToast(message);
  window.setTimeout(() => window.alert(message), 80);
}

function detailPair(label, value, wide = false) {
  return `
    <div class="detail-label">${escapeHtml(label)}：</div>
    <div class="detail-value ${wide ? "detail-wide" : ""}">${escapeHtml(value || "")}</div>`;
}

function renderDetail(ticket) {
  return `
    <div class="detail-header-row">
      ${detailPair("标题", ticket.title, true)}
    </div>
    <div class="detail-header-row">
      ${detailPair("工单内容", ticket.content, true)}
    </div>
    <div class="detail-row">
      ${detailPair("工单编号", ticket.ticket_no)}
      ${detailPair("工单状态", ticket.status)}
      ${detailPair("工单类型", ticket.ticket_type)}
      ${detailPair("渠道", ticket.channel)}
      ${detailPair("紧急程度", ticket.urgency)}
      ${detailPair("来电号码", ticket.caller_phone)}
      ${detailPair("客户姓名", ticket.customer_name)}
      ${detailPair("客户性别", ticket.customer_gender)}
      ${detailPair("联系号码", ticket.contact_phone)}
      ${detailPair("一级业务类型", ticket.business_type_l1)}
      ${detailPair("二级业务类型", ticket.business_type_l2)}
      ${detailPair("三级业务类型", ticket.business_type_l3)}
      ${detailPair("四级业务类型", ticket.business_type_l4)}
      ${detailPair("年龄范围", ticket.age_range)}
      ${detailPair("来源", ticket.source)}
      ${detailPair("创建时间", ticket.created_at)}
      ${detailPair("计划完成时间", ticket.due_at)}
      ${detailPair("诉求时间", ticket.appeal_at)}
      ${detailPair("所属区域", ticket.region)}
      ${detailPair("归属地地址", ticket.domicile_address)}
      ${detailPair("经纬度", ticket.longitude_latitude)}
      ${detailPair("诉求情绪", ticket.appeal_emotion)}
      ${detailPair("诉求次数", ticket.appeal_count ?? "")}
      ${detailPair("诉求目的", ticket.appeal_purpose)}
      ${detailPair("证件类型", ticket.id_type)}
      ${detailPair("证件号", ticket.id_no)}
      ${detailPair("公开客户信息", ticket.public_customer_info)}
      ${detailPair("事发时间", ticket.incident_at)}
      ${detailPair("事发地址", ticket.incident_address)}
      ${detailPair("第三方任务单编号", ticket.third_party_ticket_no)}
    </div>
    <div class="detail-row">
      <div class="detail-label">附件：</div>
      <div class="detail-value detail-wide">
        ${(ticket.attachments || []).length
          ? ticket.attachments.map((name) => `<span class="attachment">${escapeHtml(name)}</span>`).join("，")
          : '<span class="attachment">附件</span>'}
      </div>
    </div>
  `;
}

function renderAiResultHtml(result) {
  return `
    ${renderDecisionCard(result)}
    ${renderAutomationCard(result)}
    ${renderStructureCard(result)}
    ${renderLegalReferenceCard(result)}
    ${renderRiskCard(result)}
    ${renderOperationCard(result)}
  `;
}

function renderDecisionCard(result) {
  const displayStatus = resultStatusLabel(result);
  return `
    <div class="result-card">
      <h3>处理结论</h3>
      <div class="kv">
        <div class="key">状态</div><div>${badge(displayStatus, statusColor(displayStatus))}</div>
        <div class="key">工单性质</div><div>${escapeHtml(result.structured.case_nature)}（${escapeHtml(result.structured.case_nature_source)}）</div>
        <div class="key">职责判断</div><div>${escapeHtml(result.jurisdiction || "-")}</div>
        <div class="key">建议承办单位</div><div>${escapeHtml(result.recommended_branch || "-")}</div>
        <div class="key">退单原因</div><div>${escapeHtml(result.return_reason || "-")}</div>
      </div>
    </div>`;
}

function renderAutomationCard(result) {
  const modeText = result.automation_mode === "auto_executed" ? "已自动执行" : "需人工确认";
  const color = result.automation_mode === "auto_executed" ? "green" : "orange";
  const confidence = Number(result.automation_confidence || 0).toFixed(2);
  return `
    <div class="result-card">
      <h3>智能流转</h3>
      <div class="kv">
        <div class="key">执行模式</div><div>${badge(modeText, color)}</div>
        <div class="key">置信度</div><div>${escapeHtml(confidence)}</div>
        <div class="key">说明</div><div>${escapeHtml(result.automation_reason || "-")}</div>
      </div>
    </div>`;
}

function renderStructureCard(result) {
  const s = result.structured;
  return `
    <div class="result-card">
      <h3>结构化信息</h3>
      <div class="kv">
        <div class="key">提交人</div><div>${escapeHtml(s.complainant_name || "-")}</div>
        <div class="key">联系电话</div><div>${escapeHtml(s.contact_phone || "-")}</div>
        <div class="key">事发地址</div><div>${escapeHtml(s.incident_address || "-")}</div>
        <div class="key">所属区域</div><div>${escapeHtml(s.region || "-")}</div>
        <div class="key">对象名称</div><div>${escapeHtml(s.respondent || "-")}</div>
        <div class="key">诉求</div><div>${escapeHtml(s.appeal || "-")}</div>
        <div class="key">金额</div><div>${s.amount ?? "-"}</div>
        <div class="key">关键词</div><div>${escapeHtml((s.keywords || []).join("，") || "-")}</div>
        <div class="key">缺失字段</div><div>${list(result.missing_fields)}</div>
        <div class="key">建议核实</div><div>${list(result.recommended_supplement_fields)}</div>
      </div>
    </div>`;
}

function renderRiskCard(result) {
  return `
    <div class="result-card">
      <h3>风险提示</h3>
      <div class="kv">
        <div class="key">情绪等级</div><div>${badge(result.emotion_level, riskColor(result.emotion_level))}</div>
        <div class="key">调解建议</div><div>${escapeHtml(result.mediation_advice || "-")}</div>
        <div class="key">职业索赔</div><div>${badge(result.professional_claimant_risk, riskColor(result.professional_claimant_risk))}</div>
        <div class="key">风险原因</div><div>${list(result.professional_claimant_reasons)}</div>
      </div>
    </div>`;
}

function renderLegalReferenceCard(result) {
  const references = result.legal_references || [];
  const content = references.length
    ? `<ul class="legal-list">${references.map((item) => `
        <li>
          <div class="legal-title">${escapeHtml(item.law_name)} ${escapeHtml(item.article)}</div>
          <div>${escapeHtml(item.excerpt || "-")}</div>
          <div class="muted">检索方式：${escapeHtml(item.retrieval_method || "vector")}；向量模型：${escapeHtml(item.embedding_model || "-")}；重排模型：${escapeHtml(item.reranker_model || "-")}</div>
          <div class="muted">最终分数：${Number(item.relevance_score || 0).toFixed(2)}；向量分数：${Number(item.vector_score || 0).toFixed(2)}；重排分数：${Number(item.rerank_score || 0).toFixed(2)}</div>
          <div class="muted">知识库编号：${escapeHtml(item.source_id || "-")}</div>
          <div class="muted">参考原因：${escapeHtml(item.reason || "-")}</div>
        </li>
      `).join("")}</ul>`
    : "<span class='muted'>无相关法律条款达到当前分数要求。</span>";
  return `
    <div class="result-card">
      <h3>法律条款参考</h3>
      ${content}
    </div>`;
}

function renderOperationCard(result) {
  const buttons = [];
  const autoExecuted = result.automation_mode === "auto_executed";
  if (autoExecuted) {
    buttons.push(`<button class="btn ${executedButtonClass(result)}" disabled>${escapeHtml(executedActionLabel(result))}</button>`);
  }
  if (!autoExecuted && (result.missing_fields || []).length > 0) {
    buttons.push(`<button class="btn warning op-supplement" data-ticket-no="${escapeHtml(result.ticket_no)}">生成补充核心信息任务</button>`);
  }
  if (!autoExecuted && result.status === "建议退单") {
    buttons.push(`<button class="btn danger op-return" data-ticket-no="${escapeHtml(result.ticket_no)}">确认退单</button>`);
  }
  if (!autoExecuted && result.status === "待流转" && !(result.missing_fields || []).length) {
    buttons.push(`<button class="btn success op-transfer" data-ticket-no="${escapeHtml(result.ticket_no)}">流转至${escapeHtml(result.recommended_branch || "建议承办单位")}</button>`);
  }

  const note = autoExecuted
    ? "置信度达到自动执行阈值，系统已模拟调用对应接口。"
    : (result.missing_fields || []).length > 0
    ? "存在核心字段缺失，应先生成补充任务并电话核实；demo 阶段不真实提交。"
    : ((result.actions || [])[0]?.note || "demo 阶段只演示操作，不真实提交。");

  return `
    <div class="result-card">
      <h3>后续操作</h3>
      <div class="kv">
        <div class="key">建议动作</div><div>${escapeHtml((result.actions || []).map((item) => item.tool).join("，") || "-")}</div>
        <div class="key">说明</div><div>${escapeHtml(note)}</div>
      </div>
      <div class="action-bar">${buttons.join("")}</div>
    </div>`;
}
