# Problem-Focused Bug Report Taxonomy

This document defines the canonical bug report categories and explains how they are applied in the pipeline via deterministic heuristics.

## Canonical Categories

Defined in `config/categories.json` (id, name, description):

- functional_errors
- ui_ux_issues
- performance_issues
- connectivity_problems
- authentication_access
- data_integrity_issues
- crash_stability
- integration_failures
- configuration_settings
- compatibility_issues
- feature_requests
- unclear_insufficient_info

## Where Categories Are Used

- `run_pipeline.py` uses `pipeline/mapping_rules.py` to assign categories.
- `scripts/populate_empty_categories.py` uses the same rules to fill missing categories.
- `scripts/arrange_by_headers.py` was updated so any derived labels map to these IDs if needed for interim grouping.
- Documentation (`README.md`, `docs/*.md`) references this taxonomy only.

## Deterministic Mapping Heuristics

Implemented in `pipeline/mapping_rules.py`. Priority order:

1. Comment-driven classification (feature request, connectivity, auth, performance, crash, data integrity, UI/UX, functional, configuration, integration, compatibility)
2. OCR-driven classification (auth, connectivity, performance, configuration, integration, data integrity)
3. Filename hints (error → functional_errors, login → authentication_access, timeout/network → connectivity_problems)
4. Post-adjustment (e.g., explicit crash/network/auth signals upgrade model predictions)
5. Fallback: `unclear_insufficient_info`

All rules are deterministic and order-sensitive; the first matching rule wins.

## Unit Tests

Unit tests cover the main mapping rules in `tests/test_mapping_rules.py`.
Run them with:

```bash
python -m unittest tests/test_mapping_rules.py -v
```

The goal is ≥ 90% of rule cases pass (current suite: 18/18).

## Model Retraining / Dataset Changes

If you have a learned classifier, update your training labels to use the canonical IDs above. Suggested steps:

1. Export your current labeled dataset.
2. Create a label mapping from any old labels to the new taxonomy (e.g., `error_screens` → `functional_errors`, `login_screens` → `authentication_access`, `navigation_screens` → `ui_ux_issues`, `processing_error`/`uncategorized` → `unclear_insufficient_info`).
3. Apply the mapping to produce a new training CSV/JSON with `category_id` matching `config/categories.json`.
4. Retrain your model. During inference, feed its prediction into `mapping_rules.post_adjustment()` if you want deterministic overrides.

Note: The pipeline remains fully functional without a trained model; the deterministic rules alone will assign categories.

## Assumptions & Conventions

- Input records have fields similar to Firebase export: `attachments`, `comment`, `createdAt`, `email`, `name`, `userId`.
- OCR text is best-effort extracted from attachments (images), but rules do not require OCR.
- All outputs must contain a non-empty `category` from the canonical set; if no signals, use `unclear_insufficient_info`.
