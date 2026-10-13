# Security Notes

## Current Safety Model

This application employs several layers of security to protect data and ensure safe usage:

1. **Read-only DB sessions**: All database connections are configured as read-only, preventing any data modification operations (INSERT, UPDATE, DELETE, etc.) regardless of the SQL generated.

2. **Statement timeout**: A statement timeout is enforced on all database connections to prevent long-running queries from consuming excessive resources.

3. **SQL validation**: Generated SQL undergoes rigorous validation before execution. The validation service blocks:
   - Non-SELECT statements (only SELECT queries are allowed)
   - Multi-statement queries (to prevent SQL injection via statement chaining)
   - Any SQL containing disallowed keywords or patterns associated with data modification

4. **Encrypted credential storage**: Database credentials are encrypted at rest using AES-256 encryption before being stored in the database. The encryption key is derived from environment variables and is not exposed in the application code or logs.

## What's Not Yet Handled (Multi-tenancy Considerations)

While the current safety model is robust for single-tenant use, extending this architecture to serve multiple users/tenants against a shared database introduces additional risks that are not addressed in the current implementation:

- **No row-level isolation**: The current architecture uses a single set of database credentials per connection. If multiple tenants were to share the same database connection (or even separate connections using the same credentials), there would be no inherent mechanism to prevent a query from one tenant from accessing data belonging to another tenant. A connection's credentials determine what data is visible at the database level, so without additional controls, multi-tenancy would require either:
  - **(a) Separate database credentials per tenant with real Postgres RLS policies**: Each tenant would have their own database user/role, and Row Level Security (RLS) policies would be defined at the database level to restrict each credential's visible rows to only that tenant's data.
  - **(b) Application-level tenant_id filter injected into every generated query**: The application would modify every generated SQL query to include a WHERE clause that filters by tenant_id (e.g., `WHERE tenant_id = current_user_tenant()`). This approach is weaker and more error-prone because it relies on the application correctly modifying every query, and a bug in the SQL generation or modification process could lead to data leakage.

## Recommendation for Future Multi-tenancy Implementation

If multi-tenancy is ever added to this application, we recommend preferring **database-level RLS with per-tenant credentials** over application-level filtering for the following reasons:

- **Defense in depth**: Database-level RLS provides a security boundary that is enforced by the database itself, independent of the application logic. Even if there were a bug in the SQL generation or application code that inadvertently omitted a tenant filter, the database would still prevent access to unauthorized data.
- **Reduced attack surface**: By enforcing tenant isolation at the database level, we eliminate a whole class of application-level bugs that could lead to cross-tenant data leakage.
- **Operational simplicity**: Database permissions and RLS policies are well-understood concepts with mature tooling for auditing and monitoring. This approach leverages the database's built-in security features rather than requiring custom application logic for every query.
- **Performance**: Modern databases are optimized for RLS evaluation, and the performance impact is typically minimal compared to the risk of application-level filtering mistakes.

In summary, while application-level filtering might seem simpler to implement initially, it creates a fragile security model that is prone to failure. Investing in proper database-level RLS from the outset provides a stronger, more reliable foundation for multi-tenancy.

## Compliance and Best Practices

The current implementation follows security best practices for single-tenant applications:
- Principle of least privilege (read-only access)
- Defense in depth (multiple independent security layers)
- Secure credential management (encryption at rest)
- Input validation and output encoding (SQL validation)

When extending to multi-tenancy, these principles should continue to guide the implementation, with database-level RLS serving as the cornerstone of tenant isolation.