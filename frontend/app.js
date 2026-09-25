/* 事故导排网络校核前端：草稿编辑、审计提交、结论（含过期历史）展示。 */
(function () {
  "use strict";

  const nodeTbody = document.querySelector("#node-table tbody");
  const pipeTbody = document.querySelector("#pipe-table tbody");
  const requiredInput = document.getElementById("required-flow");
  const draftState = document.getElementById("draft-state");
  const auditState = document.getElementById("audit-state");
  const staleBanner = document.getElementById("stale-banner");
  const resultEmpty = document.getElementById("result-empty");
  const resultBody = document.getElementById("result-body");
  const inputMsg = document.getElementById("input-msg");

  let lastAudit = null; // 最近一次审计结论（可能已过期）
  let dirty = false;

  // ---------- 草稿行 ----------
  function addNodeRow(node) {
    const tr = document.createElement("tr");
    tr.className = "node-row";
    tr.innerHTML =
      '<td class="seq"></td>' +
      '<td><input class="n-id" /></td>' +
      '<td><select class="n-kind">' +
        '<option value="junction">汇合节点</option>' +
        '<option value="source">泄压源</option>' +
        '<option value="sink">安全焚烧端</option>' +
      "</select></td>" +
      '<td><input class="n-label" placeholder="可选" /></td>' +
      '<td><button type="button" class="btn btn-danger btn-del">删除</button></td>';
    tr.querySelector(".n-id").value = node?.id || "";
    tr.querySelector(".n-kind").value = node?.kind || "junction";
    tr.querySelector(".n-label").value = node?.label || "";
    tr.querySelector(".btn-del").addEventListener("click", () => {
      tr.remove();
      markDirty();
      refreshPipeNodeOptions();
      renumber();
    });
    tr.querySelectorAll("input,select").forEach((el) =>
      el.addEventListener("input", () => { markDirty(); refreshPipeNodeOptions(); })
    );
    nodeTbody.appendChild(tr);
    renumber();
    refreshPipeNodeOptions();
  }

  function addPipeRow(pipe) {
    const tr = document.createElement("tr");
    tr.className = "pipe-row";
    tr.innerHTML =
      '<td class="seq"></td>' +
      '<td><input class="p-id" /></td>' +
      '<td><select class="p-source"></select></td>' +
      '<td><select class="p-target"></select></td>' +
      '<td><input class="p-cap" type="number" min="1" step="1" /></td>' +
      '<td style="text-align:center"><input class="p-maint" type="checkbox" checked /></td>' +
      '<td><button type="button" class="btn btn-danger btn-del">删除</button></td>';
    tr.querySelector(".p-id").value = pipe?.id || "";
    tr.querySelector(".p-cap").value = pipe?.capacity ?? "";
    tr.querySelector(".p-maint").checked = pipe ? !!pipe.maintainable : true;
    tr.querySelector(".btn-del").addEventListener("click", () => {
      tr.remove();
      markDirty();
      renumber();
    });
    tr.querySelectorAll("input,select").forEach((el) =>
      el.addEventListener("input", markDirty)
    );
    pipeTbody.appendChild(tr);
    fillPipeNodeOptions(tr);
    if (pipe) {
      tr.querySelector(".p-source").value = pipe.source;
      tr.querySelector(".p-target").value = pipe.target;
    }
    renumber();
  }

  function nodeIds() {
    return [...nodeTbody.querySelectorAll(".node-row")]
      .map((r) => r.querySelector(".n-id").value.trim())
      .filter(Boolean);
  }

  function fillPipeNodeOptions(tr) {
    const ids = nodeIds();
    [".p-source", ".p-target"].forEach((selCls) => {
      const sel = tr.querySelector(selCls);
      const current = sel.value;
      sel.innerHTML =
        '<option value="">—</option>' +
        ids.map((id) => `<option value="${escapeHtml(id)}">${escapeHtml(id)}</option>`).join("");
      if (ids.includes(current)) sel.value = current;
    });
  }

  function refreshPipeNodeOptions() {
    pipeTbody.querySelectorAll(".pipe-row").forEach(fillPipeNodeOptions);
  }

  function renumber() {
    nodeTbody.querySelectorAll(".node-row").forEach((r, i) => {
      r.querySelector(".seq").textContent = i + 1;
    });
    pipeTbody.querySelectorAll(".pipe-row").forEach((r, i) => {
      r.querySelector(".seq").textContent = i + 1;
    });
  }

  // ---------- 序列化 ----------
  function collectDraft() {
    return {
      required_flow: parseInt(requiredInput.value, 10),
      nodes: [...nodeTbody.querySelectorAll(".node-row")].map((r) => ({
        id: r.querySelector(".n-id").value.trim(),
        kind: r.querySelector(".n-kind").value,
        label: r.querySelector(".n-label").value.trim(),
      })),
      pipes: [...pipeTbody.querySelectorAll(".pipe-row")].map((r) => ({
        id: r.querySelector(".p-id").value.trim(),
        source: r.querySelector(".p-source").value,
        target: r.querySelector(".p-target").value,
        capacity: parseInt(r.querySelector(".p-cap").value, 10),
        maintainable: r.querySelector(".p-maint").checked,
      })),
    };
  }

  function loadDraft(draft) {
    if (!draft) return;
    requiredInput.value = draft.required_flow ?? "";
    nodeTbody.innerHTML = "";
    pipeTbody.innerHTML = "";
    (draft.nodes || []).forEach(addNodeRow);
    (draft.pipes || []).forEach(addPipeRow);
    renumber();
  }

  // ---------- 结论渲染 ----------
  function renderAudit(audit) {
    lastAudit = audit;
    resultEmpty.hidden = !!audit;
    resultBody.hidden = !audit;
    staleBanner.hidden = !(audit && audit.stale);

    if (!audit) {
      auditState.textContent = "尚未审计";
      auditState.className = "tag tag-muted";
      return;
    }

    const map = {
      passed: ["放行通过", "tag-pass"],
      failed: ["校核失败 · 不予放行", "tag-fail"],
      rejected: ["输入无效 · 拒绝审计", "tag-reject"],
    };
    const [label, cls] = map[audit.status] || map.rejected;
    auditState.textContent = label + (audit.stale ? "（已过期）" : "");
    auditState.className = "tag " + cls;

    let html = "";
    if (audit.status === "rejected") {
      html += `<div class="verdict reject">审计被拒绝：方向、容量或节点引用存在 ${
        audit.errors.length} 处无效输入，未进行任何流量计算。</div>`;
      html += '<ul class="error-list">' +
        audit.errors.map((e) => `<li>${escapeHtml(e)}</li>`).join("") + "</ul>";
    } else {
      const passed = audit.status === "passed";
      html += `<div class="verdict ${passed ? "pass" : "fail"}">${
        passed
          ? `✓ 全部 ${audit.scenarios.length} 种情形（正常网络 + 单管段失效）最大可导排量均不低于事故必须流量 ${audit.required_flow}，准予检修放行。`
          : "✗ 存在不达标情形，不予放行。"
      }</div>`;

      if (!passed && audit.failure) html += evidenceHtml(audit.failure, audit.required_flow);
      html += scenariosTable(audit.scenarios);
    }

    resultBody.innerHTML = html;
  }

  function evidenceHtml(f, required) {
    const title = f.case === "normal"
      ? "正常网络即不达标"
      : `首条失效管段（按录入顺序）：#${f.pipe_seq} ${escapeHtml(f.pipe_id)}`;
    return (
      '<div class="evidence"><h4>失败证据（可独立复核）</h4>' +
      `<dl>
        <dt>失效情形</dt><dd>${title}</dd>
        <dt>必须持续排出</dt><dd class="mono">${required}</dd>
        <dt>最大可导排量</dt><dd class="mono bad">${f.max_flow}（缺口 ${f.shortfall}）</dd>
        <dt>源侧割集节点</dt><dd class="mono">${f.source_cut.map(escapeHtml).join("、") || "（空）"}</dd>
        <dt>焚烧端侧节点</dt><dd class="mono">${f.sink_side.map(escapeHtml).join("、") || "（空）"}</dd>
        <dt>割集管段（S→T）</dt><dd class="mono">${f.cut_edges.map(escapeHtml).join("、") || "（无跨越边）"}</dd>
        <dt>该割集容量</dt><dd class="mono bad">${f.cut_capacity}</dd>
      </dl></div>`
    );
  }

  function scenariosTable(scenarios) {
    const rows = scenarios.map((s) => {
      const name = s.case === "normal"
        ? "正常网络"
        : `#${s.pipe_seq} ${escapeHtml(s.pipe_id)} 临时失效`;
      return `<tr class="${s.satisfies ? "" : "badrow"}">
        <td>${name}</td>
        <td class="flow-num">${s.max_flow}</td>
        <td>${s.required_flow}</td>
        <td>${s.satisfies ? '<span class="good">达标</span>' : '<span class="bad">不达标</span>'}</td>
        <td class="mono">${s.cut_edges.map(escapeHtml).join("、") || "—"}</td>
        <td class="flow-num">${s.cut_capacity}</td>
      </tr>`;
    }).join("");
    return `<h3>逐情形最大可导排量（服务端独立计算）</h3>
      <table class="case-table">
        <thead><tr><th>情形</th><th>最大流</th><th>必须流量</th><th>结论</th><th>最小割管段</th><th>割集容量</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  // ---------- 交互 ----------
  function markDirty() {
    dirty = true;
    draftState.textContent = "未保存的修改";
    draftState.className = "tag tag-fail";
    if (lastAudit && !lastAudit.stale) {
      // 草稿一改，当前结论立刻在界面上转为“历史结论（已过期）”
      lastAudit.stale = true;
      staleBanner.hidden = false;
      auditState.textContent = auditState.textContent.replace(/（已过期）$/, "") + "（已过期）";
    }
  }

  function flash(msg, ok) {
    inputMsg.textContent = msg;
    inputMsg.className = "input-msg " + (ok ? "ok" : "err");
  }

  async function saveDraft() {
    const resp = await fetch("/api/draft", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collectDraft()),
    });
    if (!resp.ok) { flash("草稿保存失败", false); return; }
    dirty = false;
    draftState.textContent = "草稿已保存";
    draftState.className = "tag tag-muted";
    flash("草稿已保存，可继续修改后重新审计。", true);
  }

  async function submitAudit() {
    const draft = collectDraft();
    // 保存草稿，保证旧结论与新草稿的过期关系由服务端指纹判定
    await fetch("/api/draft", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(draft),
    });
    const resp = await fetch("/api/audit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(draft),
    });
    const body = await resp.json();
    body.stale = false; // 刚提交，结论必然对应当前草稿
    renderAudit(body);
    dirty = false;
    draftState.textContent = "草稿已保存";
    draftState.className = "tag tag-muted";
    flash("", true);
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function loadExample() {
    loadDraft({
      required_flow: 6,
      nodes: [
        { id: "SRC", kind: "source", label: "泄压源" },
        { id: "J1", kind: "junction", label: "汇合节点1" },
        { id: "J2", kind: "junction", label: "汇合节点2" },
        { id: "INC", kind: "sink", label: "安全焚烧端" },
      ],
      pipes: [
        { id: "P1", source: "SRC", target: "J1", capacity: 8, maintainable: true },
        { id: "P2", source: "SRC", target: "J2", capacity: 6, maintainable: true },
        { id: "P3", source: "J1", target: "INC", capacity: 6, maintainable: true },
        { id: "P4", source: "J2", target: "INC", capacity: 6, maintainable: true },
        { id: "P5", source: "J1", target: "J2", capacity: 6, maintainable: false },
      ],
    });
    markDirty();
    flash("已载入示例网络，提交审计查看逐情形结果。", true);
  }

  document.getElementById("add-node").addEventListener("click", () => addNodeRow());
  document.getElementById("add-pipe").addEventListener("click", () => addPipeRow());
  document.getElementById("save-draft").addEventListener("click", saveDraft);
  document.getElementById("submit-audit").addEventListener("click", submitAudit);
  document.getElementById("load-example").addEventListener("click", loadExample);
  requiredInput.addEventListener("input", markDirty);

  // 启动：恢复服务端草稿与最近审计结论（含过期标记）
  (async function init() {
    try {
      const resp = await fetch("/api/draft");
      const state = await resp.json();
      if (state.draft) {
        loadDraft(state.draft);
        draftState.textContent = "草稿已保存";
        draftState.className = "tag tag-muted";
        dirty = false;
        renderAudit(state.audit);
      } else {
        loadExample();
        inputMsg.textContent = "";
        inputMsg.className = "input-msg";
      }
    } catch (e) {
      loadExample();
    }
  })();
})();
