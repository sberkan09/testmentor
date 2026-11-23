/* Otomatik üretildi: npm run types (api/schema.json). Elle düzenleme. */

export type Name = string;
export type Key = string;
export type CardText = string;
export type Name1 = string;
export type Criterion = string;
export type Methods = MethodDef[];
export type Text = string;
export type Id = string | null;
export type Language = string | null;
export type Source = string | null;
export type Sheet = string | null;
export type Command =
  | MoveRequirement
  | CreateCluster
  | DeleteCluster
  | MergeClusters
  | RenameCluster
  | SetGranularity
  | EditRequirement
  | EditTestCase
  | EditMethod
  | EditProjectCard
  | Pin
  | Unpin
  | KeepMine
  | SetStageMode
  | ApproveStage
  | Regenerate
  | Undo
  | Focus;
export type Type = "move_requirement";
export type Requirement = string;
export type ToCluster = string;
export type Type1 = "create_cluster";
/**
 * @minItems 1
 */
export type Members = [string, ...string[]];
export type Cluster = string | null;
export type Type2 = "delete_cluster";
export type Cluster1 = string;
export type Type3 = "merge_clusters";
/**
 * @minItems 2
 */
export type Sources = [string, string, ...string[]];
export type NewCluster = string | null;
export type Type4 = "rename_cluster";
export type Cluster2 = string;
export type Name2 = string;
export type Type5 = "set_granularity";
export type DistanceThreshold = number;
export type Type6 = "edit_requirement";
export type Requirement1 = string;
export type Text1 = string;
export type Type7 = "edit_test_case";
export type Case = string;
export type Kind = "test_case";
export type Id1 = string;
export type Title = string;
/**
 * @minItems 1
 */
export type Covers = [string, ...string[]];
export type Type8 = string;
export type Priority = string;
export type Preconditions = string;
export type TestInputs = string;
export type Assumptions = string;
/**
 * @minItems 1
 */
export type Steps = [Step, ...Step[]];
export type No = number;
export type Action = string;
export type Expected = string;
export type Type9 = "edit_method";
export type Requirement2 = string;
/**
 * @minItems 1
 */
export type Methods1 = [string, ...string[]];
export type Type10 = "edit_project_card";
export type Text2 = string;
export type Methods2 = MethodDef[] | null;
export type Type11 = "pin";
/**
 * Declared in topological order: every kind depends only on kinds listed before it.
 */
export type NodeKind =
  | "requirement"
  | "project_card"
  | "kb_index"
  | "cluster"
  | "embedding"
  | "clustering"
  | "method"
  | "cluster_label"
  | "retrieval"
  | "test_set"
  | "test_case"
  | "matrix_row";
export type Key1 = string;
export type Type12 = "unpin";
export type Type13 = "keep_mine";
export type Type14 = "set_stage_mode";
export type Mode = "auto" | "approval";
export type Type15 = "approve_stage";
export type Type16 = "regenerate";
export type Type17 = "undo";
export type Type18 = "focus";
export type Nodes = NodeRef[];
export type Accepted = boolean;
export type Seq = number;
export type Reason = string;
export type ProjectId = string;
export type Name3 = string;
export type Seq1 = number;
export type Status = "fresh" | "stale" | "running" | "failed";
export type Pinned = boolean;
export type Origin = "generated" | "edited";
export type Version = number;
export type Content = {
  [k: string]: unknown;
} | null;
export type ProducedBy = {
  [k: string]: unknown;
} | null;
export type Waiting = boolean;
export type PinnedWarning = boolean;
export type Nodes1 = NodeView[];
export type Mode1 = "auto" | "approval";
export type Fresh = number;
export type Stale = number;
export type Running = number;
export type Failed = number;
export type WaitingApproval = boolean;
export type Stages = StageView[];
export type Id2 = string;
export type Priority1 = "P0" | "P1" | "P2";
export type State = "queued" | "waiting_approval" | "running";
export type Jobs = JobView[];
export type RequirementId = string;
export type Text3 = string;
export type Language1 = string;
export type Cluster3 = string;
export type ClusterName = string;
export type Methods3 = string[];
export type TestCaseKeys = string[];
export type Covered = boolean;
export type Warning = "" | "test_without_case" | "case_without_test_method";
export type Matrix = MatrixRowView[];
export type Seq2 = number;
export type ProjectId1 = string;
export type Type19 =
  | "command_applied"
  | "command_rejected"
  | "node_created"
  | "node_updated"
  | "node_removed"
  | "node_stale"
  | "job_started"
  | "job_progress"
  | "job_done"
  | "job_failed"
  | "stage_waiting_approval"
  | "lock_changed";
export type Actor = string;
export type Id3 = string;
export type Name4 = string;
export type Chunks = number;
export type AddedBy = string;
export type AddedAt = number;
export type Seq3 = number;
export type Seq4 = number;
export type Mode2 = "header" | "password";
export type User = string;
export type Password = string;
export type Token = string;
export type User1 = string;
export type ExpiresAt = number;

/**
 * Container so that every model lands in one schema with shared `$defs`.
 */
export interface ApiContract {
  import_request: ImportRequest;
  command_request: CommandRequest;
  command_result: CommandResult;
  snapshot: Snapshot;
  server_event: ServerEvent;
  node_view: NodeView;
  matrix_row: MatrixRowView;
  kb_document: KbDocumentView;
  kb_upload_result: KbUploadResult;
  kb_remove_result: KbRemoveResult;
  auth_config: AuthConfig;
  login_request: LoginRequest;
  login_result: LoginResult;
}
/**
 * `POST /projects` body (multipart: this as JSON field `meta` plus the file).
 */
export interface ImportRequest {
  name: Name;
  key: Key;
  card_text?: CardText;
  methods?: Methods;
  mapping: ColumnMapping;
  sheet?: Sheet;
}
/**
 * One verification method of the project and its criterion (docs/tasarim.md, Proje kartı).
 */
export interface MethodDef {
  name: Name1;
  criterion?: Criterion;
}
/**
 * Which source columns hold what. Only `text` is required; a missing id gets `REQ-<n>`.
 */
export interface ColumnMapping {
  text: Text;
  id?: Id;
  language?: Language;
  source?: Source;
}
/**
 * `POST /projects/{id}/commands` body. The actor comes from the `X-User` header.
 */
export interface CommandRequest {
  command: Command;
  expected_versions?: ExpectedVersions;
}
export interface MoveRequirement {
  type?: Type;
  requirement: Requirement;
  to_cluster: ToCluster;
}
export interface CreateCluster {
  type?: Type1;
  members: Members;
  cluster?: Cluster;
}
export interface DeleteCluster {
  type?: Type2;
  cluster: Cluster1;
  destinations: Destinations;
}
export interface Destinations {
  [k: string]: string;
}
export interface MergeClusters {
  type?: Type3;
  sources: Sources;
  new_cluster?: NewCluster;
}
export interface RenameCluster {
  type?: Type4;
  cluster: Cluster2;
  name: Name2;
}
/**
 * Re-cut the clustering tree (`core.stages.clustering.recut`); pinned assignments stay.
 */
export interface SetGranularity {
  type?: Type5;
  distance_threshold: DistanceThreshold;
}
export interface EditRequirement {
  type?: Type6;
  requirement: Requirement1;
  text: Text1;
}
export interface EditTestCase {
  type?: Type7;
  case: Case;
  content: TestCaseContent;
}
/**
 * Same fields as the generation schema (`core.schemas.case_set_model`); labels are plain
 * strings here because the label lists come from project configuration.
 */
export interface TestCaseContent {
  kind?: Kind;
  id: Id1;
  title: Title;
  covers: Covers;
  type: Type8;
  priority: Priority;
  preconditions?: Preconditions;
  test_inputs?: TestInputs;
  assumptions?: Assumptions;
  steps: Steps;
}
export interface Step {
  no: No;
  action: Action;
  expected: Expected;
}
export interface EditMethod {
  type?: Type9;
  requirement: Requirement2;
  methods: Methods1;
}
/**
 * Stales every model output; the regeneration waits for approval (`APPROVAL_EVENTS`).
 */
export interface EditProjectCard {
  type?: Type10;
  text: Text2;
  methods?: Methods2;
}
export interface Pin {
  type?: Type11;
  node: NodeRef;
}
export interface NodeRef {
  kind: NodeKind;
  key: Key1;
}
export interface Unpin {
  type?: Type12;
  node: NodeRef;
}
/**
 * Fark ekranı "benimkini koru" (`core.events.NodeKept`).
 */
export interface KeepMine {
  type?: Type13;
  node: NodeRef;
}
export interface SetStageMode {
  type?: Type14;
  stage: NodeKind;
  mode: Mode;
}
export interface ApproveStage {
  type?: Type15;
  stage: NodeKind;
}
/**
 * Retry a failed node, or produce a stale node now (priority P0).
 */
export interface Regenerate {
  type?: Type16;
  node: NodeRef;
}
/**
 * Undo the actor's own last undoable command (per user, docs/tasarim.md).
 */
export interface Undo {
  type?: Type17;
}
/**
 * The nodes the actor is looking at; their jobs get P0. Not an undoable command.
 */
export interface Focus {
  type?: Type18;
  nodes?: Nodes;
}
export interface ExpectedVersions {
  [k: string]: number;
}
export interface CommandResult {
  accepted: Accepted;
  seq: Seq;
  reason?: Reason;
  current_versions?: CurrentVersions;
}
export interface CurrentVersions {
  [k: string]: number;
}
/**
 * `GET /projects/{id}/snapshot`: the whole project at event `seq`.
 */
export interface Snapshot {
  project_id: ProjectId;
  name: Name3;
  seq: Seq1;
  nodes: Nodes1;
  stages: Stages;
  jobs: Jobs;
  matrix: Matrix;
  locks?: Locks;
}
/**
 * One node as clients see it (`core.nodes.Node` without hashes).
 */
export interface NodeView {
  ref: NodeRef;
  status: Status;
  pinned: Pinned;
  origin: Origin;
  version: Version;
  content: Content;
  produced_by?: ProducedBy;
  waiting?: Waiting;
  pinned_warning?: PinnedWarning;
}
export interface StageView {
  stage: NodeKind;
  mode: Mode1;
  fresh: Fresh;
  stale: Stale;
  running: Running;
  failed: Failed;
  waiting_approval: WaitingApproval;
}
export interface JobView {
  id: Id2;
  node: NodeRef;
  priority: Priority1;
  state: State;
}
/**
 * One row of the matrix view (paket 4, `core.matrix_view`).
 */
export interface MatrixRowView {
  requirement_id: RequirementId;
  text: Text3;
  language: Language1;
  cluster: Cluster3;
  cluster_name: ClusterName;
  methods: Methods3;
  test_case_keys: TestCaseKeys;
  covered: Covered;
  warning?: Warning;
}
export interface Locks {
  [k: string]: string;
}
/**
 * `WS /projects/{id}/events` message. `seq` grows by one per event within a project; a
 * reconnecting client sends its last `seq` and receives the missed events, or a `snapshot`
 * message when they are no longer kept.
 */
export interface ServerEvent {
  seq: Seq2;
  project_id: ProjectId1;
  type: Type19;
  actor?: Actor;
  payload?: Payload;
}
export interface Payload {
  [k: string]: unknown;
}
export interface KbDocumentView {
  id: Id3;
  name: Name4;
  chunks: Chunks;
  added_by?: AddedBy;
  added_at?: AddedAt;
}
export interface KbUploadResult {
  document: KbDocumentView;
  seq: Seq3;
}
export interface KbRemoveResult {
  seq: Seq4;
}
export interface AuthConfig {
  mode: Mode2;
}
export interface LoginRequest {
  user: User;
  password: Password;
}
export interface LoginResult {
  token: Token;
  user: User1;
  expires_at: ExpiresAt;
}
