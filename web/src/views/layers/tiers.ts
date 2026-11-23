/** Thread drawing tiers of the layer view (no imports: the e2e test reads these too).
 *
 *  Above EXACT_THREADS_BELOW × the framing distance every island shows bundled threads (each
 *  covered requirement → the island's test case hub → the island's matrix block). Below it only
 *  the islands nearest the camera target show threads, the exact ones (requirement → test case
 *  → matrix row), within a segment budget that shrinks as the camera comes closer. The values
 *  come from a sweep under software rendering (docs/paketler/paket-9-plan.md). */
export type ThreadTier = "bundled" | "exact";

export const EXACT_THREADS_BELOW = 0.45;
export const EXACT_SEGMENT_BUDGET = 1600;
