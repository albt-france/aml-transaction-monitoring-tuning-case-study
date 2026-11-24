# Proposal: follow-up engagement "TM optimisation, phase 2"

**Client:** Bank N (fictional). **Format:** one data analyst plus part-time senior oversight, remote. **Duration:** 8 weeks.

## Objective
Implement and prove the first wave of the roadmap, so that the normal-week alert volume stays under analyst capacity
without losing detection, with evidence the second line can sign off.

## Scope and deliverables
| Week | Work | Deliverable |
|---|---|---|
| 1-2 | R02/R04/R10 code fixes in a test environment; ACH feed incident follow-up; C02 load gate | Fix log, before/after alert counts |
| 3-4 | Threshold changes (R01, R03, R06, R09, R11) with ATL/BTL evidence on 3 months of production data | Tuning pack for the second line |
| 5-6 | R13 network scenario in shadow mode; alert quality review with the analysts | Shadow-run report, go/no-go |
| 7-8 | Challenger score back-test on closed cases; model card; Power BI monitoring pages in production | Model validation pack, live dashboard |

## Effort
About 40 analyst-days plus 4 days of senior review. Client time: about 6 days (TM owner, data engineer, 2 analysts for the review sessions).

## Expected outcome (based on this assessment)
Normal-week alerts from 2,875 to about 1,543; precision from
0.6% to about 1.5%; network typologies covered; a ranked queue.

## Risks and mitigations
| Risk | Mitigation |
|---|---|
| Production data behaves differently from the assessment data | Re-run every ATL/BTL test on production history before any change |
| Raising thresholds loses unique detections | Pair each raise with the score; monitor recall on confirmed cases monthly |
| Feed fixes depend on another team | Load gate on C02 first, so the defect is visible even before the fix |
| Model risk | Shadow mode, champion/challenger, model card, second-line review |

*Indicative proposal written as part of a case study; no commercial terms.*

---
*Independent case study based on public and synthetic data · not affiliated with any bank or consultancy. Labels: PUBLIC DATA (synthetic AML benchmark), SIMULATED (Bank N layer), ILLUSTRATIVE (country tiers).*
