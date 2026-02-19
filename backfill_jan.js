const axios = require('axios');

const API_KEY = '2b0450c5714930ad44733cc304b33edeb1c87950ba14a81acd76160504567705';
const BASE_URL = 'https://sh-apk-api-production.up.railway.app/v1/ingest/shealth/daily';
const DEVICE_ID = 'd4593c8e-26ff-4f3f-b056-fc2bb715fbc2';

const data = [
    { date: '2026-01-01', steps: 1601 },
    { date: '2026-01-02', steps: 3102 },
    { date: '2026-01-03', steps: 2612 },
    { date: '2026-01-04', steps: 2927 },
    { date: '2026-01-05', steps: 4494 },
    { date: '2026-01-06', steps: 2945 },
    { date: '2026-01-07', steps: 496 },
    { date: '2026-01-08', steps: 434 },
    { date: '2026-01-09', steps: 245 },
    { date: '2026-01-10', steps: 401 },
    { date: '2026-01-11', steps: 468 },
    { date: '2026-01-12', steps: 1533 },
    { date: '2026-01-13', steps: 3833 },
    { date: '2026-01-14', steps: 3712 },
    { date: '2026-01-15', steps: 2944 },
    { date: '2026-01-16', steps: 2313 }
];

async function backfill() {
    for (const entry of data) {
        const payload = {
            date: entry.date,
            steps_total: entry.steps,
            schema_version: 1,
            source: {
                device_id: DEVICE_ID,
                collected_at: new Date().toISOString()
            }
        };

        try {
            const res = await axios.post(BASE_URL, payload, {
                headers: { 'X-API-Key': API_KEY }
            });
            console.log(`✅ ${entry.date}: ${res.status}`);
        } catch (err) {
            console.error(`❌ ${entry.date}: ${err.message}`);
        }
    }
}

backfill();
