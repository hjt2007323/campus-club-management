"use strict";

const el = id => document.getElementById(id);
const value = id => el(id).value;
const idOf = id => {
  const idValue = Number(value(id));
  if (!Number.isSafeInteger(idValue) || idValue < 1) throw new Error("请先选择记录");
  return idValue;
};
const list = id => value(id).split(/\r?\n/).map(item => item.trim()).filter(Boolean);
const localDate = id => {
  const date = new Date(value(id));
  if (Number.isNaN(date.getTime())) throw new Error("请选择有效的日期和时间");
  return date.toISOString();
};
const formatDate = date => date ? new Date(date).toLocaleString("zh-CN", {hour12: false}) : "—";

const labels = {
  pending: "待审核", approved: "已通过", rejected: "已退回", draft: "草稿",
  submitted: "待审批", completed: "已完成", active: "已报名", cancelled: "已取消",
  affected: "征用待协调", superseded: "已换场",
};
const statusLabel = status => labels[status] || status;
const state = {
  token: "", actor: null, clubs: [], activities: [], rooms: [],
  managedClubs: [], managedActivities: [], reservations: [], blocks: [], registrations: [],
  coordination: null,
};

async function api(path, method = "GET", body, token = state.token) {
  const headers = {};
  if (token) headers.Authorization = "Bearer " + token;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(path, {method, headers, body: body === undefined ? undefined : JSON.stringify(body)});
  const result = await response.json();
  if (!response.ok) {
    const detail = result.detail;
    const message = Array.isArray(detail) ? detail.map(item => item.msg).join("；") : detail;
    throw new Error(message || "操作失败，请重试");
  }
  return result;
}
const withSemester = (path, term) => term ? path + "?" + new URLSearchParams({semester: term}) : path;

function feedback(message, error = false) {
  el("feedback").textContent = message;
  el("feedback").dataset.error = String(error);
  el("feedback").hidden = !message;
}

let busy = false;
function action(id, eventName, handler) {
  el(id).addEventListener(eventName, async event => {
    event.preventDefault();
    if (busy) return;
    busy = true;
    const target = event.submitter || event.currentTarget;
    const isButton = target instanceof HTMLButtonElement;
    if (isButton) target.disabled = true;
    feedback("处理中…");
    try {
      feedback(await handler());
    } catch (error) {
      feedback(error.message, true);
    } finally {
      if (isButton && target.id !== "confirm-coordination") target.disabled = false;
      updateConfirm();
      updateReservationControls();
      busy = false;
    }
  });
}
const form = (id, handler) => action(id, "submit", handler);
const click = (id, handler) => action(id, "click", handler);

function labelOptions(id, data, label, prompt = "请选择") {
  const select = el(id);
  const current = select.value;
  const selected = [...select.selectedOptions].map(option => option.value);
  const options = data.map(item => new Option(label(item), item.id));
  select.replaceChildren(...(!select.multiple ? [new Option(prompt, "")] : []), ...options);
  if (select.multiple) {
    for (const option of select.options) option.selected = selected.includes(option.value);
  } else if ([...select.options].some(option => option.value === current)) {
    select.value = current;
  }
}

function drawTable(target, columns, rows, empty = "暂无记录") {
  const container = typeof target === "string" ? el(target) : target;
  container.replaceChildren();
  if (rows.length === 0) {
    container.textContent = empty;
    return;
  }
  const table = document.createElement("table");
  table.className = "table table-sm align-middle";
  const header = table.createTHead().insertRow();
  for (const column of columns) {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = column;
    header.append(cell);
  }
  const body = table.createTBody();
  for (const values of rows) {
    const row = body.insertRow();
    for (const content of values) {
      const cell = row.insertCell();
      if (content instanceof Node) cell.append(content);
      else cell.textContent = content ?? "—";
    }
  }
  container.append(table);
}

function accountView() {
  const role = state.actor?.role || "guest";
  const access = [role, ...(state.actor ? ["signed"] : [])];
  for (const element of document.querySelectorAll("[data-role]")) {
    element.hidden = !element.dataset.role.split(" ").some(item => access.includes(item));
  }
  el("logout").hidden = !state.actor;
  el("account").textContent = state.actor
    ? (role === "admin" ? "管理员" : "学生") + " · " + state.actor.id
    : "访客";
}

for (const tab of document.querySelectorAll("[data-tab]")) {
  tab.addEventListener("click", () => {
    for (const panel of document.querySelectorAll(".page")) panel.hidden = panel.id !== tab.dataset.tab;
    for (const item of document.querySelectorAll("[data-tab]")) item.removeAttribute("aria-current");
    tab.setAttribute("aria-current", "page");
    if (!busy) feedback("");
  });
}

function clearCoordination() {
  state.coordination = null;
  el("coordination-list").replaceChildren();
  updateConfirm();
}

function resetPrivateViews() {
  for (const id of ["annual-table", "roster-table", "credit-table", "evaluation-table",
    "statistics-summary", "statistics-tables"]) el(id).replaceChildren();
  labelOptions("annual-review-id", [], item => item.year);
  labelOptions("attendance-student", [], item => item.id);
  el("draft").reset();
  el("venue-edit").reset();
  clearCoordination();
}

form("login", async () => {
  const token = value("token").trim();
  const actor = await api("/me", "GET", undefined, token);
  state.token = token;
  state.actor = actor;
  el("token").value = "";
  resetPrivateViews();
  await refresh();
  return "已切换账号";
});
click("logout", async () => {
  state.token = "";
  state.actor = null;
  el("token").value = "";
  resetPrivateViews();
  await refresh();
  return "已退出账号";
});

function activityName(id) {
  return [...state.managedActivities, ...state.activities].find(row => row.id === id)?.plan.title || "活动 " + id;
}
const roomName = id => state.rooms.find(row => row.id === id)?.name || "场地 " + id;
const clubName = id => [...state.managedClubs, ...state.clubs].find(row => row.id === id)?.name || "社团 " + id;
const activeBookings = new Set(["pending", "approved", "affected"]);

async function refresh() {
  [state.clubs, state.activities, state.rooms] = await Promise.all([
    api("/clubs"), api("/activities"), api("/venues"),
  ]);
  state.managedClubs = [];
  state.managedActivities = [];
  state.reservations = [];
  state.blocks = [];
  state.registrations = [];
  if (state.actor) {
    [state.managedClubs, state.managedActivities, state.reservations, state.blocks, state.registrations] = await Promise.all([
      api("/managed/clubs"), api("/managed/activities"), api("/reservations"),
      state.actor.role === "admin" ? api("/venue-blocks") : [],
      state.actor.role === "student" ? api("/me/registrations") : [],
    ]);
  }
  accountView();
  renderClubs();
  renderActivities();
  renderVenues();
}

function renderClubs() {
  drawTable("clubs-table", ["社团"], state.clubs.map(row => [row.name]));
  drawTable("managed-clubs-table", ["社团", "状态"], state.managedClubs.map(row => [row.name, statusLabel(row.status)]));
  const approved = state.managedClubs.filter(row => row.status === "approved");
  const pending = state.managedClubs.filter(row => row.status === "pending");
  for (const id of ["draft-club", "annual-club", "annual-filter"]) labelOptions(id, approved, row => row.name);
  labelOptions("review-club", pending, row => row.name);
}

function renderActivities() {
  drawTable("activities-table", ["活动", "社团", "时间", "场地", "报名状态"],
    state.activities.map(row => [
      row.plan.title, clubName(row.club_id), formatDate(row.schedule.starts_at),
      row.venue_name || (row.reservation_status === "affected" ? "征用待协调" : "待公布"),
      row.registration_open ? "可报名" : (row.status === "completed" ? "已完成" : "报名已结束"),
    ]));
  drawTable("managed-activities-table", ["活动", "社团", "状态", "时间"],
    state.managedActivities.map(row => [
      row.plan.title, clubName(row.club_id), statusLabel(row.status), formatDate(row.schedule?.starts_at),
    ]));
  drawTable("registration-table", ["我的报名", "报名状态", "签到时间"],
    state.registrations.map(row => [activityName(row.activity_id), statusLabel(row.status), formatDate(row.signed_at)]));
  const managed = state.managedActivities;
  const drafts = managed.filter(row => ["draft", "rejected"].includes(row.status));
  const approved = managed.filter(row => row.status === "approved");
  const currentActivities = state.activities.filter(row => row.registration_open);
  const signedEvents = new Set(state.registrations.filter(row => row.signed_at).map(row => row.activity_id));
  const bookingActivities = new Set(state.reservations.filter(row => activeBookings.has(row.status)).map(row => row.activity_id));
  const choices = {
    "draft-id": drafts,
    "submit-activity": drafts,
    "review-activity": managed.filter(row => row.status === "submitted"),
    "register-activity": currentActivities,
    "attendance-activity": managed.filter(row => ["approved", "completed"].includes(row.status)),
    "complete-activity": approved,
    "reserve-activity": currentActivities.filter(row => approved.some(item => item.id === row.id) && !bookingActivities.has(row.id)),
    "credit-activity": approved,
    "evaluation-activity": state.activities.filter(row => row.status === "completed" && signedEvents.has(row.id)),
    "evaluation-filter": managed.filter(row => row.status === "completed"),
  };
  for (const [id, options] of Object.entries(choices)) {
    const prompt = id === "draft-id" ? "新建草稿"
      : id === "reserve-activity" && !options.length ? "暂无可预约的活动" : "请选择";
    labelOptions(id, options, row => row.plan.title, prompt);
  }
}

function renderVenues() {
  drawTable("venues-table", ["场地", "容量", "设备"], state.rooms.map(row => [
    row.name, row.capacity, row.equipment.join("、") || "—",
  ]));
  drawTable("reservations-table", ["活动", "场地", "开始时间", "状态"],
    state.reservations.map(row => [
      activityName(row.activity_id), roomName(row.venue_id), formatDate(row.starts_at), statusLabel(row.status),
    ]));
  for (const id of ["venue-edit-id", "reserve-venue", "block-venues"]) {
    labelOptions(id, state.rooms, row => row.name + " · " + row.capacity + " 人", id === "venue-edit-id" ? "新增场地" : "请选择");
  }
  labelOptions("review-reservation", state.reservations.filter(row => ["pending", "affected"].includes(row.status)),
    row => activityName(row.activity_id) + " · " + roomName(row.venue_id) + " · " + statusLabel(row.status));
  labelOptions("block-id", state.blocks, row => row.reason + " · " + formatDate(row.starts_at));
  updateReservationControls();
}

form("club-apply", async () => {
  await api("/clubs", "POST", {name: value("club-name")});
  el("club-name").value = "";
  await refresh();
  return "社团申请已提交";
});
form("club-review", async () => {
  await api("/clubs/" + idOf("review-club") + "/review", "POST", {status: value("club-decision")});
  await refresh();
  return "社团审核已更新";
});
form("annual-submit", async () => {
  await api("/clubs/" + idOf("annual-club") + "/annual-reviews", "POST",
    {year: Number(value("annual-year")), materials: value("annual-materials")});
  el("annual-filter").value = value("annual-club");
  await loadAnnualReviews();
  return "年审材料已提交";
});
async function loadAnnualReviews() {
  const records = await api("/clubs/" + idOf("annual-filter") + "/annual-reviews");
  drawTable("annual-table", ["年份", "年审材料", "状态"], records.map(row => [row.year, row.materials, statusLabel(row.status)]));
  labelOptions("annual-review-id", records.filter(row => row.status === "pending"), row => row.year + " 年");
}
el("annual-filter").addEventListener("change", () => {
  el("annual-table").replaceChildren();
  labelOptions("annual-review-id", [], row => row.year);
});
form("annual-load", async () => {
  await loadAnnualReviews();
  return "已更新年审记录";
});
form("annual-review", async () => {
  await api("/annual-reviews/" + idOf("annual-review-id") + "/decision", "POST", {status: value("annual-decision")});
  await loadAnnualReviews();
  return "年审结果已保存";
});

const planFields = {
  title: "title", summary: "summary", participants: "participants",
  duration: "duration_minutes", capacity: "venue_capacity",
  goals: "goals", agenda: "agenda", equipment: "equipment", notes: "notes",
};
function fillPlan(plan = {}) {
  for (const [field, key] of Object.entries(planFields)) {
    el("plan-" + field).value = Array.isArray(plan[key]) ? plan[key].join("\n") : plan[key] ?? "";
  }
}
el("draft-id").addEventListener("change", () => {
  const draft = state.managedActivities.find(row => row.id === Number(value("draft-id")));
  if (draft) el("draft-club").value = draft.club_id;
  fillPlan(draft?.plan);
});
click("generate-plan", async () => {
  const club = idOf("draft-club");
  const description = value("description").trim();
  if (!description) throw new Error("请填写活动构想");
  fillPlan(await api("/clubs/" + club + "/ai-plan", "POST", {description}));
  return "草案已生成，请编辑并确认保存";
});
form("draft", async () => {
  const plan = {
    title: value("plan-title"), summary: value("plan-summary"),
    participants: Number(value("plan-participants")), duration_minutes: Number(value("plan-duration")),
    venue_capacity: Number(value("plan-capacity")), goals: list("plan-goals"), agenda: list("plan-agenda"),
    equipment: list("plan-equipment"), notes: list("plan-notes"),
  };
  const draft = state.managedActivities.find(row => row.id === Number(value("draft-id")));
  const club = idOf("draft-club");
  if (draft && draft.club_id !== club) throw new Error("编辑草稿时请保留原主办社团");
  const saved = draft
    ? await api("/activities/" + draft.id, "PATCH", {confirmed: true, plan})
    : await api("/activities", "POST", {club_id: club, confirmed: true, plan});
  await refresh();
  el("draft-id").value = saved.id;
  el("submit-activity").value = saved.id;
  return "活动草稿已保存";
});
form("activity-submit", async () => {
  await api("/activities/" + idOf("submit-activity") + "/submit", "POST", {
    starts_at: localDate("activity-start"), ends_at: localDate("activity-end"),
    semester: value("semester"), category: value("category"),
  });
  await refresh();
  return "活动已提交审批";
});
form("activity-review", async () => {
  await api("/activities/" + idOf("review-activity") + "/review", "POST", {
    status: value("activity-decision"), priority: Number(value("activity-priority")),
  });
  await refresh();
  return "活动审批已更新";
});
form("registration", async () => {
  await api("/activities/" + idOf("register-activity") + "/registration", "PUT");
  await refresh();
  return "报名成功";
});
click("cancel-registration", async () => {
  await api("/activities/" + idOf("register-activity") + "/registration", "DELETE");
  await refresh();
  return "报名已取消";
});
async function loadRoster() {
  const records = await api("/activities/" + idOf("attendance-activity") + "/registrations");
  drawTable("roster-table", ["学生", "签到时间"], records.map(row => [row.student_id, formatDate(row.signed_at)]));
  labelOptions("attendance-student", records.filter(row => !row.signed_at).map(row => ({id: row.student_id})), row => row.id);
}
el("attendance-activity").addEventListener("change", () => {
  el("roster-table").replaceChildren();
  labelOptions("attendance-student", [], row => row.id);
});
click("load-roster", async () => {
  await loadRoster();
  return "已更新有效报名名单";
});
form("attendance", async () => {
  await api("/activities/" + idOf("attendance-activity") + "/attendance", "POST", {student_id: value("attendance-student")});
  await loadRoster();
  return "已登记签到";
});
form("activity-complete", async () => {
  const result = await api("/activities/" + idOf("complete-activity") + "/complete", "POST");
  await refresh();
  return "活动已完成，为 " + result.credits_awarded + " 名学生认定学分";
});

el("venue-edit-id").addEventListener("change", () => {
  const room = state.rooms.find(row => row.id === Number(value("venue-edit-id")));
  el("venue-name").value = room?.name || "";
  el("venue-capacity").value = room?.capacity || "";
  el("venue-equipment").value = room?.equipment.join("\n") || "";
});
form("venue-edit", async () => {
  const existingId = Number(value("venue-edit-id"));
  const body = {name: value("venue-name"), capacity: Number(value("venue-capacity")), equipment: list("venue-equipment")};
  await api(existingId ? "/venues/" + existingId : "/venues", existingId ? "PATCH" : "POST", body);
  el("venue-edit").reset();
  await refresh();
  return "场地已保存";
});
function updateReservationControls() {
  const selected = Boolean(value("reserve-activity"));
  el("load-venue-options").disabled = !selected;
  el("reserve-venue").disabled = !selected;
  el("venue-reserve").querySelector('button[type="submit"]').disabled = !selected;
}

el("reserve-activity").addEventListener("change", () => {
  labelOptions("reserve-venue", state.rooms, row => row.name);
  updateReservationControls();
});
click("load-venue-options", async () => {
  const options = await api("/activities/" + idOf("reserve-activity") + "/venue-options");
  labelOptions("reserve-venue", options, row => row.name);
  return "符合原时段、容量和设备条件的场地共 " + options.length + " 间";
});
form("venue-reserve", async () => {
  await api("/reservations", "POST", {activity_id: idOf("reserve-activity"), venue_id: idOf("reserve-venue")});
  await refresh();
  return "场地预约已提交，等待审核";
});
form("reservation-review", async () => {
  await api("/reservations/" + idOf("review-reservation") + "/review", "POST", {status: value("reservation-decision")});
  await refresh();
  return "预约状态已更新";
});
form("venue-block", async () => {
  const venues = [...el("block-venues").selectedOptions].map(option => Number(option.value));
  const block = await api("/venue-blocks", "POST", {
    venue_ids: venues, starts_at: localDate("block-start"), ends_at: localDate("block-end"), reason: value("block-reason"),
  });
  await refresh();
  el("block-id").value = block.id;
  await loadCoordination();
  return "征用已登记，受影响预约 " + block.affected_reservation_ids.length + " 条";
});

el("block-id").addEventListener("change", clearCoordination);
function readAssignments() {
  return (state.coordination?.affected || []).flatMap(row => {
    const venue = el("assignment-" + row.id)?.value;
    return venue ? [{reservation_id: row.id, venue_id: Number(venue)}] : [];
  });
}
function updateConfirm() {
  el("confirm-coordination").disabled = readAssignments().length === 0;
}
async function loadCoordination() {
  const blockId = idOf("block-id");
  const preview = await api("/venue-blocks/" + blockId + "/coordination");
  state.coordination = preview;
  const proposed = new Map((preview.suggested_assignments || []).map(row => [row.reservation_id, row.venue_id]));
  const rows = preview.affected.map(row => {
    const select = document.createElement("select");
    select.id = "assignment-" + row.id;
    select.className = "form-select form-select-sm";
    select.setAttribute("aria-label", row.title + "的替代场地");
    select.append(new Option(row.candidates.length ? "暂不安排" : "没有可用场地", ""));
    for (const room of row.candidates) select.append(new Option(room.name, room.id));
    if (proposed.has(row.id)) select.value = proposed.get(row.id);
    select.addEventListener("change", updateConfirm);
    return [row.title, formatDate(row.starts_at), roomName(row.venue_id), row.priority, select];
  });
  drawTable("coordination-list", ["活动", "原定开始时间", "原场地", "优先级", "替代场地"], rows, "没有待协调的预约");
  updateConfirm();
}
click("load-coordination", async () => {
  await loadCoordination();
  const preview = state.coordination;
  if (preview.affected.length === 0) return "没有待协调的预约";
  return preview.suggested_assignments === null
    ? "候选场地已列出，请人工选择"
    : "建议已填入，可调整后确认。";
});
form("venue-coordinate", async () => {
  const assignments = readAssignments();
  if (!state.coordination || state.coordination.block_id !== idOf("block-id") || !assignments.length) {
    throw new Error("请加载候选场地并选择替代场地");
  }
  const result = await api("/venue-blocks/" + state.coordination.block_id + "/coordinate", "POST", {assignments});
  await refresh();
  await loadCoordination();
  return "已确认 " + result.confirmed.length + " 条安排，待协调 " + result.unassigned_reservation_ids.length + " 条";
});

form("credit-rule", async () => {
  await api("/activities/" + idOf("credit-activity") + "/credit-rule", "PUT", {credits: value("credit-amount")});
  return "学分规则已保存";
});
form("credit-load", async () => {
  const records = await api(withSemester("/me/credits", value("credit-semester").trim()));
  drawTable("credit-table", ["来源活动", "学期", "学分", "认定时间"], records.records.map(row => [
    row.activity_title, row.semester, row.credits, formatDate(row.awarded_at),
  ]));
  return "所选范围学分合计 " + records.total;
});
form("evaluation-submit", async () => {
  await api("/activities/" + idOf("evaluation-activity") + "/evaluations", "POST", {
    rating: Number(value("evaluation-rating")), comment: value("evaluation-comment"),
  });
  el("evaluation-comment").value = "";
  return "评价已提交";
});
form("evaluation-load", async () => {
  const result = await api("/activities/" + idOf("evaluation-filter") + "/evaluations");
  drawTable("evaluation-table", ["学生", "评分", "文字评价"], result.records.map(row => [row.student_id, row.rating, row.comment]));
  return result.average === null ? "活动暂无评价" : "活动平均评分 " + result.average.toFixed(2);
});
form("statistics-load", async () => {
  const data = await api(withSemester("/statistics", value("stats-semester").trim()));
  const metrics = [
    ["活动", data.activity_count], ["有效报名人次", data.registrations], ["签到人次", data.attendances],
    ["报名学生数", data.unique_students], ["已认定学分", data.credit_total],
  ];
  el("statistics-summary").replaceChildren(...metrics.map(([name, amount]) => {
    const item = document.createElement("div");
    item.className = "metric";
    const label = document.createElement("span");
    const total = document.createElement("strong");
    label.textContent = name;
    total.textContent = amount;
    item.append(label, total);
    return item;
  }));
  const detail = el("statistics-tables");
  detail.replaceChildren();
  const groups = [
    [["学期", "活动数", "已认定学分", "学分记录数"],
      Object.entries(data.activities_by_semester).map(([term, count]) =>
        [term, count, data.credits_by_semester[term]?.credits ?? 0, data.credits_by_semester[term]?.records ?? 0])],
    [["社团", "活动数"], data.activities_by_club.map(row => [row.name, row.count])],
    [["活动类型", "活动数"], Object.entries(data.activities_by_category)],
  ];
  for (const [columns, rows] of groups) {
    const box = document.createElement("div");
    box.className = "table-responsive statistics-group";
    drawTable(box, columns, rows);
    detail.append(box);
  }
  return "统计数据已更新";
});

el("annual-year").value = new Date().getFullYear();
refresh().catch(error => feedback(error.message, true));
