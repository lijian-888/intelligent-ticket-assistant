const kbState = {
  offset: 0,
  lastChunkCount: 0,
};

const kbEls = {
  sourceSelect: document.getElementById("sourceSelect"),
  pathInput: document.getElementById("pathInput"),
  sourceFileInput: document.getElementById("sourceFileInput"),
  limitInput: document.getElementById("limitInput"),
  searchBtn: document.getElementById("searchBtn"),
  clearSearchBtn: document.getElementById("clearSearchBtn"),
  prevBtn: document.getElementById("prevBtn"),
  nextBtn: document.getElementById("nextBtn"),
  refreshBtn: document.getElementById("refreshBtn"),
  backBtn: document.getElementById("backBtn"),
  summaryText: document.getElementById("summaryText"),
  chunkRows: document.getElementById("chunkRows"),
};

function getLimit() {
  const value = Number(kbEls.limitInput.value || 50);
  return Math.min(Math.max(value, 1), 500);
}

async function loadChunks() {
  const source = kbEls.sourceSelect.value;
  const limit = getLimit();
  const params = new URLSearchParams({ limit: String(limit), offset: String(kbState.offset) });
  const sourceFile = kbEls.sourceFileInput.value.trim();
  if (sourceFile) {
    params.set("source_file", sourceFile);
  }
  if (source === "files") {
    params.set("path", kbEls.pathInput.value || "legalDocx");
  }
  const url = source === "files" ? `/legal-kb/preview?${params}` : `/legal-kb/chunks?${params}`;
  setLoading(true);
  try {
    const data = await api(url);
    kbState.lastChunkCount = data.chunk_count || 0;
    renderSummary(data, source);
    renderRows(data.items || [], kbState.offset);
  } catch (error) {
    showToast(`加载知识库片段失败：${error.message}`);
  } finally {
    setLoading(false);
  }
}

function renderSummary(data, source) {
  const sourceText = source === "files" ? "法规文件切片预览" : "数据库已入库片段";
  const modelText = data.embedding_models?.length ? `；向量模型：${data.embedding_models.join("，")}` : "";
  const filteredText = data.source_file_filter
    ? `，来源文件包含“${data.source_file_filter}”的片段 ${data.filtered_chunk_count || 0} 个`
    : "";
  const visibleTotal = data.source_file_filter ? data.filtered_chunk_count || 0 : data.chunk_count || 0;
  kbEls.summaryText.textContent = `${sourceText}：文档 ${data.document_count || 0} 个，片段 ${data.chunk_count || 0} 个${filteredText}，当前 ${data.offset || 0} - ${(data.offset || 0) + (data.items || []).length}${modelText}`;
  kbEls.prevBtn.disabled = kbState.offset <= 0;
  kbEls.nextBtn.disabled = kbState.offset + getLimit() >= visibleTotal;
}

function renderRows(items, offset) {
  kbEls.chunkRows.innerHTML = items.length
    ? items.map((item, index) => `
      <tr>
        <td>${offset + index + 1}</td>
        <td>${escapeHtml(item.law_name || "-")}</td>
        <td>${escapeHtml(item.chapter || "-")}</td>
        <td>${escapeHtml(item.article || "-")}</td>
        <td class="source-file-cell">${escapeHtml(fileName(item.source_file || "-"))}</td>
        <td><pre class="chunk-text">${escapeHtml(item.chunk_text || "")}</pre></td>
      </tr>
    `).join("")
    : `<tr><td colspan="6" class="empty-cell">暂无片段</td></tr>`;
}

function fileName(path) {
  return String(path).split(/[\\/]/).pop();
}

function setLoading(loading) {
  kbEls.refreshBtn.disabled = loading;
  kbEls.prevBtn.disabled = loading || kbState.offset <= 0;
  kbEls.nextBtn.disabled = loading;
  if (loading) {
    kbEls.summaryText.textContent = "正在加载知识库片段...";
  }
}

kbEls.refreshBtn.addEventListener("click", () => {
  kbState.offset = 0;
  loadChunks();
});

kbEls.searchBtn.addEventListener("click", () => {
  kbState.offset = 0;
  loadChunks();
});

kbEls.clearSearchBtn.addEventListener("click", () => {
  kbState.offset = 0;
  kbEls.sourceFileInput.value = "";
  loadChunks();
});

kbEls.sourceFileInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    kbState.offset = 0;
    loadChunks();
  }
});

kbEls.prevBtn.addEventListener("click", () => {
  kbState.offset = Math.max(0, kbState.offset - getLimit());
  loadChunks();
});

kbEls.nextBtn.addEventListener("click", () => {
  kbState.offset += getLimit();
  loadChunks();
});

kbEls.sourceSelect.addEventListener("change", () => {
  kbState.offset = 0;
  kbEls.pathInput.disabled = kbEls.sourceSelect.value === "db";
  loadChunks();
});

kbEls.backBtn.addEventListener("click", () => {
  window.location.href = "/demo/";
});

loadChunks();
