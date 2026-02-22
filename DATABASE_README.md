# Database Orientation for sh-apk-api

This document provides a general overview of the database structure, schemas, and key tables for the Health Connect data pipeline.

## Schemas

### `public`
This schema contains all active, in-use tables for the application.

- **`shealth_daily`**: The primary table for all Health Connect data. See details below.
- **`alembic_version`**: A utility table used by the Alembic tool to track database migration history.

### `legacy`
This schema is used for archiving tables that are no longer actively used by the application but are kept for historical data.

- `calorie_entries`
- `food_references`
- `users`

## Key Tables (`public` schema)

### `shealth_daily`
This is the core table of the service, storing aggregated health data.

- **Source**: Data comes from the Samsung Health Connect APK.
- **Sync Types**: The table stores two distinct types of data entries:
    - **Daily Summaries**: A full sync of the day's data. This is the default entry type.
    - **Intraday Updates**: Partial updates that occur throughout the day.
- **How to Differentiate**: The `source_type` column indicates the type of sync.
    - `source_type = 'daily'`: Represents a full daily summary.
    - `source_type = 'intraday'`: Represents a partial update during the day.
