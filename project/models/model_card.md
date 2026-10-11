# DangerMLP model card

Status: **trained research checkpoint / shadow mode only**. The weights are kept locally in `models/danger_mlp_uca_v1.pt` and ignored by Git.

`DangerMLP` scores a LaBSE text embedding into low, medium, or high operational priority. It does not identify people, prove an incident, or automate a security response.

## Training run 2026-10-05

- Source: official UCA annotation repository, commit `e478cb5b2277c6b7cf6a1dc4691021592003e216`.
- Split: official train (15,677 sentences), validation (3,534), test (4,331), disjoint by video.
- Encoder: frozen `sentence-transformers/LaBSE`, 768 dimensions.
- Head: project-owned `DangerMLP`, 768 → 256 → 64 → 3; weighted cross-entropy, AdamW, seed 42, 8 epochs.
- Runtime: local Apple Silicon with PyTorch 2.9.1; this run used MPS.
- Selection: best validation macro F1 at epoch 6, 0.6766.
- Untouched test: macro F1 0.6904; high precision 0.6096, high recall 0.6126.
- Test confusion matrix, rows/columns low, medium, high: `[[2212,331,122],[147,621,165],[68,216,449]]`.
- Checkpoint SHA-256: `f1764d3332a81effa1b3f328659a76d278f208ffe4433a7e2211f751aaab3900`.

## Limits

The risk label was inferred from the source video's category and assigned to every sentence in that video. This is weak supervision: an ordinary action inside a crime video may carry an incorrect high label. UCA is English while live descriptions are expected in Russian. The test performance does not establish performance on the four deployed cameras. Calibration, Russian event descriptions, camera-specific evaluation, and operator review are required before enabling alerts.
