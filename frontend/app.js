const API = "/api";
const CACHE_KEY = "saarthi-plan-v2";
const QUEUE_KEY = "saarthi-offline-evidence-v2";
const MATERIALS = ["chalk", "blackboard", "paper", "pencils", "number cards (1-100)", "bottle caps", "sticks (bundles of 10)", "letter cards", "picture cards", "storybooks (5 copies)"];

const state = {
  classroom: null, students: [], groups: [], plan: null, summary: null,
  competencies: [], attendance: new Map(), evidence: new Map(),
  activityId: null, variation: 0,
  demo: {active: false, startedAt: 0, step: "attendance"},
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = (value = "") => String(value).replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));

async function request(path, options = {}) {
  const init = {method: options.method || "GET", headers: {"Content-Type": "application/json"}};
  if (options.body !== undefined) init.body = JSON.stringify(options.body);
  try {
    const response = await fetch(API + path, init);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
    return data;
  } catch (error) {
    if (!navigator.onLine && options.queue) {
      const queue = JSON.parse(localStorage.getItem(QUEUE_KEY) || "[]");
      queue.push({path, options: {method: init.method, body: options.body}});
      localStorage.setItem(QUEUE_KEY, JSON.stringify(queue));
      updateConnection();
      return {queued: true};
    }
    throw error;
  }
}

function toast(message, error = false) {
  const node = $("#toast");
  node.textContent = message;
  node.className = "toast show" + (error ? " error" : "");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.className = "toast", 3200);
}

function busy(button, active, label = "Working…") {
  if (active) button.dataset.label = button.innerHTML;
  button.disabled = active;
  button.innerHTML = active ? label : (button.dataset.label || button.innerHTML);
}

function comp(id) {
  return state.competencies.find(item => item.id === id) || {id, description: id};
}

function mastery(student, id = state.classroom?.target_competency_id) {
  return student.competencies[id] || {score: 0, state: "Not yet learned", last_assessed: null};
}

function previousAttendance(student) {
  return student.attendance_history.filter(item => item.date < state.classroom.current_date).sort((a, b) => a.date.localeCompare(b.date)).at(-1);
}

function returning(student) {
  const previous = previousAttendance(student);
  return Boolean(previous && !previous.present && state.attendance.get(student.id) !== false);
}

async function bootstrap() {
  try {
    const data = await request("/bootstrap");
    Object.assign(state, {
      classroom: data.classroom, students: data.students, groups: data.groups || [],
      plan: data.latest_plan, summary: data.summary, competencies: data.competencies,
    });
    state.attendance = new Map(state.students.map(student => {
      const today = student.attendance_history.find(item => item.date === state.classroom.current_date);
      return [student.id, today?.present ?? true];
    }));
    renderAll();
    cachePlan();
  } catch (error) {
    const cached = JSON.parse(localStorage.getItem(CACHE_KEY) || "null");
    if (!cached) return toast("Could not load classroom: " + error.message, true);
    Object.assign(state, cached);
    state.attendance = new Map(state.students.map(student => [student.id, true]));
    renderAll();
    toast("Offline: showing the last saved classroom plan", true);
  }
}

function cachePlan() {
  if (!state.classroom) return;
  localStorage.setItem(CACHE_KEY, JSON.stringify({
    classroom: state.classroom, students: state.students, groups: state.groups,
    plan: state.plan, summary: state.summary, competencies: state.competencies,
  }));
}

function renderAll() {
  renderShell(); renderDashboard(); renderAttendance(); renderGroups();
  renderPlan(); renderEndClass(); buildPrintPack();
}

function renderShell() {
  $("#side-class-name").textContent = "Sunita Devi · Grades 1–3";
  $("#side-date").textContent = state.classroom.current_date;
  $("#side-duration").textContent = state.classroom.class_duration_minutes;
  $("#print-button").hidden = !state.plan;
  updateConnection();
}

function renderDashboard() {
  const summary = state.summary || {};
  const priority = state.groups[0];
  const cards = [
    ["Present today", `${summary.present_count ?? state.students.length}/${summary.total_students ?? state.students.length}`, `${summary.absent_count || 0} absent`, false],
    ["Returning", summary.returning_count ?? state.students.filter(returning).length, "after a missed class", false],
    ["Possible gaps", summary.prerequisite_gap_count ?? "—", "need a quick verification", false],
    ["Teacher first", priority ? priority.name.split("·")[0].trim() : "Not set", priority ? priority.name.split("·")[1].trim() : "Save attendance first", true],
  ];
  $("#summary-grid").innerHTML = cards.map(([label, value, detail, special]) => `<article class="summary-card ${special ? "priority" : ""}"><div class="label">${esc(label)}<span>↗</span></div><strong class="value">${esc(value)}</strong><span class="detail">${esc(detail)}</span></article>`).join("");
  $("#objective-select").innerHTML = state.competencies.filter(item => item.subject === "Numeracy").map(item => `<option value="${item.id}" ${item.id === state.classroom.target_competency_id ? "selected" : ""}>${item.id} · ${esc(item.description)}</option>`).join("");
  $("#language-select").value = state.classroom.instruction_language;
  $("#duration-select").value = String(state.classroom.class_duration_minutes);
  $("#slot-select").value = String(state.classroom.slot_duration_minutes);
  $("#material-options").innerHTML = MATERIALS.map(item => `<label class="material-chip"><input type="checkbox" value="${esc(item)}" ${state.classroom.available_materials.includes(item) ? "checked" : ""}><span>${esc(item)}</span></label>`).join("");
}

function renderAttendance(filter = "") {
  if (!state.classroom) return;
  const target = state.classroom.target_competency_id;
  const students = state.students.filter(student => student.name.toLowerCase().includes(filter.toLowerCase()));
  $("#attendance-count").textContent = `${[...state.attendance.values()].filter(Boolean).length} present · ${state.students.length} learners`;
  const rows = students.map(student => {
    const record = mastery(student, target);
    const isPresent = state.attendance.get(student.id) !== false;
    return `<div class="attendance-row" data-student-id="${student.id}">
      <div class="student-cell"><span class="avatar">${esc(student.name.slice(0, 2).toUpperCase())}</span><div><strong>${esc(student.name)}${returning(student) ? '<span class="returning-badge">Returning</span>' : ""}</strong><small>${esc(student.teacher_notes || "No teacher note")}</small></div></div>
      <div class="mastery-mini"><strong>Grade ${student.grade}</strong>${esc(student.home_language)}</div>
      <div class="mastery-mini"><strong>${Math.round(record.score * 100)}% · ${esc(record.state)}</strong>${record.last_assessed ? `Checked ${esc(record.last_assessed)}` : "Needs verification"}</div>
      <div class="attendance-toggle"><button class="present ${isPresent ? "active" : ""}" data-att="present">Present</button><button class="absent ${!isPresent ? "active" : ""}" data-att="absent">Absent</button></div>
    </div>`;
  }).join("");
  $("#attendance-list").innerHTML = `<div class="attendance-head"><span>Learner</span><span>Grade / language</span><span>${target} evidence</span><span>Today</span></div>${rows}`;
}

function groupStyle(group) {
  return group.mastery_level === "RECOVERY" ? "recovery" : group.mastery_level === "Mastered" ? "extension" : "practice";
}

function renderGroups() {
  if (!state.groups.length) {
    $("#teacher-first-banner").innerHTML = `<div><strong>No groups yet</strong><p>Save today’s attendance to create the first recommendation.</p></div>`;
    $("#group-grid").innerHTML = `<article class="panel"><p>Groups will appear here after attendance.</p></article>`;
    return;
  }
  const first = state.groups[0];
  $("#teacher-first-banner").innerHTML = `<div><strong>${esc(first.name)} receives the teacher first</strong><p>${esc(first.priority_explanation)}</p></div><span class="priority-number">${Number(first.priority_score).toFixed(1)}</span>`;
  $("#group-grid").innerHTML = state.groups.map(group => {
    const students = group.student_ids.map(id => {
      const student = state.students.find(item => item.id === id);
      return `<div class="student-chip ${id === "STU020" ? "rajkumar" : ""}" draggable="true" data-student-id="${id}"><span>${esc(student?.name || id)}</span><em>G${student?.grade} · ${esc(student?.home_language || "")}</em></div>`;
    }).join("");
    const label = group.mastery_level === "RECOVERY" ? "Possible gap" : group.mastery_level;
    return `<article class="group-card ${groupStyle(group)}" data-group-id="${group.id}">
      <span class="pill ${groupStyle(group)}">${esc(label)}</span><h2>${esc(group.name)}</h2>
      <div class="focus">Focus: ${group.focus_competency_id} · ${esc(comp(group.focus_competency_id).description)}</div>
      <div class="group-reason"><strong>Why this group?</strong>${esc(group.reason)}</div>
      <div class="student-dropzone" data-group-id="${group.id}">${students}</div>
      <div class="language-line">Scaffold: ${esc(group.scaffold_language)} · ${esc(Object.entries(group.language_breakdown).map(([key, value]) => `${key} ${value}`).join(" / "))}</div>
    </article>`;
  }).join("");
  wireDrag();
}

function wireDrag() {
  $$(".student-chip").forEach(chip => chip.addEventListener("dragstart", event => event.dataTransfer.setData("text/plain", chip.dataset.studentId)));
  $$(".student-dropzone").forEach(zone => {
    zone.addEventListener("dragover", event => { event.preventDefault(); zone.classList.add("dragover"); });
    zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
    zone.addEventListener("drop", event => {
      event.preventDefault(); zone.classList.remove("dragover");
      const id = event.dataTransfer.getData("text/plain");
      const chip = $(`.student-chip[data-student-id="${id}"]`);
      if (chip) zone.appendChild(chip);
    });
  });
}

function groupOverrides() {
  return $$(".group-card").map(card => ({
    id: card.dataset.groupId,
    student_ids: $$(".student-chip", card).map(chip => chip.dataset.studentId),
  }));
}

function renderPlan() {
  if (!state.plan) {
    $("#plan-meta").innerHTML = "";
    $("#rotation-wrap").innerHTML = `<div style="padding:28px">Build groups first, then generate the rotation plan.</div>`;
    return;
  }
  const plan = state.plan;
  const meta = [
    `${plan.duration_minutes} minute class`, `${plan.slot_duration_minutes} minute rotations`, `${plan.groups.length} groups`,
    plan.language === "Auto" ? "Language by group" : plan.language,
    plan.teacher_approved ? "Teacher approved" : "Awaiting teacher review", `${plan.planning_runtime_ms} ms plan runtime`,
  ];
  $("#plan-meta").innerHTML = meta.map(item => `<span>${esc(item)}</span>`).join("");
  const slotIndexes = [...new Set(plan.schedule.map(item => item.slot_index))];
  const lookup = new Map(plan.schedule.map(item => [`${item.slot_index}:${item.group_id}`, item]));
  const rows = slotIndexes.map(index => {
    const example = plan.schedule.find(item => item.slot_index === index);
    const cells = plan.groups.map(group => {
      const item = lookup.get(`${index}:${group.id}`);
      const style = item.station.startsWith("Teacher") ? "teacher" : item.station.startsWith("Peer") ? "peer" : "independent";
      return `<td><button class="activity-cell ${style}" data-activity-id="${item.activity.id}"><span class="station">${esc(item.station)}</span><strong>${esc(item.activity.title)}</strong><small>${esc(item.activity.competency_id)} · ${esc(item.activity.activity_type)} · ${esc(item.activity.language)}</small></button></td>`;
    }).join("");
    return `<tr><td class="time-label">${example.start_minute}–${example.end_minute}<br><small>minutes</small></td>${cells}</tr>`;
  }).join("");
  $("#rotation-wrap").innerHTML = `<table class="rotation-table"><thead><tr><th>Time</th>${plan.groups.map(group => `<th>${esc(group.name)}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table>`;
  $$("[data-activity-id]").forEach(button => button.addEventListener("click", () => openActivity(button.dataset.activityId)));
}

function evidenceValue(studentId, competencyId) {
  const key = `${studentId}:${competencyId}`;
  if (!state.evidence.has(key)) state.evidence.set(key, {student_id: studentId, competency_id: competencyId, observation: "not_assessed", exit_ticket_correct: null});
  return state.evidence.get(key);
}

function renderEndClass() {
  if (!state.groups.length) {
    $("#raj-evidence-callout").innerHTML = `<div><strong>Create groups before recording evidence</strong><p>The group focus determines which competency the exit check measures.</p></div>`;
    $("#evidence-groups").innerHTML = "";
    return;
  }
  const rajGroup = state.groups.find(group => group.student_ids.includes("STU020"));
  $("#raj-evidence-callout").innerHTML = `<div><strong>Close Rajkumar’s possible ${esc(rajGroup?.focus_competency_id || "prerequisite")} gap</strong><p>A correct answer plus your observation can move him forward.</p></div><button class="button secondary" id="use-demo-evidence">Use demo evidence</button>`;
  $("#evidence-groups").innerHTML = state.groups.map((group, groupIndex) => {
    const rows = group.student_ids.map(studentId => {
      const student = state.students.find(item => item.id === studentId);
      const value = evidenceValue(studentId, group.focus_competency_id);
      return `<div class="evidence-row" data-evidence-key="${studentId}:${group.focus_competency_id}">
        <div class="student-cell"><span class="avatar">${esc(student.name.slice(0,2).toUpperCase())}</span><div><strong>${esc(student.name)}</strong><small>Checking ${group.focus_competency_id} · ${esc(comp(group.focus_competency_id).description)}</small></div></div>
        <label>Teacher observation<select data-field="observation"><option value="not_assessed" ${value.observation === "not_assessed" ? "selected" : ""}>Not assessed</option><option value="understood" ${value.observation === "understood" ? "selected" : ""}>Understood</option><option value="needs_practice" ${value.observation === "needs_practice" ? "selected" : ""}>Needs practice</option></select></label>
        <div><span class="eyebrow">EXIT CHECK</span><div class="ticket-control"><button type="button" class="yes ${value.exit_ticket_correct === true ? "active" : ""}" data-ticket="true">Correct</button><button type="button" class="no ${value.exit_ticket_correct === false ? "active" : ""}" data-ticket="false">Not yet</button><button type="button" class="${value.exit_ticket_correct === null ? "active" : ""}" data-ticket="null">Skip</button></div></div>
        <span class="mastery-mini"><strong>${Math.round(mastery(student, group.focus_competency_id).score * 100)}%</strong>Current evidence</span>
      </div>`;
    }).join("");
    return `<details class="panel evidence-group" ${groupIndex === 0 ? "open" : ""}><summary><span>${esc(group.name)} · ${group.student_ids.length} learners</span><button type="button" class="text-button group-apply" data-apply-group="${group.id}">Apply “understood + correct” to group</button></summary><div>${rows}</div></details>`;
  }).join("");
  wireEvidence();
}

function wireEvidence() {
  $$("[data-evidence-key]").forEach(row => {
    const value = state.evidence.get(row.dataset.evidenceKey);
    $("select", row).addEventListener("change", event => value.observation = event.target.value);
    $$("[data-ticket]", row).forEach(button => button.addEventListener("click", () => {
      value.exit_ticket_correct = button.dataset.ticket === "null" ? null : button.dataset.ticket === "true";
      $$("[data-ticket]", row).forEach(item => item.classList.remove("active"));
      button.classList.add("active");
    }));
  });
  $$("[data-apply-group]").forEach(button => button.addEventListener("click", event => {
    event.preventDefault();
    const group = state.groups.find(item => item.id === button.dataset.applyGroup);
    group.student_ids.forEach(id => Object.assign(evidenceValue(id, group.focus_competency_id), {observation: "understood", exit_ticket_correct: true}));
    renderEndClass();
  }));
  $("#use-demo-evidence")?.addEventListener("click", () => {
    const group = state.groups.find(item => item.student_ids.includes("STU020"));
    Object.assign(evidenceValue("STU020", group.focus_competency_id), {observation: "understood", exit_ticket_correct: true});
    state.demo.step = "regroup"; updateDemoRail(); renderEndClass();
    toast("Rajkumar: understood + exit check correct");
  });
}

function findActivity(id) {
  return state.plan?.schedule.find(item => item.activity.id === id)?.activity;
}

function openActivity(id) {
  const activity = findActivity(id);
  if (!activity) return;
  state.activityId = id;
  const form = $("#activity-form");
  $("#dialog-title").textContent = activity.title;
  $("#dialog-badges").innerHTML = `<span class="pill neutral">${esc(activity.activity_type)}</span><span class="pill ${activity.target_level === "RECOVERY" ? "recovery" : "practice"}">${esc(activity.target_level)}</span><span class="pill neutral">${esc(activity.language)}</span>`;
  form.elements.title.value = activity.title;
  form.elements.objective.value = activity.objective;
  form.elements.student_instructions.value = activity.student_instructions.join("\n");
  form.elements.expected_response.value = activity.expected_response;
  form.elements.quick_check.value = activity.quick_check;
  $("#dialog-source").innerHTML = `<strong>Grounded source</strong><br>${esc(activity.source_reference)}${activity.recovery_reason ? `<br><br><strong>Why this recovery task?</strong><br>${esc(activity.recovery_reason)}` : ""}<br><br>Generated by: ${esc(activity.generated_by)}`;
  $("#activity-dialog").showModal();
}

function replaceActivity(oldId, replacement) {
  state.plan.schedule.forEach(item => { if (item.activity.id === oldId) item.activity = replacement; });
  cachePlan(); renderPlan(); buildPrintPack();
}

async function loadMetrics() {
  try {
    const result = await request("/metrics");
    if (!result.summary) {
      $("#metric-grid").innerHTML = `<article class="panel">${esc(result.status || "Evaluation unavailable")}</article>`;
      return;
    }
    const summary = result.summary;
    const cards = [
      ["Learners assigned", `${summary.grouping.student_assignment_rate}%`, "Across all fixed scenarios"],
      ["Groups occupied", `${summary.scheduling.continuous_work_rate}%`, "Every rotation slot"],
      ["Grounded activities", `${summary.activities.curriculum_grounding_rate}%`, "Approved source retained"],
      ["Plans accepted", `${summary.workflow.plan_acceptance_rate}%`, "Passed all guardrails"],
    ];
    $("#metric-grid").innerHTML = cards.map(([label, value, note]) => `<article class="metric-card"><span>${esc(label)}</span><strong>${esc(value)}</strong><small>${esc(note)}</small></article>`).join("");
    const capability = value => value ? "Built in" : "Not built in";
    $("#baseline-table").innerHTML = `<table class="baseline"><thead><tr><th>Workflow</th><th>All groups occupied</th><th>Gap-aware</th><th>Sources</th><th>Validated plans</th></tr></thead><tbody>${result.baseline_comparison.map(row => `<tr><td>${esc(row.name)}</td><td>${capability(row.groups_continuously_occupied)}</td><td>${capability(row.prerequisite_aware)}</td><td>${capability(row.curriculum_sources)}</td><td>${row.validated_constraint_rate == null ? "Not tested" : `${row.validated_constraint_rate}%`}</td></tr>`).join("")}</tbody></table>`;
  } catch (error) {
    toast("Could not load evaluation: " + error.message, true);
  }
}

function buildPrintPack() {
  const container = $("#print-pack");
  if (!state.plan) { container.innerHTML = ""; return; }
  const cards = state.plan.groups.map(group => {
    const slots = state.plan.schedule.filter(item => item.group_id === group.id).sort((a, b) => a.slot_index - b.slot_index);
    return `<section class="print-card"><p>SAARTHI-MG · ${esc(state.plan.date)}</p><h1>${esc(group.name)}</h1><p><strong>Learning focus:</strong> ${group.focus_competency_id} · ${esc(comp(group.focus_competency_id).description)}</p>${slots.map(item => `<h2>${item.start_minute}–${item.end_minute} min · ${esc(item.station)}</h2><h3>${esc(item.activity.title)}</h3><ol class="print-instructions">${item.activity.student_instructions.map(step => `<li>${esc(step)}</li>`).join("")}</ol><p><strong>Materials:</strong> ${esc(item.activity.materials_needed.join(", ") || "None")}</p><p><strong>Quick check:</strong> ${esc(item.activity.quick_check)}</p>`).join("")}<hr><p><strong>Source:</strong> ${esc(slots[0]?.activity.source_reference || "")}</p></section>`;
  }).join("");
  const tickets = state.plan.groups.flatMap(group => {
    const ticket = state.plan.exit_tickets.find(item => item.group_id === group.id);
    return group.student_ids.map(id => {
      const student = state.students.find(item => item.id === id);
      return `<article class="print-ticket"><h2>Exit check · ${esc(group.focus_competency_id)}</h2><p>Name: ${esc(student?.name || id)}</p><p>${esc(ticket.question)}</p><p>${esc(ticket.follow_up)}</p><br><br><p>Answer: ____________________</p></article>`;
    });
  }).join("");
  container.innerHTML = cards + `<section class="print-card"><h1>Exit tickets</h1>${tickets}</section>`;
}

function navigate(screen) {
  $$(".screen").forEach(item => item.classList.toggle("active", item.dataset.screen === screen));
  $$(".nav-item").forEach(item => item.classList.toggle("active", item.dataset.nav === screen));
  $(".sidebar").classList.remove("open");
  history.replaceState(null, "", "#" + screen);
  if (screen === "evidence") loadMetrics();
  if (screen === "endclass") renderEndClass();
  window.scrollTo({top: 0, behavior: "smooth"});
}

function updateDemoRail() {
  if (!state.demo.active) return;
  const order = ["attendance", "groups", "plan", "approve", "evidence", "regroup"];
  const current = order.indexOf(state.demo.step);
  $$("[data-demo-step]").forEach((item, index) => {
    item.classList.toggle("done", index < current);
    item.classList.toggle("current", index === current);
  });
  const seconds = Math.round((Date.now() - state.demo.startedAt) / 1000);
  $("#demo-time").textContent = `Elapsed ${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")} · target <3:00`;
}

function updateConnection() {
  const queued = JSON.parse(localStorage.getItem(QUEUE_KEY) || "[]").length;
  const node = $("#connection");
  node.classList.toggle("offline", !navigator.onLine);
  node.innerHTML = `<span></span>${navigator.onLine ? (queued ? `${queued} update queued` : "Saved locally") : `Offline · ${queued} update queued`}`;
}

async function flushQueue() {
  const queue = JSON.parse(localStorage.getItem(QUEUE_KEY) || "[]");
  if (!navigator.onLine || !queue.length) return;
  const remaining = [];
  for (const item of queue) {
    try { await request(item.path, item.options); } catch { remaining.push(item); }
  }
  localStorage.setItem(QUEUE_KEY, JSON.stringify(remaining));
  updateConnection();
  if (!remaining.length) toast("Offline evidence synced");
}

document.addEventListener("click", event => {
  const target = event.target.closest("[data-nav]");
  if (target) { event.preventDefault(); navigate(target.dataset.nav); }
});

$("#mobile-menu").addEventListener("click", () => $(".sidebar").classList.toggle("open"));
$("#attendance-search").addEventListener("input", event => renderAttendance(event.target.value));
$("#attendance-list").addEventListener("click", event => {
  const button = event.target.closest("[data-att]");
  if (!button) return;
  const row = button.closest("[data-student-id]");
  state.attendance.set(row.dataset.studentId, button.dataset.att === "present");
  renderAttendance($("#attendance-search").value);
});

$("#mark-all-present").addEventListener("click", () => {
  state.students.forEach(student => state.attendance.set(student.id, true));
  renderAttendance($("#attendance-search").value);
});

$("#save-setup").addEventListener("click", async event => {
  const button = event.currentTarget;
  busy(button, true, "Saving…");
  try {
    const available = $$("#material-options input:checked").map(input => input.value);
    if (!available.length) throw new Error("Select at least one available material");
    const result = await request("/classrooms", {method: "POST", body: {
      target_competency_id: $("#objective-select").value,
      instruction_language: $("#language-select").value,
      class_duration_minutes: Number($("#duration-select").value),
      slot_duration_minutes: Number($("#slot-select").value),
      available_materials: available,
    }});
    state.classroom = result.classroom;
    state.groups = []; state.plan = null;
    await bootstrap();
    toast("Class constraints saved");
  } catch (error) { toast(error.message, true); }
  finally { busy(button, false); }
});

$("#save-attendance").addEventListener("click", async event => {
  const button = event.currentTarget;
  busy(button, true, "Finding needs…");
  try {
    await request("/attendance", {method: "POST", body: {
      date: state.classroom.current_date,
      concepts_taught: [state.classroom.target_competency_id],
      records: state.students.map(student => ({student_id: student.id, present: state.attendance.get(student.id) !== false})),
    }});
    const result = await request("/groups/generate", {method: "POST", body: {}});
    state.groups = result.groups; state.plan = null;
    state.demo.step = "groups"; updateDemoRail();
    await bootstrap();
    navigate("groups");
    toast(`${state.groups.length} flexible groups created`);
  } catch (error) { toast(error.message, true); }
  finally { busy(button, false); }
});

$("#save-group-overrides").addEventListener("click", async event => {
  const button = event.currentTarget;
  busy(button, true, "Saving…");
  try {
    const result = await request("/groups/override", {method: "POST", body: {groups: groupOverrides()}});
    state.groups = result.groups; renderGroups(); cachePlan();
    toast("Teacher group changes saved");
  } catch (error) { toast(error.message, true); }
  finally { busy(button, false); }
});

async function createPlan(button) {
  busy(button, true, "Building grounded plan…");
  try {
    if ($$(".group-card").length) {
      const saved = await request("/groups/override", {method: "POST", body: {groups: groupOverrides()}});
      state.groups = saved.groups;
    }
    const result = await request("/schedule/generate", {method: "POST", body: {}});
    state.plan = result.plan;
    state.demo.step = "plan"; updateDemoRail(); cachePlan();
    renderPlan(); buildPrintPack(); navigate("plan");
    toast("Conflict-free rotation built");
  } catch (error) { toast(error.message, true); }
  finally { busy(button, false); }
}

$("#build-plan").addEventListener("click", event => createPlan(event.currentTarget));
$("#regenerate-plan").addEventListener("click", event => createPlan(event.currentTarget));

$("#approve-plan").addEventListener("click", async event => {
  if (!state.plan) return toast("Build a plan first", true);
  const button = event.currentTarget;
  busy(button, true, "Approving…");
  try {
    const result = await request(`/plans/${state.plan.id}/approval`, {method: "POST", body: {approved: true}});
    state.plan = result.plan; state.demo.step = "evidence"; updateDemoRail();
    renderPlan(); cachePlan(); toast("Plan approved by the teacher");
  } catch (error) { toast(error.message, true); }
  finally { busy(button, false); }
});

$("#activity-form").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    const result = await request(`/activities/${state.activityId}/update`, {method: "POST", body: {
      title: form.elements.title.value,
      objective: form.elements.objective.value,
      student_instructions: form.elements.student_instructions.value.split("\n").map(value => value.trim()).filter(Boolean),
      expected_response: form.elements.expected_response.value,
      quick_check: form.elements.quick_check.value,
      status: "draft",
    }});
    replaceActivity(state.activityId, result.activity);
    $("#activity-dialog").close(); toast("Teacher edit saved");
  } catch (error) { toast(error.message, true); }
});

$("#close-activity").addEventListener("click", () => $("#activity-dialog").close());

$("#regenerate-activity").addEventListener("click", async () => {
  try {
    state.variation += 1;
    const oldId = state.activityId;
    const result = await request(`/activities/${oldId}/regenerate`, {method: "POST", body: {variation: state.variation}});
    replaceActivity(oldId, result.activity);
    $("#activity-dialog").close(); toast("New grounded activity passed guardrails");
  } catch (error) { toast(error.message, true); }
});

$("#reject-activity").addEventListener("click", async() => {
  try {
    const result = await request(`/activities/${state.activityId}/update`, {method: "POST", body: {status: "rejected"}});
    replaceActivity(state.activityId, result.activity);
    $("#activity-dialog").close(); toast("Activity rejected. Edit or regenerate it before approval.");
  } catch (error) { toast(error.message, true); }
});

$("#prepare-next").addEventListener("click", async event => {
  const evidence = [...state.evidence.values()].filter(item => item.observation !== "not_assessed" || item.exit_ticket_correct !== null);
  if (!evidence.length) return toast("Record at least one observation or exit check", true);
  const button = event.currentTarget;
  busy(button, true, "Updating & regrouping…");
  try {
    const result = await request("/next-plan", {method: "POST", queue: true, body: {date: state.classroom.current_date, evidence}});
    if (result.queued) return toast("Evidence queued and will sync when online", true);
    result.updates.forEach(update => {
      const student = state.students.find(item => item.id === update.student_id);
      if (!student) return;
      const existing = student.competencies[update.competency_id] || {competency_id: update.competency_id};
      student.competencies[update.competency_id] = {
        ...existing,
        score: update.new_score,
        state: update.new_state,
        last_assessed: update.date,
        missed: false,
      };
      if (update.new_state === "Mastered") {
        student.missed_concepts = student.missed_concepts.filter(id => id !== update.competency_id);
      }
    });
    state.groups = result.groups; state.plan = null; state.classroom.current_date = result.next_date;
    const rajUpdate = result.updates.find(item => item.student_id === "STU020");
    const rajMove = result.movements.find(item => item.student_id === "STU020");
    const panel = $("#next-plan-result");
    panel.hidden = false;
    panel.innerHTML = `<p class="eyebrow" style="color:#a9d4c7">TOMORROW · ${esc(result.next_date)}</p><h2>Evidence changed the plan.</h2>${rajUpdate ? `<p>${esc(rajUpdate.explanation)}</p>` : ""}${rajMove ? `<div class="movement-item rajkumar"><strong>Rajkumar moved:</strong> ${esc(rajMove.from)} → ${esc(rajMove.to)}</div>` : ""}`;
    state.demo.step = "regroup"; updateDemoRail(); cachePlan();
    toast("Mastery updated and tomorrow's groups are ready");
  } catch (error) { toast(error.message, true); }
  finally { busy(button, false); }
});

$("#reset-demo").addEventListener("click", async event => {
  const button = event.currentTarget;
  busy(button, true, "Resetting…");
  try {
    await request("/reset-demo", {method: "POST", body: {}});
    state.demo = {active: true, startedAt: Date.now(), step: "attendance"};
    state.evidence.clear();
    $("#demo-rail").hidden = false;
    await bootstrap(); navigate("dashboard"); updateDemoRail();
    button.dataset.label = "↻ Restart demo";
    toast("Demo reset: notice Rajkumar returning after absence");
  } catch (error) { toast(error.message, true); }
  finally { busy(button, false); }
});

$("#print-button").addEventListener("click", () => window.print());
$("#refresh-metrics").addEventListener("click", loadMetrics);
window.addEventListener("online", () => { updateConnection(); flushQueue(); });
window.addEventListener("offline", updateConnection);
setInterval(updateDemoRail, 1000);

if ("serviceWorker" in navigator) window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
bootstrap().then(() => navigate(location.hash.slice(1) || "dashboard"));
