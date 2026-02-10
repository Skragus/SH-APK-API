## Android Bridge APK Plan

This plan covers the Android app that will export Samsung Health daily summaries to your existing FastAPI ingest API.

---

## 1. Tech Stack & Targets

- **Language**: Kotlin
- **Frameworks/Libraries**: AndroidX, WorkManager, Samsung Health SDK, Retrofit/OkHttp, Kotlinx Serialization or Moshi
- **minSdk**: 26
- **targetSdk**: latest stable (update in `compileSdk`/`targetSdk` when a new Android release ships)
- **App structure**: Single `Activity` with a simple setup screen, then effectively headless (only a daily background worker).

---

## 2. High-Level Architecture

- **Setup Activity**
  - Requests Samsung Health read permissions.
  - Generates and stores `device_id` (UUID) in `SharedPreferences` if not already present.
  - Optionally offers a “Test connection” button that triggers one ad-hoc worker run.
  - Shows a simple “Done”/“All set” state.

- **Daily Sync Worker (WorkManager)**
  - `PeriodicWorkRequest` scheduled for ~02:30 local time with `networkType = CONNECTED` and exponential backoff.
  - On run:
    - Computes **local “yesterday”** date.
    - Reads daily summary from Samsung Health (steps, sleep sessions, resting HR if available).
    - Builds JSON payload matching the server expectation.
    - Sends `POST /v1/ingest/shealth/daily` with header `X-API-Key: <BuildConfig.API_KEY>`.
    - On success: logs and exits.
    - On failure: lets WorkManager manage retries; no manual backfill beyond that.

- **Data Layer**
  - `SamsungHealthRepository` to encapsulate all Samsung Health SDK calls.
  - `ApiClient` using Retrofit/OkHttp to handle HTTP calls and JSON serialization.
  - `Preferences` helper for `device_id` and any one-time flags (e.g. “setup completed”).

---

## 3. Data Model (Client Side)

Define Kotlin data classes mirroring your backend `DailyIngestRequest`:

- `DailyIngestRequest`
  - `schemaVersion: Int = 1`
  - `date: String` (formatted `YYYY-MM-DD` in local “yesterday” date)
  - `stepsTotal: Int`
  - `sleepSessions: List<SleepSession>` (may be empty)
  - `heartRateSummary: HeartRateSummary?` (nullable, **only present if `restingHr` is available**)
  - `source: Source`

- `SleepSession`
  - `startTime: String` (ISO-8601 with offset)
  - `endTime: String`
  - `durationMinutes: Int`
  - (later: optional stages field)

- `HeartRateSummary`
  - `restingHr: Int`

- `Source`
  - `sourceApp: String = "samsung_health"`
  - `deviceId: String` (UUID from preferences)
  - `collectedAt: String` (run timestamp ISO-8601 with offset)

---

## 4. WorkManager Design

- **One-time setup**
  - On first app launch after permissions are granted, enqueue a `PeriodicWorkRequest`:
    - Interval: 24 hours.
    - Flex window: choose a window (e.g. 1–2 hours) around 02:30 so WorkManager can optimize.
    - Constraints: `networkType = CONNECTED`.
    - Backoff policy: `EXPONENTIAL` with a sensible initial delay (e.g. 10–15 minutes).

- **Worker class**
  - `SamsungHealthDailyWorker : CoroutineWorker`
  - Steps:
    1. Ensure `device_id` exists; if not, generate and persist it.
    2. Calculate local “yesterday” as a `LocalDate`.
    3. Query Samsung Health for:
       - Total steps for that date.
       - Sleep sessions intersecting that date.
       - Resting heart rate; if not available, set `heartRateSummary = null`.
    4. Map results to data model and serialize to JSON.
    5. Call the API with Retrofit; handle HTTP errors and network errors distinctly for logging.
    6. Return `Result.success()` or `Result.retry()` based on error type.

---

## 5. Networking Layer

- **Retrofit setup**
  - Base URL from `BuildConfig.BASE_URL` (e.g. `https://your-app.up.railway.app/`).
  - JSON converter: Kotlinx Serialization or Moshi.
  - OkHttp client with:
    - Interceptor to add `X-API-Key: BuildConfig.API_KEY` to every request.
    - Reasonable connect/read timeouts (e.g. 5–10 seconds).

- **API interface**
  - `@POST("/v1/ingest/shealth/daily")`
  - `suspend fun postDaily(@Body body: DailyIngestRequest): Response<IngestResponse>`
  - `IngestResponse` matches `{ "status": "ok", "upserted": true }`.

---

## 6. Samsung Health Integration

- Add Samsung Health SDK dependency and required permissions/scopes in `AndroidManifest.xml`.
- Implement `SamsungHealthRepository` to:
  - Connect to Samsung Health.
  - Request read permissions for steps, sleep, heart rate.
  - Fetch yesterday’s summary:
    - Total step count.
    - Sleep sessions (start/end/duration).
    - Resting HR (if available).
- Handle:
  - Permission not granted → surface to setup UI.
  - Data not available → send zero steps and empty lists, or fail gracefully based on what makes sense.

---

## 7. Build Flavors & BuildConfig

- Define at least two flavors:
  - `staging`: points to a staging/base Railway URL; uses a non-production API key.
  - `prod`: points to the production URL and API key.
- For each flavor:
  - `BuildConfig.BASE_URL`
  - `BuildConfig.API_KEY`
- No runtime toggles; switching requires rebuilding with a different flavor.

---

## 8. Local Dev & Testing Strategy

- **Unit tests**
  - Pure Kotlin tests for:
    - Date/“yesterday” calculations.
    - Mapping Samsung Health SDK models → payload models.
  - Mock repositories and API client.

- **Instrumented tests (optional)**
  - Basic smoke test to ensure the worker enqueues and runs.

- **Manual testing**
  - Install `debug` build on your phone.
  - Use:
    - A “Test connection” button in setup Activity, or
    - `WorkManager`’s `OneTimeWorkRequest` triggered via a debug-only button.
  - Check:
    - Logs in Logcat.
    - Server logs / DB rows on your FastAPI side.

---

## 9. Local Environment Setup (Your Machine)

Because you mentioned you have never worked with these technologies, here is a concrete setup guide for Windows:

1. **Install Android Studio**
   - Download from `https://developer.android.com/studio`.
   - Run the installer and accept defaults (standard setup).
   - During setup, ensure the **Android SDK**, **Android SDK Platform-Tools**, and at least one recent **Android SDK Platform** are selected.

2. **Install Java (if prompted)**
   - Recent Android Studio bundles a compatible JDK; if it asks for one, let it install the bundled JDK.

3. **Verify SDK location**
   - Open Android Studio → *More Actions* → *SDK Manager*.
   - Note the **Android SDK location** (e.g. `C:\Users\<you>\AppData\Local\Android\Sdk`).

4. **Clone/open this repo**
   - Ensure `git` is installed and clone `SH-APK-API` (or just continue using your existing local folder).
   - In Android Studio: *File → Open…* and select this repo directory.
   - Later, when we create the Android app module (e.g. `android-app/`), reopen that folder if Android Studio prompts you.

5. **Gradle & build tools**
   - Android Studio will automatically download Gradle and build tools on first sync.
   - If you see a “Sync Now” bar at the top, click it and wait until it finishes with no errors.

6. **Device for testing**
   - Prefer a **real Android phone** (the same one that has Samsung Health and your watch data).
   - Enable **Developer options** and **USB debugging** (or use Wi‑Fi debugging).
   - Connect the phone and ensure it appears under *Run → Select Device* in Android Studio.

7. **Samsung Health**
   - Ensure Samsung Health is installed and logged in on the phone.
   - Ensure your watch is paired and syncing to Samsung Health normally.

Once this is in place, we can scaffold the Android module (`android-app/`) and you will be able to build and run it directly from Android Studio.

---

## 10. Next Steps

1. Create a new Android module or subproject in this repo (e.g. `android-app/`) using Android Studio, with `minSdk 26` and `targetSdk` set to latest stable.
2. Add dependencies: AndroidX, WorkManager, Retrofit/OkHttp, JSON library, Samsung Health SDK.
3. Implement the preferences helper and `device_id` generation.
4. Implement the Retrofit client and API interface.
5. Integrate Samsung Health SDK and implement `SamsungHealthRepository`.
6. Implement the daily worker and its scheduling from the setup Activity.
7. Wire build flavors for staging/prod and set appropriate `BuildConfig` fields.
8. Test end-to-end with your real phone hitting your Railway-hosted API.

