# Fix UI/UX Simulation Interface

The goal is to fix the remaining UI issues reported:
1. The loading spinner on the simulation tab stays running even after completion.
2. The transcript layout is side-by-side (columns) instead of a vertical chat bubble layout.
3. The "Simpan Hasil" (Save Result) button is missing.
4. The Verdict ("Hasil Putusan") panel layout is messy and needs refactoring.

## User Review Required

- **Chat Bubble Alignment**: Do you want the "Hakim" bubbles to be on the left and "Pemohon" bubbles on the right (like a standard chat app)?
- **Save Result Button Placement**: I plan to place the "Simpan Hasil" button either in the `header-right` area or alongside the "Mulai Simulasi" button. 

## Open Questions

- None at the moment. The plan covers all requests directly.

## Proposed Changes

### `static/style.css`
- **Transcript Layout**:
  - Update `.round-section` to use `flex-direction: column` instead of `row`.
  - Add chat bubble styling to `.entry-card`.
  - Introduce classes like `.bubble-left` (Hakim, Pemerintah, dll) and `.bubble-right` (Pemohon) using `align-self`.
- **Verdict Layout**:
  - Refactor `.verdict-card` and `#panelScores` to use CSS Grid or Flex with proper wrapping, padding, and gap spacing to prevent overlapping text.

### `static/index.html`
- **Simpan Hasil Button**:
  - Add `<button id="btnSimpanHasil" class="btn btn-primary" onclick="saveSimulationResult()">Simpan Hasil</button>` in the appropriate container (e.g., header actions or right panel).
- **Transcript Container**:
  - Adjust any inline styles on `round-section` generated dynamically or within HTML.

### `static/app.js`
- **Loading State Bug**:
  - Locate the SSE (`EventSource`) termination events (`done`, `error`, `final_result`).
  - Ensure the `activeSimSlot.isRunning` state is set to `false` and `isFinished = true`, followed by `renderSimulationSlotTabs()`.
- **Chat Bubble Logic**:
  - Update `appendEntryToRound()` to inject `.bubble-left` or `.bubble-right` classes based on `entry.speaker` role.

## Verification Plan

### Manual Verification
- Run a new simulation.
- Verify the transcript renders vertically as chat bubbles.
- Check if the spinner stops when the simulation reaches 100%.
- Ensure "Simpan Hasil" appears and works.
- Verify the verdict panel is clean and readable at the end of the simulation.
