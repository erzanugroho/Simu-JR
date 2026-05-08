import asyncio
import os

os.environ["SIMU_DISABLE_RAG_IMPORT"] = "1"
from core.orchestrator import SimulationOrchestrator


class FastHearingOrchestrator(SimulationOrchestrator):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("enable_validator", False)
        kwargs.setdefault("retriever", None)
        super().__init__(*args, **kwargs)

    async def _fetch_uu_context_from_api(self, draft: str) -> str:
        return ""

    async def _generate_agent_response(self, agent, prompt: str, rag_context: str = "") -> str:
        return f"{agent.name}: {prompt[:32]}"


def test_perbaikan_profile_does_not_run_other_rounds():
    orch = FastHearingOrchestrator(
        1,
        hearing_mode="perbaikan_permohonan",
        target_turn_range=(5, 5),
    )

    result = asyncio.run(orch.run_full_simulation("Draft pengujian Pasal 1 UU terhadap Pasal 28D UUD 1945."))

    assert result["metadata"]["hearing_mode"] == "perbaikan_permohonan"
    assert result["metadata"]["turn_count"] == 5
    assert {entry["round"] for entry in result["transcript"]} == {"Perbaikan Permohonan"}
    speakers = {entry["speaker"] for entry in result["transcript"]}
    assert "Ahli Pemohon" not in speakers
    assert "Ahli Pemerintah" not in speakers
    assert "Kuasa Hukum Presiden/DPR" not in speakers
    assert not result["individual_scores"]
    assert result["scores"] == {}


def test_pendahuluan_profile_respects_target_range():
    orch = FastHearingOrchestrator(
        2,
        hearing_mode="pemeriksaan_pendahuluan",
        target_turn_range=(7, 9),
    )

    result = asyncio.run(orch.run_full_simulation("Draft singkat tentang kerugian konstitusional Pemohon."))

    turn_count = result["metadata"]["turn_count"]
    assert 7 <= turn_count <= 9
    assert result["metadata"]["target_turn_range"] == [7, 9]
    assert {entry["round"] for entry in result["transcript"]} == {"Pemeriksaan Pendahuluan"}
    assert result["metadata"]["stop_reason"]


def test_full_training_simulation_uses_legacy_round_sequence():
    calls = []

    class LegacyFlowOrchestrator(FastHearingOrchestrator):
        async def run_round_1_pendahuluan(self, draft_input: str):
            calls.append("round1")

        async def run_round_2_perbaikan(self):
            calls.append("round2")

        async def run_round_2b_ahli(self):
            calls.append("round2b")

        async def run_round_3_pokok_perkara(self):
            calls.append("round3")

        async def run_round_4_kesimpulan(self):
            calls.append("round4")
            return {"simulation_id": self.simulation_id, "transcript": [], "scores": {}}

        async def run_round_5_feedback(self):
            calls.append("feedback")
            return {}

    orch = LegacyFlowOrchestrator(3, hearing_mode="full_training_simulation")
    asyncio.run(orch.run_full_simulation("Draft"))

    assert calls == ["round1", "round2", "round2b", "round3", "round4", "feedback"]
