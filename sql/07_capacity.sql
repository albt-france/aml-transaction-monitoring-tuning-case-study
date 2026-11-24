-- Alert volume against analyst capacity (SIMULATED: 12 analysts, 30 productive hours a week, median 12 minutes).

CREATE OR REPLACE TABLE alert_hours AS
SELECT CAST(floor(datediff('day', (SELECT d0 FROM period), a.day) / 7) + 1 AS INTEGER) AS wk,
       sum(d.handling_minutes) / 60 AS hours_needed_implemented
FROM alerts a JOIN dispositions d USING (alert_id) GROUP BY 1;

-- name: capacity_weekly
WITH imp AS (SELECT wk, count(*) AS alerts_implemented FROM alerts_implemented GROUP BY 1),
     tun AS (SELECT wk, count(*) AS alerts_tuned FROM alerts_tuned GROUP BY 1)
SELECT c.wk, c.days_in_week, c.analysts, c.hours_available, c.alert_capacity,
       imp.alerts_implemented, tun.alerts_tuned,
       imp.alerts_implemented / c.alert_capacity AS load_implemented,
       tun.alerts_tuned / c.alert_capacity AS load_tuned,
       h.hours_needed_implemented
FROM capacity c LEFT JOIN imp USING (wk) LEFT JOIN tun USING (wk) LEFT JOIN alert_hours h USING (wk)
ORDER BY c.wk;

-- name: capacity_daily
SELECT d.day,
       (SELECT count(*) FROM alerts_implemented a WHERE a.day = d.day) AS alerts_implemented,
       (SELECT count(*) FROM alerts_tuned a WHERE a.day = d.day) AS alerts_tuned,
       (SELECT max(alert_capacity / days_in_week) FROM capacity) AS daily_capacity
FROM (SELECT DISTINCT day FROM alerts_implemented) d ORDER BY d.day;

-- name: disposition_summary
SELECT coalesce(a.rule_id, 'All rules') AS rule_id, count(*) AS alerts,
       count(*) FILTER (WHERE d.decision = 'sar_filed') AS sar_filed,
       count(*) FILTER (WHERE d.decision = 'escalated') AS escalated,
       count(*) FILTER (WHERE d.decision = 'closed_no_issue') AS closed_no_issue,
       count(*) FILTER (WHERE d.decision = 'sar_filed') / count(*) AS sar_conversion,
       median(d.handling_minutes) AS median_minutes,
       sum(d.handling_minutes) / 60 AS analyst_hours
FROM alerts a JOIN dispositions d USING (alert_id)
GROUP BY ROLLUP (a.rule_id) ORDER BY a.rule_id NULLS LAST;
