# JSON flattening example (from 05_flatten_json.py)

## Before: one OpenAQ hourly record as received (nested JSON)

```json
{
 "value": 12.8,
 "flagInfo": {
  "hasFlags": false
 },
 "parameter": {
  "id": 15,
  "name": "no2",
  "units": "ppb",
  "displayName": null
 },
 "period": {
  "label": "1hour",
  "interval": "01:00:00",
  "datetimeFrom": {
   "utc": "2025-09-30T23:30:00Z",
   "local": "2025-10-01T05:00:00+05:30"
  },
  "datetimeTo": {
   "utc": "2025-10-01T00:30:00Z",
   "local": "2025-10-01T06:00:00+05:30"
  }
 },
 "coordinates": null,
 "summary": {
  "min": 12.0,
  "q02": 12.012,
  "q25": 12.149999999999999,
  "median": 12.5,
  "q75": 13.125,
  "q98": 14.022,
  "max": 14.1,
  "avg": 12.775000000000002,
  "sd": 0.41633319989322737
 },
 "coverage": {
  "expectedCount": 4,
  "expectedInterval": "01:00:00",
  "observedCount": 4,
  "observedInterval": "01:00:00",
  "percentComplete": 100.0,
  "percentCoverage": 100.0,
  "datetimeFrom": {
   "utc": "2025-09-30T22:45:00Z",
   "local": "2025-10-01T04:15:00+05:30"
  },
  "datetimeTo": {
   "utc": "2025-10-01T00:30:00Z",
   "local": "2025-10-01T06:00:00+05:30"
  }
 }
}
```

## After: the same record as one row (`pd.json_normalize`)

|                             | value                     |
|:----------------------------|:--------------------------|
| value                       | 12.8                      |
| coordinates                 |                           |
| flagInfo.hasFlags           | False                     |
| parameter.id                | 15                        |
| parameter.name              | no2                       |
| parameter.units             | ppb                       |
| parameter.displayName       |                           |
| period.label                | 1hour                     |
| period.interval             | 01:00:00                  |
| period.datetimeFrom.utc     | 2025-09-30T23:30:00Z      |
| period.datetimeFrom.local   | 2025-10-01T05:00:00+05:30 |
| period.datetimeTo.utc       | 2025-10-01T00:30:00Z      |
| period.datetimeTo.local     | 2025-10-01T06:00:00+05:30 |
| summary.min                 | 12.0                      |
| summary.q02                 | 12.012                    |
| summary.q25                 | 12.149999999999999        |
| summary.median              | 12.5                      |
| summary.q75                 | 13.125                    |
| summary.q98                 | 14.022                    |
| summary.max                 | 14.1                      |
| summary.avg                 | 12.775000000000002        |
| summary.sd                  | 0.41633319989322737       |
| coverage.expectedCount      | 4                         |
| coverage.expectedInterval   | 01:00:00                  |
| coverage.observedCount      | 4                         |
| coverage.observedInterval   | 01:00:00                  |
| coverage.percentComplete    | 100.0                     |
| coverage.percentCoverage    | 100.0                     |
| coverage.datetimeFrom.utc   | 2025-09-30T22:45:00Z      |
| coverage.datetimeFrom.local | 2025-10-01T04:15:00+05:30 |
| coverage.datetimeTo.utc     | 2025-10-01T00:30:00Z      |
| coverage.datetimeTo.local   | 2025-10-01T06:00:00+05:30 |
