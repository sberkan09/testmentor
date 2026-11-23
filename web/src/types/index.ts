export type {
  Command,
  CommandRequest,
  CommandResult,
  ColumnMapping,
  ImportRequest,
  JobView,
  KbDocumentView,
  KbRemoveResult,
  KbUploadResult,
  MatrixRowView,
  MethodDef,
  NodeRef,
  NodeView,
  ServerEvent,
  Snapshot,
  StageView,
  Step,
  TestCaseContent,
} from "./contract";

import type { NodeRef } from "./contract";

export type NodeKind = NodeRef["kind"];

/** `str(NodeRef)` of the contract: "test_case:A:TC-1". */
export function refKey(ref: NodeRef): string {
  return `${ref.kind}:${ref.key}`;
}

export function makeRef(kind: NodeKind, key: string): NodeRef {
  return { kind, key };
}
