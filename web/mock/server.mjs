// Sözleşmeye (worker/contracts.py, api/schema.json) göre çalışan küçük sahte API.
// Arka uç hazır değilken ön yüzü geliştirmek ve gözle denetlemek içindir; testlerde kullanılmaz.
// Kullanım: npm run mock (8000 numaralı kapı), sonra TESTMENTOR_API=http://127.0.0.1:8000 npm run dev
import http from "node:http";
import { WebSocketServer } from "ws";

const PORT = Number(process.env.PORT ?? 8000);
const projects = new Map();
const METHODS = [
  { name: "Test", criterion: "Çalışan sistemde senaryo koşularak doğrulanır." },
  { name: "İnceleme", criterion: "Belge ya da tasarım incelenerek doğrulanır." },
  { name: "Analiz", criterion: "Hesap ya da çözümleme ile doğrulanır." },
];
const NAMES = ["Kimlik doğrulama ve oturum", "Başvuru oluşturma", "Belge yükleme", "Bildirimler", "Raporlama", "Yetkilendirme", "Denetim izi"];
const RATIONALES = [
  "Kullanıcının sisteme güvenli girişi ve oturumun yönetimi.",
  "Başvuru formunun doldurulması, kaydedilmesi ve gönderilmesi.",
  "Ek belgelerin yüklenmesi, biçim ve boyut denetimleri.",
  "Kullanıcıya giden e-posta ve ekran bildirimleri.",
  "Yönetici raporları ve dışa aktarım.",
  "Rol ve izin tabanlı erişim denetimi.",
  "Kritik işlemlerin kaydı ve izlenebilirliği.",
];

const rk = (kind, key) => `${kind}:${key}`;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function parseCsv(text) {
  const t = text.replace(/^\u{FEFF}/u, "");
  const first = t.split(/\r?\n/, 1)[0] ?? "";
  const delim = (first.match(/;/g) ?? []).length > (first.match(/,/g) ?? []).length ? ";" : ",";
  const rows = [];
  let row = [], cell = "", q = false;
  for (let i = 0; i < t.length; i++) {
    const c = t[i];
    if (q) {
      if (c === '"') { if (t[i + 1] === '"') { cell += '"'; i++; } else q = false; } else cell += c;
    } else if (c === '"') q = true;
    else if (c === delim) { row.push(cell); cell = ""; }
    else if (c === "\n" || c === "\r") { if (c === "\r" && t[i + 1] === "\n") i++; row.push(cell); cell = ""; rows.push(row); row = []; }
    else cell += c;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  return rows.filter((r) => r.some((x) => x.trim()));
}

function parseMultipart(buf, contentType) {
  const boundary = /boundary=(.+)$/.exec(contentType)?.[1];
  const parts = {};
  for (const raw of buf.toString("utf8").split(`--${boundary}`)) {
    const m = /name="([^"]+)"[\s\S]*?\r\n\r\n([\s\S]*?)\r\n$/.exec(raw);
    if (m) parts[m[1]] = m[2];
  }
  return parts;
}

function makeProject(meta, csvText) {
  const rows = parseCsv(csvText);
  const head = rows[0] ?? [];
  const col = (name) => (name ? head.indexOf(name) : -1);
  const iText = col(meta.mapping.text), iId = col(meta.mapping.id), iLang = col(meta.mapping.language);
  const p = {
    id: meta.key, name: meta.name, seq: 0, nodes: new Map(), events: [], clients: new Set(), locks: {}, jobs: new Map(),
    undo: new Map(), jobSeq: 0,
    stages: ["cluster_label", "method", "test_set", "test_case", "matrix_row"].map((stage) => ({ stage, mode: "auto", fresh: 0, stale: 0, running: 0, failed: 0, waiting_approval: false })),
  };
  p.nodes.set(rk("project_card", "card"), view("project_card", "card", { kind: "project_card", text: meta.card_text || `Proje: ${meta.name}`, methods: METHODS }));
  const reqs = rows.slice(1).map((r, i) => ({ id: iId >= 0 ? r[iId] : `REQ-${i + 1}`, text: r[iText] ?? "", language: iLang >= 0 ? r[iLang] : "tr" }));
  const per = Math.max(3, Math.ceil(reqs.length / 6));
  reqs.forEach((r, i) => {
    p.nodes.set(rk("requirement", r.id), view("requirement", r.id, { kind: "requirement", ...r, source: "" }));
    const m = i % 5 === 4 ? ["İnceleme"] : ["Test"];
    p.nodes.set(rk("method", r.id), view("method", r.id, { kind: "method", methods: m, rationale: m[0] === "Test" ? "Davranış çalıştırılarak gözlenebilir." : "Belge incelemesiyle doğrulanır." }));
  });
  for (let c = 0; c * per < reqs.length; c++) {
    const key = String.fromCharCode(65 + c);
    const members = reqs.slice(c * per, (c + 1) * per).map((r) => r.id).sort();
    p.nodes.set(rk("cluster", key), view("cluster", key, { kind: "cluster", members, pinned_members: [] }));
    p.nodes.set(rk("cluster_label", key), view("cluster_label", key, null, { status: "stale" }));
    p.nodes.set(rk("test_set", key), view("test_set", key, { kind: "test_set", case_keys: [] }, { status: "stale" }));
  }
  return p;
}

function view(kind, key, content, extra = {}) {
  return { ref: { kind, key }, status: "fresh", pinned: false, origin: "generated", version: content ? 1 : 0, content, produced_by: null, waiting: false, pinned_warning: false, ...extra };
}

function counts(p) {
  return p.stages.map((s) => {
    const ns = [...p.nodes.values()].filter((n) => n.ref.kind === s.stage);
    const c = (st) => ns.filter((n) => n.status === st).length;
    return { ...s, fresh: c("fresh"), stale: c("stale"), running: c("running"), failed: c("failed") };
  });
}

function matrix(p) {
  const cases = [...p.nodes.values()].filter((n) => n.ref.kind === "test_case");
  const clusters = [...p.nodes.values()].filter((n) => n.ref.kind === "cluster");
  return [...p.nodes.values()].filter((n) => n.ref.kind === "requirement").map((r) => {
    const id = r.content.id;
    const keys = cases.filter((c) => c.content?.covers.includes(id)).map((c) => c.ref.key);
    const cl = clusters.find((c) => c.content.members.includes(id));
    const label = cl && p.nodes.get(rk("cluster_label", cl.ref.key));
    const methods = p.nodes.get(rk("method", id))?.content?.methods ?? [];
    const warning = methods.includes("Test") && !keys.length ? "test_without_case" : !methods.includes("Test") && keys.length ? "case_without_test_method" : "";
    return { requirement_id: id, text: r.content.text, language: r.content.language, cluster: cl?.ref.key ?? "", cluster_name: label?.content?.name ?? cl?.ref.key ?? "", methods, test_case_keys: keys, covered: keys.length > 0, warning };
  });
}

function snapshot(p) {
  return { project_id: p.id, name: p.name, seq: p.seq, nodes: [...p.nodes.values()], stages: counts(p), jobs: [...p.jobs.values()], matrix: matrix(p), locks: p.locks };
}

function emit(p, type, payload, actor = "", persist = true) {
  const ev = { seq: persist ? ++p.seq : p.seq, project_id: p.id, type, actor, payload };
  if (persist) p.events.push(ev);
  const msg = JSON.stringify(ev);
  for (const ws of p.clients) if (ws.readyState === 1) ws.send(msg);
  return ev;
}

function put(p, node, actor, type = "node_updated") {
  p.nodes.set(rk(node.ref.kind, node.ref.key), node);
  emit(p, type, { node }, actor);
}

async function produce(p, node, text, build) {
  const job = { id: `j${++p.jobSeq}`, node: node.ref, priority: "P2", state: "running" };
  p.jobs.set(job.id, job);
  put(p, { ...node, status: "running" }, "");
  emit(p, "job_started", { job });
  for (const word of text.split(" ")) {
    emit(p, "job_progress", { job, text: word + " " }, "", false);
    await sleep(60);
  }
  p.jobs.delete(job.id);
  const cur = p.nodes.get(rk(node.ref.kind, node.ref.key)) ?? node;
  if (cur.pinned && cur.content) { put(p, { ...cur, status: "fresh" }, ""); emit(p, "job_done", { job }); return; }
  put(p, { ...cur, status: "fresh", content: build(), version: cur.version + 1 }, "");
  emit(p, "job_done", { job });
}

async function pipeline(p) {
  const clusters = [...p.nodes.values()].filter((n) => n.ref.kind === "cluster");
  await sleep(400);
  for (const [i, c] of clusters.entries()) {
    const name = NAMES[i % NAMES.length];
    await produce(p, p.nodes.get(rk("cluster_label", c.ref.key)), `${name}: ${RATIONALES[i % RATIONALES.length]}`, () => ({ kind: "cluster_label", name, rationale: RATIONALES[i % RATIONALES.length] }));
  }
  for (const c of clusters) {
    const cur = p.nodes.get(rk("cluster", c.ref.key));
    const caseKeys = [];
    for (const rid of cur.content.members) {
      const methods = p.nodes.get(rk("method", rid)).content.methods;
      if (!methods.includes("Test")) continue;
      const key = `${c.ref.key}:TC-${rid}`;
      caseKeys.push(key);
      const req = p.nodes.get(rk("requirement", rid)).content;
      const content = testCase(`TC-${rid}`, req);
      p.nodes.set(rk("test_case", key), view("test_case", key, null, { status: "stale" }));
      await produce(p, p.nodes.get(rk("test_case", key)), `${content.title}: ${content.steps.map((s) => s.action).join(" ")}`, () => content);
    }
    const set = p.nodes.get(rk("test_set", c.ref.key));
    put(p, { ...set, status: "fresh", version: set.version + 1, content: { kind: "test_set", case_keys: caseKeys } }, "");
  }
}

function testCase(id, req) {
  const short = req.text.length > 70 ? `${req.text.slice(0, 67)}…` : req.text;
  return {
    kind: "test_case", id, title: `${req.id} doğrulama: ${short}`, covers: [req.id], type: "Fonksiyonel", priority: "Yüksek",
    preconditions: "Sistem çalışır durumda ve test kullanıcısı tanımlı.", test_inputs: "Geçerli test verisi.", assumptions: "",
    steps: [
      { no: 1, action: "Sisteme test kullanıcısı ile giriş yap.", expected: "Giriş başarılı olur, ana sayfa açılır." },
      { no: 2, action: `Gereksinimin tarif ettiği işlemi uygula: ${short}`, expected: "İşlem gereksinimde belirtilen sonucu verir." },
    ],
  };
}

function reply(res, status, body, type = "application/json") {
  res.writeHead(status, { "Content-Type": type, "Access-Control-Allow-Origin": "*" });
  res.end(typeof body === "string" || Buffer.isBuffer(body) ? body : JSON.stringify(body));
}

async function readBody(req) {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  return Buffer.concat(chunks);
}

function runCommand(p, body, actor) {
  const { command: cmd, expected_versions: exp = {} } = body;
  const fail = (reason) => ({ accepted: false, seq: p.seq, reason, current_versions: Object.fromEntries(Object.keys(exp).map((k) => [k, p.nodes.get(k)?.version ?? 0])) });
  for (const [k, v] of Object.entries(exp)) if ((p.nodes.get(k)?.version ?? 0) !== v) return [409, fail("version_conflict")];
  const lockKey = cmd.case ? rk("test_case", cmd.case) : cmd.requirement ? rk("requirement", cmd.requirement) : null;
  if (lockKey && p.locks[lockKey] && p.locks[lockKey] !== actor && cmd.type.startsWith("edit_")) return [423, fail("locked")];
  const bump = (n, patch) => ({ ...n, ...patch, version: n.version + 1 });
  const done = () => { emit(p, "command_applied", { command: cmd, result: { accepted: true, seq: p.seq, reason: "", current_versions: {} } }, actor); return [200, { accepted: true, seq: p.seq, reason: "", current_versions: {} }]; };
  const inverse = (c) => { const s = p.undo.get(actor) ?? []; s.push(c); p.undo.set(actor, s); };
  switch (cmd.type) {
    case "move_requirement": {
      const from = [...p.nodes.values()].find((n) => n.ref.kind === "cluster" && n.content.members.includes(cmd.requirement));
      const to = p.nodes.get(rk("cluster", cmd.to_cluster));
      if (!to) return [422, fail("invalid: bilinmeyen öbek")];
      if (from && from.ref.key !== to.ref.key) {
        if (from.content.members.length === 1) return [422, fail("invalid: öbek boş kalamaz")];
        put(p, bump(from, { content: { ...from.content, members: from.content.members.filter((m) => m !== cmd.requirement) } }), actor);
        put(p, bump(to, { content: { ...to.content, members: [...to.content.members, cmd.requirement].sort() } }), actor);
        inverse({ type: "move_requirement", requirement: cmd.requirement, to_cluster: from.ref.key });
      }
      return done();
    }
    case "rename_cluster": {
      const n = p.nodes.get(rk("cluster_label", cmd.cluster));
      if (!n) return [422, fail("invalid")];
      inverse({ type: "rename_cluster", cluster: cmd.cluster, name: n.content?.name ?? cmd.cluster });
      put(p, bump(n, { content: { ...(n.content ?? { kind: "cluster_label", rationale: "" }), name: cmd.name }, origin: "edited", pinned: true }), actor);
      return done();
    }
    case "edit_test_case": {
      const n = p.nodes.get(rk("test_case", cmd.case));
      if (!n) return [422, fail("invalid")];
      inverse({ type: "edit_test_case", case: cmd.case, content: n.content });
      put(p, bump(n, { content: cmd.content, origin: "edited", pinned: true, pinned_warning: false }), actor);
      return done();
    }
    case "edit_requirement": {
      const n = p.nodes.get(rk("requirement", cmd.requirement));
      put(p, bump(n, { content: { ...n.content, text: cmd.text }, origin: "edited" }), actor);
      return done();
    }
    case "edit_method": {
      const n = p.nodes.get(rk("method", cmd.requirement));
      put(p, bump(n, { content: { ...n.content, methods: cmd.methods }, origin: "edited" }), actor);
      return done();
    }
    case "pin":
    case "unpin": {
      const n = p.nodes.get(rk(cmd.node.kind, cmd.node.key));
      if (!n?.content) return [422, fail("invalid: içeriksiz düğüm sabitlenemez")];
      put(p, bump(n, { pinned: cmd.type === "pin" }), actor);
      return done();
    }
    case "keep_mine": {
      const n = p.nodes.get(rk(cmd.node.kind, cmd.node.key));
      put(p, bump(n, { status: "fresh", pinned_warning: false }), actor);
      return done();
    }
    case "set_stage_mode":
      p.stages.find((s) => s.stage === cmd.stage).mode = cmd.mode;
      return done();
    case "approve_stage":
      p.stages.find((s) => s.stage === cmd.stage).waiting_approval = false;
      return done();
    case "undo": {
      const s = p.undo.get(actor) ?? [];
      const last = s.pop();
      if (!last) return [409, fail("nothing_to_undo")];
      return runCommand(p, { command: last }, actor);
    }
    case "regenerate": {
      const n = p.nodes.get(rk(cmd.node.kind, cmd.node.key));
      if (n) void produce(p, { ...n, pinned: false }, "Yeniden üretiliyor", () => n.content);
      return done();
    }
    case "focus":
      return [200, { accepted: true, seq: p.seq, reason: "", current_versions: {} }];
    default:
      return [422, fail(`invalid: sahte API ${cmd.type} komutunu desteklemiyor`)];
  }
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://x");
  const parts = url.pathname.split("/").filter(Boolean);
  const actor = req.headers["x-user"] ?? "";
  if (req.method === "OPTIONS") return reply(res, 204, "");
  if (parts[0] !== "projects") return reply(res, 404, { detail: "yok" });
  if (parts.length === 1 && req.method === "GET") return reply(res, 200, [...projects.values()].map((p) => ({ id: p.id, name: p.name })));
  if (parts.length === 1 && req.method === "POST") {
    const f = parseMultipart(await readBody(req), req.headers["content-type"] ?? "");
    const meta = JSON.parse(f.meta ?? "{}");
    if (projects.has(meta.key)) return reply(res, 409, { detail: "anahtar kullanımda" });
    const p = makeProject(meta, f.file ?? "");
    projects.set(p.id, p);
    void pipeline(p);
    return reply(res, 200, snapshot(p));
  }
  const p = projects.get(parts[1] ?? "");
  if (!p) return reply(res, 404, { detail: "proje yok" });
  if (parts[2] === "snapshot") return reply(res, 200, snapshot(p));
  if (parts[2] === "commands" && req.method === "POST") {
    if (!actor) return reply(res, 400, { detail: "X-User yok" });
    const [status, body] = runCommand(p, JSON.parse((await readBody(req)).toString()), actor);
    return reply(res, status, body);
  }
  if (parts[2] === "locks" && req.method === "POST") {
    const { ref } = JSON.parse((await readBody(req)).toString());
    const k = rk(ref.kind, ref.key);
    if (p.locks[k] && p.locks[k] !== actor) return reply(res, 423, { detail: "kilitli" });
    if (p.locks[k] !== actor) { p.locks[k] = actor; emit(p, "lock_changed", { ref: k, user: actor }, actor); }
    clearTimeout(p.lockTimers?.[k]);
    p.lockTimers = { ...p.lockTimers, [k]: setTimeout(() => { delete p.locks[k]; emit(p, "lock_changed", { ref: k, user: null }, actor); }, 60000) };
    return reply(res, 200, { ok: true });
  }
  if (parts[2] === "matrix.xlsx") return reply(res, 200, Buffer.from("PK\u0003\u0004 sahte xlsx"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
  return reply(res, 404, { detail: "yok" });
});

const wss = new WebSocketServer({ noServer: true });
server.on("upgrade", (req, socket, head) => {
  const url = new URL(req.url, "http://x");
  const m = /^\/projects\/([^/]+)\/events$/.exec(url.pathname);
  const p = m && projects.get(decodeURIComponent(m[1]));
  if (!p) return socket.destroy();
  wss.handleUpgrade(req, socket, head, (ws) => {
    const after = Number(url.searchParams.get("after") ?? 0);
    const missed = p.events.filter((e) => e.seq > after);
    if (after > p.seq || (after < p.seq && p.events.length > 500 && missed.length !== p.seq - after)) ws.send(JSON.stringify({ type: "snapshot", snapshot: snapshot(p) }));
    else for (const e of missed) ws.send(JSON.stringify(e));
    p.clients.add(ws);
    ws.on("close", () => p.clients.delete(ws));
  });
});

server.listen(PORT, "127.0.0.1", () => console.log(`sahte API http://127.0.0.1:${PORT}`));
