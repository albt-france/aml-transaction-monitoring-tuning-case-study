# Power BI measures

Model: `powerbi/AmlTmAssessment.SemanticModel` (TMDL). Each DAX measure, in plain words.

| Measure | DAX | What it means |
|---|---|---|
| Alert Volume | `COUNTROWS ( Alerts )` | Number of alerts in the current filter (scenario, week, rule, segment). |
| True Positives | `SUM ( Alerts[is_tp] )` | Alerts raised on an account that sent or received a laundering-labelled transfer in the rule's lookback window. |
| Precision | `DIVIDE ( [True Positives], [Alert Volume] )` | Share of alerts that are true positives. |
| Recall | `DIVIDE ( SUM ( 'Rule Performance'[tp_accounts] ), MAX ( System[laundering_accounts] ) )` | Laundering accounts caught by the rule(s) divided by all laundering accounts in Bank N's book. |
| Alerts per Analyst Hour | `DIVIDE ( [Alert Volume], SUM ( Capacity[hours_available] ) )` | Alerts divided by the analyst hours available in the period. |
| Capacity Load | `DIVIDE ( [Alert Volume], SUM ( Capacity[alert_capacity] ) )` | Alerts divided by what 12 analysts can review (1.0 = exactly at capacity). |
| Alert Capacity | `SUM ( Capacity[alert_capacity] )` | Alerts the team can review in the period (hours x 60 / 12 minutes). |
| Coverage % | `AVERAGE ( 'Typology Coverage'[rules_now] )` | Average share of visible laundering attempts detected by the current rules, across typologies. |
| Coverage after R13 % | `AVERAGE ( 'Typology Coverage'[tuned_rules_plus_r13] )` | Same, with the tuned rules plus the new network scenario R13. |
| Detection Share | `AVERAGE ( 'Coverage Matrix'[share_detected] )` | Share of visible attempts of a typology detected by a rule (cell of the coverage matrix). |
| Control Fail Rate | `DIVIDE ( COUNTROWS ( FILTER ( Controls, Controls[status] = "FAIL" ) ), COUNTROWS ( Controls ) )` | Share of automated controls in FAIL status. |
| Controls Failing | `COUNTROWS ( FILTER ( Controls, Controls[status] = "FAIL" ) )` | Number of automated controls in FAIL status. |
| Max Null Rate | `MAX ( 'Feed Quality'[null_rate] )` | Highest share of rows without a beneficiary bank, by feed and day. |
| Challenger Precision | `MAX ( 'Model Simpson'[precision] )` | Precision of the challenger's capacity-limited queue for a segment / risk-tier cell. |

Data: `powerbi/data/*.csv`, exported by `src/build_powerbi.py`. Set the `DataFolder` parameter to the full path of
`powerbi/data/` in your clone, then refresh. No `.pbix` is stored in the repository.
