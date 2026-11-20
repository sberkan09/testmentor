"""Bitti ölçütü of paket 2: one test per row of the bayatlama table (docs/tasarim.md, Hangi
düzenleme neyi bayatlatır). Each test asserts the exact stale set and the model call count."""

from core.events import (
    ClusterDeleted,
    ClusterRenamed,
    ClustersMerged,
    KbDocumentAdded,
    MethodEdited,
    ProjectCardChanged,
    RequirementMoved,
    RequirementTextChanged,
    StageConfigChanged,
    TestCaseEdited,
)
from core.invalidation import Hint, analyze, apply, settle
from core.nodes import ClusterLabelContent, NodeKind, Origin, StageConfig, Status
from tests.core.helpers import (
    CL,
    CLUSTERS,
    CONFIGS,
    EMB,
    LABEL,
    METHOD,
    MX,
    PASSAGES,
    RET,
    SET,
    TC,
    TREE,
    all_cases,
    case,
    fake_result,
    produce_all,
)

ALL_MX = {MX(f"R{i}") for i in range(1, 7)}


def test_fixture_is_fresh(project):
    state, _ = project
    a = analyze(state)
    assert a.stale == frozenset()
    assert a.to_verify == frozenset()
    assert a.llm_calls == 0


def test_move_requirement(project):
    """Gereksinim A'dan B'ye taşındı → A ve B'nin setleri ve adları; 2 artımlı test, 2 ad."""
    state, _ = project
    version = state.node(SET("A")).version
    state, inv = apply(state, RequirementMoved(requirement="R2", to_cluster="B"))

    assert inv.stale == {LABEL("A"), LABEL("B"), RET("A"), RET("B"), SET("A"), SET("B")}
    assert inv.llm_calls == 4
    assert inv.to_verify == {
        TC("A", "R1"), TC("A", "R2"), TC("B", "R3"), TC("B", "R4"),
        MX("R1"), MX("R2"), MX("R3"), MX("R4"),
    }  # fmt: skip
    assert inv.hints[SET("A")] == Hint(mode="incremental")
    assert inv.hints[SET("B")] == Hint(mode="incremental")
    assert inv.removed == frozenset()
    assert not inv.requires_approval
    assert state.members("A") == ("R1",)
    assert state.members("B") == ("R2", "R3", "R4")
    assert state.node(SET("A")).status == Status.STALE
    assert state.node(SET("A")).version == version  # a status change is not a version
    assert state.node(CL("B")).content.pinned_members == ("R2",)


def test_rename_cluster(project):
    """Öbek yeniden adlandırıldı → hiçbir şey; 0."""
    state, _ = project
    before = state.node(LABEL("A"))
    state, inv = apply(state, ClusterRenamed(cluster="A", name="Oturum güvenliği"))

    assert inv.stale == frozenset()
    assert inv.to_verify == frozenset()
    assert inv.llm_calls == 0
    after = state.node(LABEL("A"))
    assert after.content == ClusterLabelContent(name="Oturum güvenliği")
    assert after.origin == Origin.EDITED
    assert after.pinned
    assert after.version == before.version + 1
    assert after.input_hash == before.input_hash
    assert after.status == Status.FRESH


def test_delete_cluster_distributes(project):
    """Öbek silindi, üyeleri dağıtıldı → üye alan öbeklerin setleri ve adları; öbek başına 1+1."""
    state, _ = project
    state, inv = apply(state, ClusterDeleted(cluster="A", destinations={"R1": "B", "R2": "C"}))

    assert inv.removed == {
        CL("A"),
        LABEL("A"), RET("A"), SET("A"), TC("A", "R1"), TC("A", "R2"),
    }  # fmt: skip
    assert inv.stale == {
        LABEL("B"), LABEL("C"), RET("B"), RET("C"), SET("B"), SET("C"),
        MX("R1"), MX("R2"),  # their covering cases were removed
    }  # fmt: skip
    assert inv.llm_calls == 4
    assert state.members("B") == ("R1", "R3", "R4")
    assert state.members("C") == ("R2", "R5", "R6")
    assert "A" not in state.keys_of(NodeKind.CLUSTER)


def test_merge_clusters(project):
    """İki öbek birleştirildi → yeni öbeğin seti ve adı; 1 test (birleştirme), 1 ad."""
    state, _ = project
    state, inv = apply(state, ClustersMerged(sources=("A", "B"), new_cluster="D"))

    assert inv.removed == {
        CL("A"), CL("B"), LABEL("A"), LABEL("B"), RET("A"), RET("B"), SET("A"), SET("B"),
        TC("A", "R1"), TC("A", "R2"), TC("B", "R3"), TC("B", "R4"),
    }  # fmt: skip
    assert inv.stale == {
        LABEL("D"), RET("D"), SET("D"),
        MX("R1"), MX("R2"), MX("R3"), MX("R4"),
    }  # fmt: skip
    assert inv.llm_calls == 2
    assert inv.hints[SET("D")] == Hint(mode="merge", sources=(SET("A"), SET("B")))
    assert state.members("D") == ("R1", "R2", "R3", "R4")
    assert state.node(SET("D")).content is None


def test_requirement_text_changed(project):
    """Gereksinim metni değişti → embedding, yöntem, öbeğin seti ve adı; 3 (yöntem, test, ad).
    The clustering tree is stale but membership does not change."""
    state, _ = project
    state, inv = apply(
        state, RequirementTextChanged(requirement="R1", text="Sistem, girişi 5 denemede kilitler.")
    )

    assert inv.stale == {
        EMB("R1"), TREE, METHOD("R1"), LABEL("A"), RET("A"), SET("A"), MX("R1"),
    }  # fmt: skip
    assert inv.llm_calls == 3
    assert inv.to_verify == {TC("A", "R1"), TC("A", "R2"), MX("R2")}
    assert {k: state.members(k) for k in CLUSTERS} == CLUSTERS
    # The set waits for its method and retrieval to be produced first.
    assert SET("A") not in analyze(state).ready


def test_test_case_edited(project):
    """Test durumu elle düzenlendi → yalnızca matris satırları (eski ve yeni covers); 0."""
    state, _ = project
    before = state.node(TC("A", "R1"))
    edited = case("R1", covers=("R1", "R3"), title="R1 ve R3 birlikte")
    state, inv = apply(state, TestCaseEdited(case=TC("A", "R1").key, content=edited))

    assert inv.stale == {MX("R1"), MX("R3")}
    assert inv.llm_calls == 0
    assert inv.to_verify == frozenset()
    after = state.node(TC("A", "R1"))
    assert after.content == edited
    assert after.origin == Origin.EDITED and after.pinned
    assert after.version == before.version + 1
    assert state.node(SET("A")).status == Status.FRESH


def test_kb_document_added(project):
    """Bilgi havuzuna belge eklendi → getirilen parçaları değişen öbeklerin setleri; öbek başına 1.
    Early cutoff: sets wait for their retrieval and stay fresh if the passages did not change."""
    state, _ = project
    state, inv = apply(state, KbDocumentAdded(document_id="doc2", index_version="v2"))

    assert inv.stale == {RET("A"), RET("B"), RET("C")}
    assert inv.llm_calls == 0
    assert inv.to_verify == {SET("A"), SET("B"), SET("C")} | all_cases() | ALL_MX
    assert state.node(SET("A")).status == Status.FRESH

    passages = PASSAGES | {"A": ("doc2#1", "doc1#1")}
    for k in ("A", "B", "C"):
        state = settle(state, RET(k), fake_result(state, RET(k), passages)).state

    a = analyze(state)
    assert a.stale == {SET("A")}
    assert a.llm_calls == 1
    assert a.to_verify == {TC("A", "R1"), TC("A", "R2"), MX("R1"), MX("R2")}
    assert a.ready == (SET("A"),)


def test_stage_version_changed(project):
    """Prompt ya da model sürümü değişti → o aşamanın tüm çıktıları, kullanıcı onayıyla."""
    state, _ = project
    new = CONFIGS[NodeKind.TEST_SET].model_copy(update={"prompt_version": "t2"})
    state, inv = apply(state, StageConfigChanged(stage=NodeKind.TEST_SET, config=new))

    assert inv.stale == {SET("A"), SET("B"), SET("C")}
    assert inv.llm_calls == 3
    assert inv.requires_approval
    assert inv.to_verify == all_cases() | ALL_MX


def test_stage_model_changed_keeps_pinned(project):
    """Same row for the label stage: a pinned (renamed) label is stale but only warned about."""
    state, _ = project
    state, _ = apply(state, ClusterRenamed(cluster="A", name="Oturum güvenliği"))
    new = StageConfig(prompt_version="l1", model="other-llm")
    state, inv = apply(state, StageConfigChanged(stage=NodeKind.CLUSTER_LABEL, config=new))

    assert inv.stale == {LABEL("A"), LABEL("B"), LABEL("C")}
    assert inv.pinned_warnings == {LABEL("A")}
    assert inv.llm_calls == 2
    assert inv.requires_approval
    assert LABEL("A") not in analyze(state).ready


def test_method_edited(project):
    """Doğrulama yöntemi elle değişti (paket 2) → öbeğin seti; 1."""
    state, _ = project
    state, inv = apply(state, MethodEdited(requirement="R1", methods=("Analiz",)))

    assert inv.stale == {SET("A"), MX("R1")}
    assert inv.llm_calls == 1
    node = state.node(METHOD("R1"))
    assert node.origin == Origin.EDITED and node.pinned and node.status == Status.FRESH


def test_project_card_changed(project):
    """Proje kartı değişti (paket 2) → tüm model çıktıları, kullanıcı onayıyla."""
    state, _ = project
    state, inv = apply(state, ProjectCardChanged(text="Proje: Örnek portal v2."))

    labels = {LABEL(k) for k in CLUSTERS}
    sets = {SET(k) for k in CLUSTERS}
    methods = {METHOD(f"R{i}") for i in range(1, 7)}
    assert inv.stale == labels | sets | methods
    assert inv.llm_calls == 12
    assert inv.requires_approval


def test_every_row_converges(project):
    """After any row, producing the ready nodes leaves nothing stale."""
    state, cache = project
    state, _ = apply(state, RequirementMoved(requirement="R2", to_cluster="B"))
    state = produce_all(state, cache)
    a = analyze(state)
    assert a.stale == frozenset() and a.to_verify == frozenset()
    # The matrix row sees the identical case that moved from A to B under its new key.
    assert state.node(MX("R2")).content.test_case_keys == (TC("B", "R2").key,)
