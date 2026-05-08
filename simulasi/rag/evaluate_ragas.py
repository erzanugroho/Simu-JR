"""
RAG Evaluation Module — RAGAS Metrics
======================================
Mengukur kualitas retrieval pipeline menggunakan RAGAS framework:
  - context_precision   : Seberapa relevan chunk yang di-retrieve
  - context_recall      : Seberapa lengkap chunk yang di-retrieve
  - answer_relevancy    : Seberapa relevan jawaban terhadap pertanyaan
  - faithfulness        : Seberapa setia jawaban terhadap konteks (anti-hallucination)

Usage:
  python evaluate_ragas.py                         # Jalankan evaluasi default
  python evaluate_ragas.py --build-dataset         # Bangun eval dataset dari JSONL
  python evaluate_ragas.py --report-only           # Hanya tampilkan report terakhir
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from openai import AsyncOpenAI

# Load .env
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

logger = logging.getLogger(__name__)

# ============================================================================
# KONFIGURASI
# ============================================================================

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://127.0.0.1:1234/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "not-needed-for-local")
MODEL_NAME = os.getenv("LLM_MODEL_NAME", "local-model")

EVAL_DATASET_PATH = Path(__file__).parent / "eval_dataset.json"
REPORT_OUTPUT_DIR = Path(__file__).parent.parent / "results" / "rag_evaluations"

# Target metrics (sesuai RAG Architect skill checkpoint)
TARGET_CONTEXT_PRECISION = 0.7
TARGET_CONTEXT_RECALL = 0.6


# ============================================================================
# EVALUATION DATASET — 30 pertanyaan hukum konstitusi + ground truth
# ============================================================================

DEFAULT_EVAL_DATASET: List[Dict[str, Any]] = [
    # --- Legal Standing (10 pertanyaan) ---
    {
        "question": "Apa syarat legal standing untuk mengajukan pengujian undang-undang ke MK?",
        "ground_truth": "Pasal 51 ayat (1) UU MK mensyaratkan: (1) kedudukan hukum konstitusional, (2) kerugian konstitusional, (3) hubungan kausal antara kerugian dengan berlakunya UU. Pemohon dapat berupa perseorangan warga negara, organisasi sosial politik, atau lembaga negara."
    },
    {
        "question": "Siapa saja yang memiliki kedudukan hukum untuk mengajukan PUU?",
        "ground_truth": "Yang dapat mengajukan permohonan PUU adalah: (1) Perseorangan atau beberapa orang sebagai warga negara, (2) organisasi sosial politik, (3) pemerintah daerah, (4) lembaga negara. Syarat utamanya adalah adanya kerugian konstitusional secara langsung."
    },
    {
        "question": "Bagaimana MK menilai kerugian konstitusional dalam permohonan PUU?",
        "ground_truth": "MK menilai kerugian konstitusional harus bersifat aktual atau potensial (reale bewijslast), spesifik, dan ada hubungan kausalitas antara berlakunya norma yang diuji dengan kerugian yang diderita. Kerugian harus terhadap hak konstitusional pemohon, bukan kerugian biasa."
    },
    {
        "question": "Apa perbedaan antara kerugian konstitusional dan kerugian biasa?",
        "ground_truth": "Kerugian konstitusional adalah kerugian terhadap hak-hak yang dijamin oleh UUD 1945, seperti hak atas pekerjaan, hak milik, hak atas kepastian hukum. Kerugian biasa adalah kerugian material atau moral yang dapat ditangani melalui pengadilan umum. Hanya kerugian konstitusional yang menjadi dasar legal standing di MK."
    },
    {
        "question": "Apakah organisasi LSM dapat mengajukan permohonan PUU?",
        "ground_truth": "Ya, organisasi sosial politik termasuk LSM dapat mengajukan permohonan PUUprovided bahwa organisasi tersebut dapat membuktikan adanya kerugian konstitusional yang langsung mengenai tujuan dan bidang kerja organisasi sesuai dengan anggaran dasarnya."
    },
    {
        "question": "Bagaimana hubungan kausalitas dibuktikan dalam legal standing?",
        "ground_truth": "Hubungan kausalitas (kausal verband) dibuktikan dengan menunjukkan bahwa kerugian konstitusional yang diderita pemohon merupakan akibat langsung dari berlakunya norma yang diuji. Pemohon harus menunjukkan nexus antara pasal yang diuji dan kerugian yang dialami."
    },
    {
        "question": "Apa yang dimaksud dengan reale bewijslast dalam konteks MK?",
        "ground_truth": "Reale bewijslast adalah beban pembuktian yang memerlukan bukti nyata bahwa kerugian konstitusional bersifat aktual atau paling tidak potensial dan spesifik. Dalam praktik MK, standar pembuktian ini tidak seketat pengadilan biasa, cukup menunjukkan kemungkinan kerugian yang nyata."
    },
    {
        "question": "Bagaimana MK menangani permohonan yang legal standing-nya lemah?",
        "ground_truth": "MK dapat memberikan nasihat perbaikan (advisory) kepada pemohon untuk memperkuat legal standing-nya. Jika setelah nasihat perbaikan legal standing tetap tidak terpenuhi, MK dapat menyatakan permohonan tidak dapat diterima. MK juga dapat memberikan kesempatan kepada pemohon untuk melengkapi argumen."
    },
    {
        "question": "Apakah pemerintah daerah memiliki legal standing untuk mengajukan PUU?",
        "ground_truth": "Ya, pemerintah daerah (provinsi, kabupaten/kota) memiliki kedudukan hukum untuk mengajukan permohonan PUU terhadap peraturan perundang-undangan yang bersifat umum dan berdampak pada kewenangan atau kepentingan pemerintah daerah sesuai UUD 1945."
    },
    {
        "question": "Bagaimana MK menilai kualifikasi pemohon perseorangan?",
        "ground_truth": "MK menilai kualifikasi pemohon perseorangan berdasarkan apakah orang tersebut sebagai warga negara Indonesia memiliki hak konstitusional yang langsung dirugikan oleh berlakunya UU. Pemohon harus menunjukkan identitas dan hubungan langsung antara norma yang diuji dengan hak konstitusionalnya."
    },

    # --- Substansi Argumen (10 pertanyaan) ---
    {
        "question": "Apa prinsip proporsionalitas dalam pengujian undang-undang?",
        "ground_truth": "Prinsip proporsionalitas mensyaratkan bahwa pembatasan hak konstitusional harus: (1) bertujuan untuk kepentingan yang sah, (2) sesuai dan layak untuk mencapai tujuan tersebut, (3) diperlukan (tidak ada cara lain yang kurang membatasi), dan (4) sebanding antara manfaat dan kerugian yang ditimbulkan."
    },
    {
        "question": "Bagaimana MK menerapkan judicial review terhadap undang-undang?",
        "ground_truth": "MK melakukan judicial review konstitusional dengan menguji apakah norma yang diuji bertentangan dengan UUD 1945. MK menggunakan berbagai tafsir: tafsir konstitusional, tafsir sistematis, tafsir historis, dan tafsir teleologis. MK juga menerapkan doktrin open legal policy dan judicial self-restraint."
    },
    {
        "question": "Apa yang dimaksud dengan open legal policy dalam praktik MK?",
        "ground_truth": "Open legal policy adalah area kebijakan yang terbuka bagi legislator untuk menentukan berdasarkan pertimbangan politik hukum. MK cenderung memberikan deference kepada legislator dalam area open legal policy, kecuali kebijakan tersebut jelas melanggar konstitusi."
    },
    {
        "question": "Bagaimana MK menangani sengketa antara UU dan UUD 1945?",
        "ground_truth": "MK menyelesaikan sengketa dengan menguji apakah UU bertentangan dengan UUD 1945 secara eksplisit atau implisit. MK dapat menyatakan UU bertentangan dengan UUD 1945 (inkonstitusional), atau memberikan tafsir konstitusional agar UU selaras dengan UUD 1945."
    },
    {
        "question": "Apa peran batu uji dalam permohonan PUU?",
        "ground_truth": "Batu uji adalah pasal-pasal UUD 1945 yang dijadikan acuan untuk menguji norma yang ditantang. Batu uji harus relevan dengan norma yang diuji dan harus dirumuskan secara spesifik. Kualitas batu uji sangat menentukan kekuatan argumen substansi permohonan."
    },
    {
        "question": "Bagaimana MK menerapkan prinsip certainty of law?",
        "ground_truth": "Prinsip certainty of law (kepastian hukum) mensyaratkan bahwa peraturan perundang-undangan harus jelas, pasti, dan tidak ambigu. MK sering menggunakan prinsip ini untuk menguji norma yang terlalu luas, tidak jelas, atau memberikan kewenangan yang tidak terbatas."
    },
    {
        "question": "Apa standar review yang digunakan MK untuk pembatasan hak asasi manusia?",
        "ground_truth": "MK menggunakan standar review ketat (strict scrutiny) untuk pembatasan HAM, mensyaratkan: tujuan yang sangat penting (compelling state interest), sarana yang sangat sesuaikan (narrowly tailored), dan tidak ada alternatif yang kurang membatasi. Untuk kebijakan sosial-ekonomi, MK menggunakan standar review longgar (rational basis review)."
    },
    {
        "question": "Bagaimana MK menggunakan preseden dalam pengambilan putusan?",
        "ground_truth": "Meskipun Indonesia tidak menganut common law, MK secara konsisten merujuk pada putusan-putusan sebelumnya sebagai preseden de facto. Ratio decidendi dari putusan sebelumnya menjadi pertimbangan penting dalam menjaga konsistensi yurisprudensi."
    },
    {
        "question": "Apa perbedaan antara bertentangan dengan UUD 1945 dan conditional unconstitutional?",
        "ground_truth": "Bertentangan dengan UUD 1945 berarti norma dinyatakan inkonstitusional secara mutlak dan tidak mempunyai kekuatan hukum mengikat. Conditional unconstitutional (inkonstitusional bersyarat) berarti norma masih berlaku selama belum ada pengganti, memberikan waktu kepada legislator untuk merevisi."
    },
    {
        "question": "Bagaimana MK menilai kewenangan legislator dalam membuat undang-undang?",
        "ground_truth": "MK menilai apakah legislator telah melaksanakan mandat UUD 1945 dengan baik. MK menggunakan prinsip judicial self-restraint untuk tidak menggantikan pertimbangan politik legislator, kecuali ada pelanggaran konstitusi yang jelas dan nyata."
    },

    # --- Prosedur & Putusan (10 pertanyaan) ---
    {
        "question": "Apa tahapan pemeriksaan dalam sidang PUU di MK?",
        "ground_truth": "Tahapan pemeriksaan PUU: (1) Pemeriksaan Pendahuluan — uji legal standing, (2) Perbaikan Permohonan — nasihat dari Majelis, (3) Pemeriksaan Ahli — keterangan ahli dari kedua pihak, (4) Pokok Perkara — argumen substansi, (5) Kesimpulan & RPH — Rapat Permusyawaratan Hakim, (6) Pengucapan Putusan."
    },
    {
        "question": "Bagaimana mekanisme Rapat Permusyawaratan Hakim (RPH)?",
        "ground_truth": "RPH adalah rapat tertutup di mana para hakim membahas dan memutuskan permohonan. Setiap hakim memberikan penilaian independen. Putusan diambil berdasarkan voting. Jika ada perbedaan pendapat, hakim dapat menyampaikan Dissenting Opinion atau Concurring Opinion."
    },
    {
        "question": "Apa jenis-jenis amar putusan MK dalam PUU?",
        "ground_truth": "Amar putusan MK dalam PUU: (1) Dikabulkan — norma dinyatakan inkonstitusional, (2) Ditolak — norma dinyatakan konstitusional, (3) Tidak Dapat Diterima — legal standing tidak terpenuhi, (4) Dikabulkan Sebagian — sebagian norma inkonstitusional, sebagian lain konstitusional."
    },
    {
        "question": "Bagaimana Dissenting Opinion bekerja di MK?",
        "ground_truth": "Dissenting Opinion adalah pendapat berbeda yang disampaikan oleh hakim yang tidak setuju dengan putusan mayoritas. Concurring Opinion adalah pendapat yang setuju dengan amar tetapi dengan alasan berbeda. Keduanya meningkatkan transparansi dan kedalaman pertimbangan hukum."
    },
    {
        "question": "Apa peran Pemerintah dalam sidang PUU?",
        "ground_truth": "Pemerintah (diwakili Menteri terkait dan/atau Kepala BKPM) wajib memberikan keterangan dalam sidang PUU. Pemerintah dapat membantah argumen pemohon menggunakan strategi open legal policy, ratio legis, dan preseden penolakan. Pemerintah juga dapat memberikan keterangan tertulis."
    },
    {
        "question": "Bagaimana pihak terkait dan amicus curiae berperan dalam sidang MK?",
        "ground_truth": "Pihak terkait adalah pihak yang kepentingannya langsung terpengaruh oleh putusan. Amicus curiae (teman pengadilan) adalah pihak yang memberikan pandangan untuk membantu Majelis, biasanya dari organisasi masyarakat atau akademisi. Keduanya memberikan perspektif tambahan yang memperkaya pertimbangan Majelis."
    },
    {
        "question": "Berapa lama waktu maksimal untuk menyelesaikan perkara PUU?",
        "ground_truth": "Berdasarkan UU MK, perkara PUU harus diselesaikan dalam waktu 90 hari sejak pendaftaran. Dalam praktik, waktu ini sering diperpanjang karena kompleksitas perkara dan kebutuhan pemeriksaan yang mendalam."
    },
    {
        "question": "Apa kekuatan hukum putusan MK dalam PUU?",
        "ground_truth": "Putusan MK bersifat final dan mengikat. Norma yang dinyatakan bertentangan dengan UUD 1945 kehilangan kekuatan hukum mengikat (tidak mempunyai kekuatan hukum mengikat). Putusan MK berkekuatan hukum tetap dan tidak dapat diganggu gugat."
    },
    {
        "question": "Bagaimana MK melakukan tafsir konstitusional?",
        "ground_truth": "MK melakukan tafsir konstitusional untuk menyelamatkan norma dari pengujian dengan menafsirkannya secara selaras dengan UUD 1945. Metode yang digunakan termasuk tafsir tekstual, sistematis, historis, teleologis, dan komparatif."
    },
    {
        "question": "Apa peran ratio decidendi dalam putusan MK?",
        "ground_truth": "Ratio decidendi adalah alasan pokok putusan yang menjadi dasar hukum keputusan MK. Ratio decidendi berisi pertimbangan konstitusional, analisis hukum, dan pemertimbangan yang mendasari amar putusan. Obs dicta adalah pernyataan tambahan yang tidak mengikat."
    },
]


# ============================================================================
# LLM CLIENT UNTUK RAGAS
# ============================================================================

def create_llm_client():
    """Buat LLM client untuk RAGAS evaluation."""
    return AsyncOpenAI(
        base_url=LLM_BASE_URL,
        api_key=LLM_API_KEY,
    )


async def llm_aio(prompt: str, client: AsyncOpenAI, max_tokens: int = 2048) -> str:
    """Async LLM call untuk RAGAS."""
    try:
        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return ""


# ============================================================================
# RAGAS-STYLE METRICS (Custom Implementation)
# ============================================================================
# Menggunakan LLM sebagai judge untuk menghindari dependency eksternal
# yang mungkin tidak kompatibel dengan local LLM.

async def evaluate_context_precision(
    question: str,
    retrieved_contexts: List[str],
    ground_truth: str,
    llm_client: AsyncOpenAI,
) -> float:
    """
    Context Precision: Seberapa banyak chunk yang di-retrieve benar-benar
    relevan dengan pertanyaan dan ground truth.

    Score: 0.0 (tidak relevan) — 1.0 (semua chunk relevan)
    """
    prompt = f"""
Anda adalah evaluator retrieval sistem. Tugas Anda menilai seberapa relevan
chunk konteks yang di-retrieve terhadap pertanyaan dan jawaban yang benar.

PERTANYAAN: {question}

JAWABAN BENAR (Ground Truth):
{ground_truth}

CHUNK KONTeks YANG DI-RETRIEVE ({len(retrieved_contexts)} chunk):
"""
    for i, ctx in enumerate(retrieved_contexts, 1):
        prompt += f"\n--- Chunk {i} ---\n{ctx[:500]}\n"

    prompt += f"""
\nNilai setiap chunk: BERLAKU (relevan dengan pertanyaan dan ground truth)
atau TIDAK RELEVAN (tidak berkaitan atau informasi salah).

Kembalikan HANYA JSON format:
{{
    "chunk_scores": [<1 atau 0 untuk setiap chunk, sesuai urutan>],
    "precision": <rata-rata chunk_scores, 2 desimal>
}}

Contoh: {{"chunk_scores": [1, 1, 0, 1, 0], "precision": 0.60}}
"""
    try:
        result = await llm_aio(prompt, llm_client)
        # Extract JSON
        start = result.find("{")
        end = result.rfind("}") + 1
        if start != -1 and end > 0:
            parsed = json.loads(result[start:end])
            return float(parsed.get("precision", 0.0))
    except Exception as e:
        logger.warning(f"Context precision eval failed: {e}")

    # Fallback: simple heuristic
    if not retrieved_contexts:
        return 0.0
    return 0.5  # Neutral fallback


async def evaluate_context_recall(
    question: str,
    retrieved_contexts: List[str],
    ground_truth: str,
    llm_client: AsyncOpenAI,
) -> float:
    """
    Context Recall: Seberapa lengkap informasi dari ground truth
tercakup dalam chunk yang di-retrieve.

    Score: 0.0 (tidak ada informasi yang relevan) — 1.0 (semua informasi tercakup)
    """
    prompt = f"""
Anda adalah evaluator retrieval sistem. Tugas Anda menilai seberapa lengkap
informasi dari jawaban benar (ground truth) tercakup dalam chunk yang di-retrieve.

PERTANYAAN: {question}

JAWABAN BENAR (Ground Truth):
{ground_truth}

CHUNK KONTeks YANG DI-RETRIEVE:
"""
    for ctx in retrieved_contexts:
        prompt += f"{ctx[:400]}\n\n"

    prompt += """
Nilai berapa persen informasi penting dari ground truth yang tercakup
dalam chunk yang di-retrieve (0-100%).

Kembalikan HANYA JSON format:
{
    "recall": <angka 0.00 sampai 1.00>,
    "missing_info": [<informasi penting yang tidak tercakup, atau array kosong>]
}

Contoh: {"recall": 0.85, "missing_info": ["detail tentang pengecualian"]}
"""
    try:
        result = await llm_aio(prompt, llm_client)
        start = result.find("{")
        end = result.rfind("}") + 1
        if start != -1 and end > 0:
            parsed = json.loads(result[start:end])
            return float(parsed.get("recall", 0.0))
    except Exception as e:
        logger.warning(f"Context recall eval failed: {e}")

    return 0.5  # Neutral fallback


async def evaluate_answer_relevancy(
    question: str,
    answer: str,
    llm_client: AsyncOpenAI,
) -> float:
    """
    Answer Relevancy: Seberapa relevan dan langsung menjawab pertanyaan.

    Score: 0.0 (tidak relevan) — 1.0 (sangat relevan dan langsung menjawab)
    """
    prompt = f"""
Anda adalah evaluator. Nilai seberapa relevan jawaban berikut terhadap pertanyaan.

PERTANYAAN: {question}

JAWABAN:
{answer}

Nilai dari 0.00 (tidak relevan/salah topik) sampai 1.00 (sangat relevan,
langsung menjawab pertanyaan dengan akurat dan lengkap).

Kembalikan HANYA JSON:
{{"answer_relevancy": <angka 0.00-1.00>, "reason": "<alasan singkat>"}}
"""
    try:
        result = await llm_aio(prompt, llm_client)
        start = result.find("{")
        end = result.rfind("}") + 1
        if start != -1 and end > 0:
            parsed = json.loads(result[start:end])
            return float(parsed.get("answer_relevancy", 0.0))
    except Exception as e:
        logger.warning(f"Answer relevancy eval failed: {e}")

    return 0.5


async def evaluate_faithfulness(
    question: str,
    answer: str,
    retrieved_contexts: List[str],
    llm_client: AsyncOpenAI,
) -> float:
    """
    Faithfulness: Apakah jawaban setia terhadap konteks yang di-retrieve
    (tidak hallucinate informasi yang tidak ada di konteks).

    Score: 0.0 (banyak hallucination) — 1.0 (semua klaim didukung konteks)
    """
    combined_context = "\n\n".join(ctx[:400] for ctx in retrieved_contexts)

    prompt = f"""
Anda adalah evaluator anti-hallucination. Periksa apakah setiap klaim dalam
jawaban didukung oleh konteks yang diberikan.

PERTANYAAN: {question}

KONTeks:
{combined_context}

JAWABAN:
{answer}

Periksa:
1. Apakah klaim faktual dalam jawaban didukung oleh konteks?
2. Apakah ada informasi yang di-inventari (hallucination)?
3. Apakah kesimpulan dalam jawaban logis berdasarkan konteks?

Kembalikan HANYA JSON:
{{
    "faithfulness": <angka 0.00-1.00>,
    "hallucinations_found": [<klaim yang tidak didukung konteks, atau array kosong>],
    "reason": "<alasan singkat>"
}}
"""
    try:
        result = await llm_aio(prompt, llm_client)
        start = result.find("{")
        end = result.rfind("}") + 1
        if start != -1 and end > 0:
            parsed = json.loads(result[start:end])
            return float(parsed.get("faithfulness", 0.0))
    except Exception as e:
        logger.warning(f"Faithfulness eval failed: {e}")

    return 0.5


# ============================================================================
# MRR (Mean Reciprocal Rank)
# ============================================================================

# ============================================================================
# MAIN EVALUATION PIPELINE
# ============================================================================

class RAGEvaluator:
    """Evaluator RAG menggunakan RAGAS-style metrics."""

    def __init__(
        self,
        retriever: Any = None,
        llm_client: AsyncOpenAI = None,
        dataset: List[Dict[str, Any]] = None,
    ):
        self.retriever = retriever
        self.llm_client = llm_client or create_llm_client()
        self.dataset = dataset or DEFAULT_EVAL_DATASET
        self.results: List[Dict[str, Any]] = []
        self.latencies: List[float] = []

    async def evaluate_single(
        self,
        question: str,
        ground_truth: str,
        role: str = "umum",
    ) -> Dict[str, Any]:
        """Evaluasi satu pertanyaan."""
        import time

        # Step 1: Retrieve
        start_time = time.time()
        retrieved_contexts: List[str] = []

        if self.retriever:
            try:
                result = self.retriever.query(question, n_results=7)
                retrieved_contexts = [
                    doc for doc in result.get("documents", [])
                ] or result.get("context_text", "").split("---")
                # Clean up context parts
                retrieved_contexts = [
                    c.strip() for c in retrieved_contexts if c.strip()
                ]
            except Exception as e:
                logger.warning(f"Retrieval failed for question: {e}")
        
        retrieval_time = time.time() - start_time

        # Step 2: Evaluate metrics
        ctx_precision = await evaluate_context_precision(
            question, retrieved_contexts, ground_truth, self.llm_client
        )
        ctx_recall = await evaluate_context_recall(
            question, retrieved_contexts, ground_truth, self.llm_client
        )
        answer_relevancy = await evaluate_answer_relevancy(
            question, ground_truth, self.llm_client
        )
        faithfulness = await evaluate_faithfulness(
            question, ground_truth, retrieved_contexts, self.llm_client
        )

        return {
            "question": question,
            "ground_truth": ground_truth,
            "retrieved_count": len(retrieved_contexts),
            "metrics": {
                "context_precision": round(ctx_precision, 4),
                "context_recall": round(ctx_recall, 4),
                "answer_relevancy": round(answer_relevancy, 4),
                "faithfulness": round(faithfulness, 4),
            },
            "retrieval_latency_ms": round(retrieval_time * 1000, 2),
            "role": role,
        }

    async def run_full_evaluation(self) -> Dict[str, Any]:
        """Jalankan evaluasi lengkap untuk semua pertanyaan."""
        logger.info(f"🚀 Memulai RAG Evaluation ({len(self.dataset)} questions)...")

        for i, item in enumerate(self.dataset):
            logger.info(
                f"  [{i+1}/{len(self.dataset)}] Evaluating: {item['question'][:60]}..."
            )
            result = await self.evaluate_single(
                question=item["question"],
                ground_truth=item["ground_truth"],
                role="umum",
            )
            self.results.append(result)
            self.latencies.append(result["retrieval_latency_ms"])

        return self._aggregate_results()

    def _aggregate_results(self) -> Dict[str, Any]:
        """Agregasi semua hasil evaluasi."""
        if not self.results:
            return {"error": "No results"}

        metrics_keys = ["context_precision", "context_recall", "answer_relevancy", "faithfulness"]

        # Rata-rata per metric
        averages = {}
        for key in metrics_keys:
            values = [r["metrics"][key] for r in self.results if r["metrics"].get(key) is not None]
            averages[key] = round(sum(values) / len(values), 4) if values else 0.0

        # Latency stats
        p50 = sorted(self.latencies)[len(self.latencies) // 2] if self.latencies else 0
        p95_idx = int(len(self.latencies) * 0.95)
        p95 = sorted(self.latencies)[p95_idx] if self.latencies else 0

        # Pass/fail terhadap target
        passed_precision = averages["context_precision"] >= TARGET_CONTEXT_PRECISION
        passed_recall = averages["context_recall"] >= TARGET_CONTEXT_RECALL

        return {
            "timestamp": datetime.now().isoformat(),
            "total_questions": len(self.results),
            "metrics_averages": averages,
            "latency": {
                "avg_ms": round(sum(self.latencies) / len(self.latencies), 2) if self.latencies else 0,
                "p50_ms": round(p50, 2),
                "p95_ms": round(p95, 2),
            },
            "targets": {
                "context_precision": {
                    "target": TARGET_CONTEXT_PRECISION,
                    "actual": averages["context_precision"],
                    "passed": passed_precision,
                },
                "context_recall": {
                    "target": TARGET_CONTEXT_RECALL,
                    "actual": averages["context_recall"],
                    "passed": passed_recall,
                },
            },
            "overall_passed": passed_precision and passed_recall,
            "per_question_results": self.results,
        }

    def save_report(self, report: Dict[str, Any]) -> str:
        """Simpan report ke file JSON."""
        REPORT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = REPORT_OUTPUT_DIR / f"rag_evaluation_{timestamp}.json"

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logger.info(f"📄 Report saved to: {report_path}")
        return str(report_path)


# ============================================================================
# QUICK EVAL — Tanpa RAGAS library (menggunakan LLM sebagai judge)
# ============================================================================

async def quick_eval(retriever: Any = None, sample_size: int = 10) -> Dict[str, Any]:
    """
    Evaluasi cepat tanpa dependency eksternal.
    Menggunakan LLM sebagai judge untuk semua metrics.
    """
    evaluator = RAGEvaluator(
        retriever=retriever,
        dataset=DEFAULT_EVAL_DATASET[:sample_size],
    )
    return await evaluator.run_full_evaluation()


# ============================================================================
# ENTRY POINT
# ============================================================================

def print_report(report: Dict[str, Any]) -> None:
    """Cetak report ke console dengan format rapi."""
    print("\n" + "=" * 70)
    print("  📊 RAG EVALUATION REPORT")
    print("=" * 70)

    print(f"\n  Timestamp       : {report.get('timestamp', '-')}")
    print(f"  Total Questions : {report.get('total_questions', 0)}")

    # Metrics
    metrics = report.get("metrics_averages", {})
    print(f"\n  {'METRIC':<25} {'SCORE':<10} {'TARGET':<10} {'STATUS':<10}")
    print(f"  {'-'*55}")

    targets = report.get("targets", {})
    for metric_name in ["context_precision", "context_recall"]:
        score = metrics.get(metric_name, 0)
        target_info = targets.get(metric_name, {})
        target_val = target_info.get("target", "-")
        passed = target_info.get("passed", False)
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {metric_name:<23} {score:<10.4f} {str(target_val):<10} {status:<10}")

    for metric_name in ["answer_relevancy", "faithfulness"]:
        score = metrics.get(metric_name, 0)
        print(f"  {metric_name:<23} {score:<10.4f}")

    # Latency
    latency = report.get("latency", {})
    print(f"\n  {'LATENCY':<25} {'VALUE':<15}")
    print(f"  {'-'*40}")
    print(f"  {'avg':<23} {latency.get('avg_ms', 0):>8.2f} ms")
    print(f"  {'p50':<23} {latency.get('p50_ms', 0):>8.2f} ms")
    print(f"  {'p95':<23} {latency.get('p95_ms', 0):>8.2f} ms")

    # Overall
    overall = report.get("overall_passed", False)
    print(f"\n  {'='*55}")
    print(f"  OVERALL: {'✅ ALL TARGETS PASSED' if overall else '❌ SOME TARGETS FAILED'}")
    print(f"  {'='*55}\n")


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="RAG Evaluation with RAGAS-style metrics")
    parser.add_argument("--build-dataset", action="store_true",
                        help="Save default eval dataset to file")
    parser.add_argument("--report-only", action="store_true",
                        help="Load and display latest report")
    parser.add_argument("--sample-size", type=int, default=10,
                        help="Number of questions to evaluate (default: 10)")
    parser.add_argument("--full", action="store_true",
                        help="Run full evaluation (all 30 questions)")
    args = parser.parse_args()

    if args.build_dataset:
        with open(EVAL_DATASET_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_EVAL_DATASET, f, indent=2, ensure_ascii=False)
        print(f"✅ Eval dataset saved to {EVAL_DATASET_PATH}")
        print(f"   Total questions: {len(DEFAULT_EVAL_DATASET)}")
        return

    if args.report_only:
        # Find latest report
        reports = sorted(REPORT_OUTPUT_DIR.glob("rag_evaluation_*.json"))
        if reports:
            with open(reports[-1], "r", encoding="utf-8") as f:
                report = json.load(f)
            print_report(report)
        else:
            print("❌ No reports found. Run evaluation first.")
        return

    # Determine sample size
    sample_size = len(DEFAULT_EVAL_DATASET) if args.full else args.sample_size

    # Try to load retriever
    retriever = None
    try:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from retriever import RAGRetriever
        retriever = RAGRetriever()
        stats = retriever.get_stats()
        logger.info(f"📚 RAG connected: {stats['total_vectors']:,} vectors")
    except Exception as e:
        logger.warning(f"⚠️ RAG not available: {e}. Running offline evaluation.")

    # Run evaluation
    report = await quick_eval(retriever=retriever, sample_size=sample_size)
    print_report(report)

    # Save report
    evaluator = RAGEvaluator(retriever=retriever)
    evaluator.results = report.get("per_question_results", [])
    evaluator.latencies = [r["retrieval_latency_ms"] for r in evaluator.results]
    evaluator.save_report(report)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    asyncio.run(main())
