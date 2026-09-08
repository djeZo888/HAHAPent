"use strict";

// Catalog content is untrusted. Only textContent/DOM nodes render remote text.
const $ = (id) => document.getElementById(id);
const el = (tag, text = "", className = "") => {
  const node = document.createElement(tag);
  node.textContent = String(text ?? "");
  if (className) node.className = className;
  return node;
};
const state = { data: null, view: "catalog", busy: false };
const labels = {
  refresh: "Refreshing catalogs", source_add: "Adding trusted source",
  source_remove: "Removing source", test_mode: "Updating test catalog setting",
  install: "Installing selected version", rollback: "Rolling back owned code",
  remove: "Removing owned code",
};

async function api(path, body) {
  const options = { credentials: "same-origin", cache: "no-store" };
  if (body !== undefined) {
    options.method = "POST";
    options.headers = { "Content-Type": "application/json", "X-HAHAPent-Request": "1" };
    options.body = JSON.stringify(body);
  }
  const response = await fetch(`./api/${path}`, options);
  let result;
  try { result = await response.json(); }
  catch { throw new Error("Suite Manager is unavailable. Reopen it from Home Assistant."); }
  if (!response.ok) throw new Error(result.error?.message || "The request could not be completed.");
  return result;
}

function notice(message, error = false) {
  $("notice").textContent = message;
  $("notice").className = error ? "notice error" : "notice";
  $("notice").hidden = !message;
}

function showJob(job) {
  state.busy = job?.state === "running";
  $("operation").hidden = !job || job.state === "idle";
  if (!job || job.state === "idle") return;
  $("operation-title").textContent = labels[job.operation] || "Suite operation";
  $("operation-state").textContent = ({running: "In progress", complete: "Complete", failed: "Blocked"})[job.state] || job.state;
  $("operation-progress").hidden = !state.busy;
  $("operation-detail").textContent = job.state === "failed"
    ? (job.error?.message || "The operation failed. Review recovery status.")
    : state.busy ? "Validation, download and file changes can take a moment. Keep this view open for the result."
      : "Files and settings checked. Review installed status for the next step.";
  if (state.busy && job.phase) {
    const phases = {downloading: "Downloading and validating the selected artifact…", staging: "Staging validated files…", backing_up: "Backing up current owned code…", prepared: "Preparing a recoverable transaction…", staged: "Validating the staged replacement…", old_moved: "Replacing owned code…", new_moved: "Saving installed ownership…", committed: "Completing the transaction…", complete: "Checking final status…"};
    $("operation-detail").textContent = phases[job.phase] || $("operation-detail").textContent;
  }
}

async function reload() {
  const data = await api("status");
  state.data = data;
  showJob(data.job);
  render();
  $("connection").textContent = "Administrator verified";
  $("connection").className = "badge";
}

async function poll() {
  try {
    const result = await api("job");
    showJob(result.job);
    if (state.busy) setTimeout(poll, 1200);
    else {
      await reload();
      if (result.job?.state === "failed") notice(result.job.error?.message || "Operation failed.", true);
    }
  } catch (error) {
    state.busy = false;
    notice(error.message, true);
    $("connection").textContent = "Connection unavailable";
    $("connection").className = "badge warning";
    if (state.data) render();
  }
}

async function perform(operation, body = {}) {
  notice("");
  try {
    const result = await api(operation, body);
    showJob(result.job);
    render();
    setTimeout(poll, 200);
  } catch (error) { notice(error.message, true); if (state.data) render(); }
}

function confirmation(title, detail, action, danger = false) {
  return new Promise((resolve) => {
    $("confirm-title").textContent = title;
    $("confirm-detail").textContent = detail;
    $("confirm-action").textContent = action;
    $("confirm-action").className = danger ? "danger" : "";
    const dialog = $("confirm-dialog");
    dialog.returnValue = "cancel";
    dialog.addEventListener("close", () => resolve(dialog.returnValue === "confirm"), { once: true });
    dialog.showModal();
  });
}

function button(label, callback, style = "", disabled = false) {
  const node = el("button", label, style);
  node.type = "button";
  node.disabled = state.busy || disabled;
  node.addEventListener("click", callback);
  return node;
}

function link(label, href, native = false) {
  const node = el("a", label);
  if (native) {
    if (!href.startsWith("/config/")) return el("span", label);
    node.href = href;
    node.target = "_top";
  } else {
    try {
      const url = new URL(href);
      if (url.protocol !== "https:" || url.username || url.password) return el("span", label);
      node.href = url.href;
      node.target = "_blank";
      node.rel = "noopener noreferrer";
    } catch { return el("span", label); }
  }
  return node;
}

function details(rows) {
  const list = el("dl", "", "details");
  for (const [key, value] of rows) list.append(el("dt", key), el("dd", value));
  return list;
}

function empty(container, title, message) {
  const node = el("div", "", "empty");
  node.append(el("div", "◇", "empty-icon"), el("h3", title), el("p", message));
  container.append(node);
}

function installedRows() {
  const rows = state.data?.installed || [];
  return Array.isArray(rows) ? rows : Object.entries(rows).map(([domain, row]) => ({integration_domain: domain, ...row}));
}

function domainOf(row) { return row.integration_domain || row.domain; }
function versionOf(row) { return row.version || row.installed_version; }
function versionSort(a, b) { return b.version.localeCompare(a.version, undefined, { numeric: true }); }
function nativeConfigLink(domain, configured) {
  return link(configured ? "Manage in HA ↗" : "Configure in HA ↗", configured
    ? "/config/integrations/dashboard"
    : `/config/integrations/dashboard/add?domain=${encodeURIComponent(domain)}`, true);
}

function catalogCard(versions) {
  versions.sort(versionSort);
  const latest = versions[0];
  const domain = domainOf(latest);
  const owned = installedRows().find((item) => domainOf(item) === domain);
  const card = el("article", "", "card");
  const top = el("div", "", "card-top");
  const heading = el("div");
  heading.append(el("h3", latest.name || latest.id), el("div", domain, "module-domain"));
  top.append(heading, el("span", owned ? "Installed" : "Available", `badge ${owned ? "" : "neutral"}`));
  card.append(top, el("p", latest.description || "No description supplied."));
  const compatibility = typeof latest.compatibility === "boolean" ? latest.compatibility
    : latest.compatibility?.compatible ?? latest.compatible;
  const compatLabel = compatibility === true ? "Compatible" : compatibility === false ? "Incompatible" : "Checked before install";
  card.append(details([
    ["Source", latest.source_id], ["Installed", owned ? versionOf(owned) : "—"],
    ["Latest available", latest.version], ["Home Assistant", compatLabel],
  ]));
  const picker = el("div", "", "version-picker");
  const label = el("label", "Version");
  const select = el("select");
  select.setAttribute("aria-label", `Version of ${latest.name || latest.id}`);
  for (const item of versions) {
    const option = el("option", item.version);
    option.value = item.version;
    select.append(option);
  }
  picker.append(label, select);
  card.append(picker);
  const requirements = el("div");
  card.append(requirements);
  const actions = el("div", "", "card-actions");
  const install = button(owned ? "Update" : "Install", async () => {
    const target = versions.find((item) => item.version === select.value);
    const verb = owned ? "Update" : "Install";
    if (await confirmation(`${verb} ${latest.name || latest.id}?`,
      `Install version ${target.version} from ${target.source_id}. Only this integration’s owned code will change. A Home Assistant restart may be needed.`, verb)) {
      await perform("install", {source_id: target.source_id, module_id: target.id, version: target.version});
    }
  });
  const updateButton = () => {
    const target = versions.find((item) => item.version === select.value);
    const allowed = typeof target.compatibility === "boolean" ? target.compatibility
      : target.compatibility?.compatible ?? target.compatible;
    install.disabled = state.busy || (owned && versionOf(owned) === target.version) || allowed === false;
    install.textContent = owned && versionOf(owned) === target.version ? "Installed" : owned ? "Update" : "Install";
    const haRange = target.home_assistant || {};
    requirements.replaceChildren(details([
      ["Required HA", `${haRange.min_version || "Unknown"}${haRange.max_version_exclusive ? ` to below ${haRange.max_version_exclusive}` : " or later"}`],
      ["Required Manager", `${target.minimum_manager_version || "0.1.0"} or later`],
      ["Dependencies", (target.dependencies || []).map((dependency) => `${dependency.source_id}/${dependency.module_id} ${dependency.version}`).join(", ") || "None"],
    ]));
  };
  select.addEventListener("change", updateButton);
  updateButton();
  actions.append(install);
  if (latest.documentation_url) actions.append(link("Documentation ↗", latest.documentation_url));
  card.append(actions);
  return card;
}

function renderCatalog() {
  const container = $("catalog");
  container.replaceChildren();
  const query = $("search").value.toLowerCase().trim();
  const groups = new Map();
  for (const row of state.data.modules || []) {
    if (query && ![row.name, row.id, row.description, row.source_id, domainOf(row)].join(" ").toLowerCase().includes(query)) continue;
    const key = `${row.source_id}/${row.id}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  }
  for (const versions of groups.values()) container.append(catalogCard(versions));
  $("catalog-count").textContent = new Set((state.data.modules || []).map((row) => `${row.source_id}/${row.id}`)).size;
  if (!groups.size) empty(container, query ? "No matching integrations" : "Your suite starts here", query
    ? "Try a different name, source or description."
    : "There are no released integrations in the normal catalog yet. Trusted sources and the device-free test catalog are available under Sources.");
}

function renderInstalled() {
  const container = $("installed");
  container.replaceChildren();
  const rows = installedRows();
  const removedRows = state.data.recovery?.removed || [];
  $("installed-count").textContent = rows.length;
  $("restart-banner").hidden = !rows.some((row) => row.restart_pending)
    && !removedRows.some((row) => row.restart_pending)
    && !(state.data.operation?.action === "remove" && state.data.operation?.restart_pending);
  for (const row of rows) {
    const domain = domainOf(row);
    const card = el("article", "", "card");
    const top = el("div", "", "card-top");
    const heading = el("div");
    heading.append(el("h3", row.name || row.module?.name || row.module_id || row.id || domain), el("div", domain, "module-domain"));
    top.append(heading, el("span", row.restart_pending ? "Restart pending" : "Files installed", `badge ${row.restart_pending ? "warning" : ""}`));
    const runtime = row.runtime || row;
    const configured = row.configured ?? runtime.configured;
    card.append(top, details([
      ["Installed version", versionOf(row)], ["Source", row.source_id || row.source?.id || "Retained ownership"],
      ["HA configuration", configured === true ? "Configured" : configured === false ? "Not configured" : "Unavailable"],
      ["Running version", runtime.loaded_version || "Not verified"],
      ["Recovery", row.rollback_available ? "Previous code version available" : "No previous code version"],
    ]));
    const actions = el("div", "", "card-actions");
    actions.append(button("Roll back", async () => {
      if (await confirmation("Roll back integration code?", "Restore the previous owned code version. Code rollback cannot undo Home Assistant configuration migrations or device settings. Review compatibility and recovery before proceeding.", "Roll back"))
        await perform("rollback", {domain, confirmed: true});
    }, "secondary", !row.rollback_available));
    actions.append(button("Uninstall", async () => {
      if (await confirmation("Uninstall owned integration code?", "Remove this integration’s configuration entry in Home Assistant first. Only Suite Manager’s owned code is removed; unrelated files and user configuration are preserved. A backup is retained.", "Uninstall", true))
        await perform("remove", {domain, confirmed: true});
    }, "secondary"));
    actions.append(nativeConfigLink(domain, configured === true));
    card.append(actions);
    if (configured === true) card.append(el("p", "Before uninstalling, use Manage in HA to delete this integration’s config entry.", "muted"));
    container.append(card);
  }
  for (const removed of removedRows) {
    const card = el("article", "", "card");
    card.append(el("h3", removed.domain), el("span", "Code removed · backup retained", "badge neutral"));
    card.append(el("p", `Version ${removed.version} is available for code recovery. Restoring code does not restore Home Assistant configuration.`));
    if (removed.restart_pending) card.append(el("p", "Core restart not verified. This conservative reminder persists with the retained backup, including after the Manager restarts.", "muted"));
    card.append(button("Restore removed code", async () => {
      if (await confirmation("Restore removed code?", "Reinstall the retained owned code backup. Home Assistant configuration remains unchanged. Code rollback cannot undo configuration migrations or device settings.", "Restore code"))
        await perform("rollback", {domain: removed.domain, confirmed: true});
    }, "secondary", !removed.rollback_available));
    container.append(card);
  }
  if (!rows.length) empty(container, "No integrations installed", "Install an integration from the catalog. Configuration uses Home Assistant’s native setup flow.");
}

function renderSources() {
  const container = $("sources");
  container.replaceChildren();
  const rows = state.data.sources || [];
  for (const source of (Array.isArray(rows) ? rows : Object.values(rows))) {
    const id = source.source_id || source.id;
    const row = el("article", "", "source-row");
    const description = el("div");
    description.append(el("strong", source.name || id), el("p", source.repository_url || source.repository || "Bundled HAHAPent catalog"));
    const actions = el("div", "", "source-actions");
    const unavailable = source.available === false || source.status === "offline" || !!source.error;
    actions.append(el("span", unavailable ? "Unavailable · installed code retained" : source.status || "Available", `badge ${unavailable ? "warning" : ""}`));
    const extras = state.data.settings?.extra_repositories || [];
    if (extras.some((extra) => (extra.source_id || extra.id) === id)) {
      actions.append(button("Remove source", async () => {
        if (await confirmation("Remove this catalog source?", "The repository will no longer supply catalog updates. Installed integration code and its recovery records stay in place.", "Remove source"))
          await perform("source_remove", {source_id: id});
      }, "secondary"));
    }
    row.append(description, actions);
    container.append(row);
  }
  $("test-mode").checked = !!(state.data.settings?.test_mode || state.data.settings?.test_catalog_enabled);
  $("test-mode").disabled = state.busy;
  $("source-form").querySelector("button").disabled = state.busy;
}

function render() {
  if (!state.data) return;
  renderCatalog();
  renderInstalled();
  renderSources();
  $("refresh").disabled = state.busy;
  const version = state.data.manager_version || state.data.version;
  $("version").textContent = `HAHAPent Suite Manager${version ? ` · ${version}` : ""}${state.data.core_version ? ` / Core ${state.data.core_version}` : ""}`;
  const recovery = state.data.recovery;
  if (recovery?.state === "required") notice("Recovery needs attention. No further file changes will be made until the recorded transaction is resolved.", true);
}

for (const view of ["catalog", "installed", "sources"]) {
  $(`tab-${view}`).addEventListener("click", () => {
    state.view = view;
    for (const item of ["catalog", "installed", "sources"]) {
      $(`view-${item}`).hidden = item !== view;
      $(`tab-${item}`).classList.toggle("active", item === view);
      $(`tab-${item}`).setAttribute("aria-selected", String(item === view));
    }
    // Native HA configuration may have changed while the user was away.
    if (view === "installed" && !state.busy) reload().catch((error) => notice(error.message, true));
  });
}
$("search").addEventListener("input", () => { if (state.data) renderCatalog(); });
$("refresh").addEventListener("click", () => perform("refresh"));
$("source-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!$("source-trust").checked) return;
  const repository = $("repository").value.trim();
  if (await confirmation("Trust this repository?", `${repository} will be allowed to supply executable integration packages. Adding it does not install code.`, "Add trusted source")) {
    await perform("source_add", {repository_url: repository, trusted: true});
    $("repository").value = "";
    $("source-trust").checked = false;
  }
});
$("test-mode").addEventListener("change", () => perform("test_mode", {enabled: $("test-mode").checked}));
reload().then(() => { if (state.busy) poll(); }).catch((error) => {
  notice(error.message, true);
  $("connection").textContent = "Access unavailable";
  $("connection").className = "badge warning";
});
