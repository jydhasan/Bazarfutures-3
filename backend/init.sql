-- BazarFutures — PostgreSQL init
-- Runs once when the container is first created

-- Enable useful extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- fast LIKE/ILIKE search
CREATE EXTENSION IF NOT EXISTS btree_gin; -- GIN indexes on basic types

-- Timezone default
ALTER DATABASE bazarfutures SET timezone TO 'Asia/Dhaka';
