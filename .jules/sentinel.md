## 2024-05-23 - Hardcoded Admin Vulnerability
**Vulnerability:** A hardcoded admin ID (`84131737`) was present in the default configuration, granting admin access if `ADMIN_LIST` env var was missing. Additionally, specific username checks (`itolstov`) bypassed the admin list configuration.
**Learning:** Default values in configuration classes can silently introduce backdoors if not carefully managed. Hardcoded username checks are a dangerous practice that can be easily overlooked.
**Prevention:** Use empty defaults for sensitive lists. Avoid hardcoding user IDs or usernames in business logic; rely solely on configuration-driven access control.
