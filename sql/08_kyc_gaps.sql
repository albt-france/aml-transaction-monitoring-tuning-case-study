-- KYC gaps in the SIMULATED Bank N customer file, and what they do to detection.

-- name: kyc_gaps
WITH c AS (SELECT * FROM customers),
     dup AS (SELECT entity_ref FROM customers GROUP BY 1 HAVING count(*) > 1)
SELECT 'Customers without expected activity' AS gap,
       count(*) FILTER (WHERE expected_monthly_volume IS NULL) AS customers,
       count(*) FILTER (WHERE expected_monthly_volume IS NULL) / count(*) AS share, 'all customers' AS base,
       'R12 cannot evaluate these customers' AS detection_impact FROM c
UNION ALL
SELECT 'High-risk customers with review older than 12 months',
       count(*) FILTER (WHERE risk_rating = 'high' AND last_review_date < DATE '2021-09-16'),
       count(*) FILTER (WHERE risk_rating = 'high' AND last_review_date < DATE '2021-09-16')
           / count(*) FILTER (WHERE risk_rating = 'high'), 'high-risk customers',
       'Risk rating and expected activity may be stale for the riskiest files' FROM c
UNION ALL
SELECT 'Customer records sharing one entity',
       count(*) FILTER (WHERE entity_ref IN (SELECT entity_ref FROM dup)),
       count(*) FILTER (WHERE entity_ref IN (SELECT entity_ref FROM dup)) / count(*),
       'all customers', 'Activity split across two records; profiles and limits are computed per record' FROM c
UNION ALL
SELECT 'KYC file flagged incomplete', count(*) FILTER (WHERE NOT kyc_complete_flag),
       count(*) FILTER (WHERE NOT kyc_complete_flag) / count(*), 'all customers', 'Monitoring runs on partial profiles' FROM c;

-- name: kyc_gap_impact
-- Laundering customers (IBM labels) whose expected activity is missing are invisible to R12 by construction.
SELECT count(*) FILTER (WHERE laundering = 1) AS laundering_customers,
       count(*) FILTER (WHERE laundering = 1 AND expected_monthly_volume IS NULL) AS laundering_customers_without_profile,
       count(*) FILTER (WHERE laundering = 1 AND expected_monthly_volume IS NULL)
           / count(*) FILTER (WHERE laundering = 1) AS share_blind_to_r12
FROM id_customers;

-- name: kyc_by_segment
SELECT segment, risk_rating, count(*) AS customers,
       avg(CASE WHEN expected_monthly_volume IS NULL THEN 1 ELSE 0 END) AS share_without_profile,
       avg(CASE WHEN kyc_complete_flag THEN 0 ELSE 1 END) AS share_incomplete
FROM customers GROUP BY 1, 2 ORDER BY 1, 2;
