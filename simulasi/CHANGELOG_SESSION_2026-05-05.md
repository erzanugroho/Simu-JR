# Changelog Session — 2026-05-05

## 1. Layar Putih (White Screen Crash)

### Root Cause
- **Race condition di `server.py`** — `active_orchestrators.pop(sid)` di `finally` block berjalan SEBELUM listener SSE sempat membaca `orch.last_result`. Akibatnya, event `scores`, `individual_scores`, `feedback` tidak pernah dikirim ke frontend.
- **Penyebab sekunder** — `scores.feedback` berupa objek dirender langsung sebagai React children → crash tanpa error boundary → layar putih.

### Fix
| File | Perubahan |
|------|-----------|
| `server.py:574-589` | DONE handler fallback ke `simulation_results[sid]` jika orchestrator sudah di-pop |
| `server.py:1390` | `simulation_results[sid]` diisi sebelum `finally` block |
| `SimulationContext.tsx:89-90` | `scores` event: spread `...data` bukan nest under `total` |
| `SimulationPage.tsx` | Defensive checks pada semua properti `scores` (`typeof`, `Array.isArray`, optional chaining) |
| `ErrorBoundary.tsx` | Komponen baru — tangkap React crash, tampil error UI alih-alih layar kosong |
| `App.tsx` | Wrap app dengan `<ErrorBoundary>` |

---

## 2. Tidak Ada Amar Putusan, Voting, & Skoring

### Root Cause
`SimulationContext.tsx:90` — handler `scores` event menaruh seluruh objek server `{total, breakdown, amar, voting_detail, catatan_hakim}` di bawah property `total`:
```ts
// SALAH: scores.total = {total: 65, amar: "ditolak", ...} ← objek, bukan angka
setScores((prev) => ({ ...prev, total: data }));
```

### Fix
| File | Perubahan |
|------|-----------|
| `types.ts` | `Scores` diperluas: `amar`, `voting_detail`, `catatan_hakim`, `individual`, `feedback`, `dissenting_opinions`. Tambah `IndividualScore`, `DissentingOpinion` |
| `SimulationContext.tsx:90` | Spread `...data` langsung ke scores object |
| `SimulationContext.tsx:95` | Tambah handler `dissenting_opinions` event |
| `SimulationContext.tsx:168-179` | `syncSimulation`: mapping lengkap field scores + fallback extract dari transcript events |
| `SimulationPage.tsx` | Tambah panel: **Amar Putusan banner**, **Rekapitulasi Voting**, **Breakdown Skor**, **Catatan Hakim**, **Dissenting Opinion**, **Feedback Hakim**, **Detail Skor Per Hakim** |

---

## 3. Avatar Hakim Blank/Placeholder

### Root Cause
Sidebar kanan hanya menampilkan angka skor di lingkaran abu-abu, tanpa gambar avatar.

### Fix
| File | Perubahan |
|------|-----------|
| `SimulationPage.tsx:30-40` | Import 9 file PNG dari `src/avatarHakim/` → array `JUDGE_AVATARS` |
| `SimulationPage.tsx:689-702` | Ganti lingkaran kosong dengan `<img>` avatar + badge skor di pojok |

---

## 4. Provider mimo Tidak Dipakai (Tetap ke Localhost)

### Root Cause
- **Frontend** — `SimulationPage.tsx:145` selalu mengirim `base_url: "http://localhost:1234/v1"` meski provider = `mimo`.
- **Backend** — `agents.py:537` `base_url = self.llm_config.get("base_url") or default_base_url` — URL lokal meng-override `MIMO_BASE_URL`.

### Fix
| File | Perubahan |
|------|-----------|
| `SimulationPage.tsx:141-146` | Hanya kirim `base_url` untuk provider `local` |
| `agents.py:530-543` | Cloud providers (`mimo`, `openrouter`) gunakan default URL mereka, abaikan `base_url` lokal |

---

## 5. RPH Scoring Kosong (Putusan 0/100)

### Root Cause
`utils.py:112-115` — `strip_cot(aggressive=True)` dipanggil di setiap `generate_response()` dan menghapus blok JSON yang mengandung key scoring (`legal_standing`, `amar`, dll). JSON dari mimo dihapus SEBELUM `_parse_json_score` membacanya.

### Fix
| File | Perubahan |
|------|-----------|
| `utils.py:111-118` | JSON block removal hanya jalan di mode display (`if not aggressive`), bukan di mode agent response processing |

---

## 6. `jumlah_hakim` & `judge_personas` Missing

### Root Cause
`orchestrator.py:__init__` tidak menyimpan `jumlah_hakim` dan `judge_personas` ke `self`, tapi `save_simulation` di `server.py` mengakses `self.jumlah_hakim` dan `self.judge_personas`.

### Fix
| File | Perubahan |
|------|-----------|
| `orchestrator.py:81-82` | Tambah `self.jumlah_hakim = jumlah_hakim` dan `self.judge_personas = judge_personas or []` |

---

## 7. API Key pasal.id Expired

### Fix
| File | Perubahan |
|------|-----------|
| `.env` | Update `PASAL_API_TOKEN` dengan token baru |
