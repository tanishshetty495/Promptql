e-- Add tenant_id column to connection_metadata table
ALTER TABLE connection_metadata
ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(36) NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001';

-- Add tenant_id column to query_history table
ALTER TABLE query_history
ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(36) NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001';

-- Add tenant_id column to schema_embeddings table
ALTER TABLE schema_embeddings
ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(36) NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001';

-- Create indexes for better performance on tenant_id queries
CREATE INDEX IF NOT EXISTS idx_connection_metadata_tenant_id ON connection_metadata(tenant_id);
CREATE INDEX IF NOT EXISTS idx_query_history_tenant_id ON query_history(tenant_id);
CREATE INDEX IF NOT EXISTS idx_schema_embeddings_tenant_id ON schema_embeddings(tenant_id);

-- Update existing rows to have a valid tenant_id (if needed)
-- This sets a default tenant_id for all existing rows
UPDATE connection_metadata
SET tenant_id = '00000000-0000-0000-0000-000000000001'
WHERE tenant_id IS NULL OR tenant_id = '';

UPDATE query_history
SET tenant_id = '00000000-0000-0000-0000-000000000001'
WHERE tenant_id IS NULL OR tenant_id = '';

UPDATE schema_embeddings
SET tenant_id = '00000000-0000-0000-0000-000000000001'
WHERE tenant_id IS NULL OR tenant_id = '';

-- Make the columns NOT NULL after setting default values
ALTER TABLE connection_metadata
ALTER COLUMN tenant_id SET NOT NULL;

ALTER TABLE query_history
ALTER COLUMN tenant_id SET NOT NULL;

ALTER TABLE schema_embeddings
ALTER COLUMN tenant_id SET NOT NULL;