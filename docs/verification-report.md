# Verification report

Verified on 2026-09-12 against the final local build.

## Automated checks

```bash
python3 evaluation/run_evaluation.py
python3 -m unittest discover -s tests -v
node --check frontend/app.js
python3 -m compileall -q backend evaluation tests
```

- 11/11 unit and end-to-end service tests passed.
- All JSON data artifacts parsed successfully.
- 30/30 fixed synthetic scenarios completed.
- Grouping: 100% assigned, zero constraint violations, 100% independent rule-rubric agreement, 100% prerequisite-gap handling.
- Scheduling: 100% continuous work, zero teacher conflicts, 100% high-priority teacher access, 100% time utilization.
- Activities: 100% schema, competency, level, material, and source checks; 0% unsafe/invalid.
- Workflow: 100% validated plan acceptance and 300 quick checks created in the benchmark.

## Browser acceptance test

The complete one-device workflow was performed through the final teacher UI:

1. Reset the fixed 35-learner demo.
2. Confirmed Rajkumar’s returning status without treating absence as failure.
3. Saved attendance and generated four groups.
4. Confirmed Rajkumar was in N4 prerequisite recovery and that the group was teacher-first.
5. Generated three complete 15-minute rotations with exactly one teacher station per slot.
6. Opened a grounded activity, saved a teacher title edit, and approved the plan.
7. Submitted one observation and one exit check for Rajkumar.
8. Confirmed N4 changed from 0.45/Developing to 0.80/Mastered.
9. Confirmed automatic movement from prerequisite recovery to N6 concept launch.
10. Confirmed the evaluation view and checked browser warnings/errors: none.

Elapsed time was 1:05, below the three-minute target. The activity close control and restart-state behavior were retested after the final fixes.

## Claims deliberately left open

- Manual teacher planning-time reduction needs a measured teacher baseline.
- Learning gains need a classroom study.
- A public deployment URL, repository publication, and demo video are release tasks outside the local implementation.
- Stretch diagnostics, voice capture, and coordinator UI are not part of the MVP.

