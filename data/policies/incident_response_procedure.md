# Incident Response Procedure

**Document Owner:** Site Reliability Engineering
**Policy Code:** IR
**Version:** 3.0
**Effective Date:** 15 January 2026

This procedure defines how production incidents are classified, escalated and reviewed. Security incidents follow the same process with the Information Security Team as incident commander.

# 1. Severity Levels

## IR-SEV1 Critical

A SEV1 incident is a complete outage of a customer-facing service or a confirmed data breach. The on-call engineer must acknowledge the page within **15 minutes**, and an incident commander must be appointed immediately. Customer status page updates are posted every **30 minutes**.

## IR-SEV2 Major

A SEV2 incident is a significant degradation affecting many customers, or a full outage of an internal critical system. Acknowledgement is required within **30 minutes**, with status updates every hour.

## IR-SEV3 Minor

A SEV3 incident has limited customer impact and a workaround exists. It must be acknowledged within **4 business hours** and can be handled during normal working hours.

# 2. Roles

## 2.1 Incident Commander

The incident commander coordinates the response, makes decisions about escalation and rollback, and is the single point of contact. The incident commander should not also be debugging the problem.

## 2.2 Communications Lead

For SEV1 and SEV2 incidents a communications lead is appointed to update the status page and inform customer support and leadership.

# 3. On-Call

## 3.1 On-Call Rotation

Engineers on the on-call rotation serve one-week shifts. On-call engineers receive a stipend for each week on call and must be able to reach a laptop within **15 minutes** of being paged.

# 4. After the Incident

## 4.1 Postmortem

A blameless postmortem is required for every SEV1 and SEV2 incident. The postmortem document must be published within **5 business days** of resolution and must include a timeline, root cause and action items with owners.

## 4.2 Action Items

Postmortem action items rated high priority must be completed within **30 days**.
